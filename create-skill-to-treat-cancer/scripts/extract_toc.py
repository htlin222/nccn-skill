#!/usr/bin/env python3
"""Extract TOC from an NCCN guideline PDF and produce a structured toc.json."""

import argparse
import json
import re
import sys
from pathlib import Path
from difflib import SequenceMatcher

import fitz

SKIP_TITLES = {"Panel Members", "Table of Contents"}

# Cancer-agnostic keywords for identifying shared (non-disease) sections.
# These appear across NCCN guidelines for all cancer types.
SHARED_APPENDIX_KEYWORDS = [
    "Supportive Care",
    "Response Criteria",
    "Principles of Radiation",
    "Principles of Systemic",
    "Principles of Surgery",
    "Principles of Imaging",
    "Principles of Pathology",
    "Immunophenotyping",
    "Genetic Testing",
    "Biomarkers",
    "Molecular Analysis",
    "Staging",
    "Performance Status",
    "Survivorship",
    "Palliative Care",
    "CAR T-Cell",
    "Chimeric Antigen Receptor",
    "Discussion",
]

SHARED_MANUSCRIPT_KEYWORDS = [
    "Overview",
    "Supportive Care",
    "Methodology",
    "Literature Search",
]

SLUG_OVERRIDES = {
    "Principles of Radiation Therapy": "radiation-therapy",
    "Principles of Systemic Therapy": "systemic-therapy",
    "Principles of Surgical Management": "surgical-management",
}

CODE_PATTERN = re.compile(r"\(([A-Z][\w-]+-[A-Z0-9]+)\)\s*$")
EMBEDDED_PDF_PATTERN = re.compile(r"^ms_.*\.pdf$", re.IGNORECASE)


def extract_code(title: str) -> str | None:
    m = CODE_PATTERN.search(title)
    return m.group(1) if m else None


def clean_title(title: str) -> str:
    cleaned = CODE_PATTERN.sub("", title).strip()
    return re.sub(r"\s+", " ", cleaned)


def to_slug(title: str) -> str:
    if title in SLUG_OVERRIDES:
        return SLUG_OVERRIDES[title]
    cleaned = clean_title(title)
    for orig, slug in SLUG_OVERRIDES.items():
        if cleaned.startswith(orig.split("/")[0]):
            return slug
    slug = cleaned.lower()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"[\s]+", "-", slug).strip("-")
    slug = re.sub(r"-+", "-", slug)
    return slug


def is_shared_appendix(title: str) -> bool:
    return any(kw.lower() in title.lower() for kw in SHARED_APPENDIX_KEYWORDS)


def is_shared_manuscript(title: str) -> bool:
    return any(kw.lower() == clean_title(title).lower() for kw in SHARED_MANUSCRIPT_KEYWORDS)


def is_embedded_pdf_bookmark(title: str) -> bool:
    return bool(EMBEDDED_PDF_PATTERN.match(title.strip()))


def fuzzy_match(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def find_manuscript_boundary(toc_raw: list[tuple[int, str, int]]) -> int | None:
    for i, (level, title, page) in enumerate(toc_raw):
        if level == 1 and (page == -1 or page < 1) and is_embedded_pdf_bookmark(title):
            return i
    return None


def compute_page_ranges(
    entries: list[dict], section_end_page: int
) -> list[dict]:
    for i, entry in enumerate(entries):
        next_start = None
        current_level = entry["level"]
        for j in range(i + 1, len(entries)):
            if entries[j]["level"] <= current_level:
                next_start = entries[j]["page_start"]
                break
        if next_start is not None and next_start > entry["page_start"]:
            entry["page_end"] = next_start - 1
        elif next_start is not None and next_start <= entry["page_start"]:
            entry["page_end"] = entry["page_start"]
        else:
            entry["page_end"] = section_end_page
    return entries


def build_entries(
    toc_raw: list[tuple[int, str, int]],
    manuscript_boundary_idx: int | None,
    total_pages: int,
) -> tuple[list[dict], int, int]:
    entries = []
    algorithm_entries = []
    manuscript_entries = []

    if manuscript_boundary_idx is not None:
        algo_toc = toc_raw[:manuscript_boundary_idx]
        ms_toc = toc_raw[manuscript_boundary_idx + 1 :]
    else:
        algo_toc = toc_raw
        ms_toc = []

    for level, title, page in algo_toc:
        if page < 1:
            continue
        entries.append(
            {
                "level": level,
                "title": title.replace("\r", " ").strip(),
                "page_start": page,
                "section": "algorithm",
            }
        )
        algorithm_entries.append(entries[-1])

    for level, title, page in ms_toc:
        if page < 1:
            continue
        entries.append(
            {
                "level": level,
                "title": title.replace("\r", " ").strip(),
                "page_start": page,
                "section": "manuscript",
            }
        )
        manuscript_entries.append(entries[-1])

    if manuscript_entries:
        manuscript_start = manuscript_entries[0]["page_start"]
        algorithm_end = manuscript_start - 1
    else:
        algorithm_end = total_pages
        manuscript_start = total_pages + 1

    compute_page_ranges(algorithm_entries, algorithm_end)
    compute_page_ranges(manuscript_entries, total_pages)

    for i, entry in enumerate(entries):
        code = extract_code(entry["title"])
        entry["index"] = i
        entry["code"] = code
        entry["slug"] = to_slug(entry["title"])

    return entries, algorithm_end, (manuscript_start if manuscript_entries else total_pages + 1)


SHARED_OVERVIEW_KEYWORDS = [
    "diagnosis",
    "initial evaluation",
    "workup",
    "clinical presentation",
]


def classify_chunk(title: str, section: str, level: int) -> str:
    cleaned = clean_title(title).lower()
    if section == "algorithm":
        if level == 1 and any(kw in cleaned for kw in SHARED_OVERVIEW_KEYWORDS):
            return "shared-overview"
        if is_shared_appendix(title):
            return "shared-appendix"
        return "disease-algorithm"
    elif section == "manuscript":
        if is_shared_manuscript(title):
            return "shared-manuscript"
        return "disease-manuscript"
    return "unknown"


def build_chunks(entries: list[dict], algorithm_disease_slugs: dict[str, str]) -> list[dict]:
    chunks = []
    seen_ids = set()

    for entry in entries:
        if entry["title"] in SKIP_TITLES:
            continue
        if entry["section"] == "algorithm" and entry["level"] != 1:
            continue
        if entry["section"] == "manuscript" and entry["level"] > 2:
            continue

        chunk_type = classify_chunk(entry["title"], entry["section"], entry["level"])
        slug = entry["slug"]
        cleaned = clean_title(entry["title"])

        if entry["section"] == "manuscript":
            output_file = f"{slug}-evidence.md"
            chunk_id = f"{slug}-manuscript"
        elif chunk_type == "shared-appendix":
            output_file = f"{slug}.md"
            chunk_id = f"{slug}-appendix"
        else:
            output_file = f"{slug}.md"
            chunk_id = f"{slug}-algorithm"

        if chunk_id in seen_ids:
            chunk_id = f"{chunk_id}-{entry['page_start']}"
        seen_ids.add(chunk_id)

        chunks.append(
            {
                "chunk_id": chunk_id,
                "title": entry["title"],
                "section": entry["section"],
                "page_start": entry["page_start"],
                "page_end": entry["page_end"],
                "type": chunk_type,
                "output_file": output_file,
            }
        )

    return chunks


def match_manuscript_to_algorithm(chunks: list[dict]) -> list[dict]:
    algo_chunks = {c["chunk_id"]: c for c in chunks if c["section"] == "algorithm"}
    algo_titles = {clean_title(c["title"]).lower(): c["chunk_id"] for c in chunks if c["section"] == "algorithm"}

    for chunk in chunks:
        if chunk["section"] != "manuscript":
            continue
        cleaned = clean_title(chunk["title"]).lower()
        # 1. Exact match
        if cleaned in algo_titles:
            chunk["matches_algorithm"] = algo_titles[cleaned]
            continue
        # 2. Best fuzzy match above threshold
        best_match = None
        best_score = 0.0
        for algo_title, algo_id in algo_titles.items():
            score = fuzzy_match(cleaned, algo_title)
            if score > best_score and score > 0.85:
                best_score = score
                best_match = algo_id
        if best_match:
            chunk["matches_algorithm"] = best_match

    return chunks


def extract_toc(pdf_path: str, output_path: str | None = None) -> dict:
    pdf_path = Path(pdf_path).resolve()
    if not pdf_path.exists():
        print(f"Error: PDF not found: {pdf_path}", file=sys.stderr)
        sys.exit(1)

    doc = fitz.open(str(pdf_path))
    total_pages = doc.page_count
    toc_raw = doc.get_toc(simple=True)
    doc.close()

    manuscript_idx = find_manuscript_boundary(toc_raw)
    entries, algorithm_end, manuscript_start = build_entries(toc_raw, manuscript_idx, total_pages)

    algo_disease_slugs = {}
    for e in entries:
        if e["section"] == "algorithm" and e["level"] == 1 and e["title"] not in SKIP_TITLES:
            algo_disease_slugs[clean_title(e["title"]).lower()] = e["slug"]

    chunks = build_chunks(entries, algo_disease_slugs)
    chunks = match_manuscript_to_algorithm(chunks)

    result = {
        "source_pdf": pdf_path.name,
        "total_pages": total_pages,
        "algorithm_end_page": algorithm_end,
        "manuscript_start_page": manuscript_start,
        "entries": [
            {
                "index": e["index"],
                "level": e["level"],
                "title": e["title"],
                "page_start": e["page_start"],
                "page_end": e["page_end"],
                "section": e["section"],
                "code": e["code"],
                "slug": e["slug"],
            }
            for e in entries
        ],
        "chunks": chunks,
    }

    if output_path is None:
        output_path = pdf_path.parent / "toc.json"
    else:
        output_path = Path(output_path).resolve()

    with open(output_path, "w") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    print_summary(result, output_path)
    return result


def print_summary(result: dict, output_path: Path) -> None:
    chunks = result["chunks"]
    disease_algo = [c for c in chunks if c["type"] == "disease-algorithm"]
    disease_ms = [c for c in chunks if c["type"] == "disease-manuscript"]
    shared = [c for c in chunks if "shared" in c["type"]]

    print(f"Source:              {result['source_pdf']}")
    print(f"Total pages:         {result['total_pages']}")
    print(f"Algorithm pages:     1-{result['algorithm_end_page']}")
    print(f"Manuscript pages:    {result['manuscript_start_page']}-{result['total_pages']}")
    print(f"TOC entries:         {len(result['entries'])}")
    print(f"Chunks:              {len(chunks)}")
    print(f"  Disease algorithm: {len(disease_algo)}")
    print(f"  Disease manuscript:{len(disease_ms)}")
    print(f"  Shared:            {len(shared)}")
    print(f"Output:              {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Extract TOC from an NCCN guideline PDF into toc.json"
    )
    parser.add_argument("pdf", help="Path to the NCCN PDF file")
    parser.add_argument(
        "--output", "-o", help="Output path for toc.json (default: same directory as PDF)"
    )
    args = parser.parse_args()
    extract_toc(args.pdf, args.output)


if __name__ == "__main__":
    main()
