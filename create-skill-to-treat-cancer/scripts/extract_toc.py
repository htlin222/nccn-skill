#!/usr/bin/env python3
"""Extract TOC from an NCCN guideline PDF and produce a structured toc.json.

Design principle: use LOOSE heuristics that work across all NCCN PDF variants.
No reliance on embedded PDF bookmarks, page=-1 markers, or specific TOC patterns.
Chunks at the finest available TOC granularity (L2 if available, else L1).
Classifies chunks by text density, not by TOC position.
"""

import argparse
import json
import re
import sys
from pathlib import Path
from difflib import SequenceMatcher

import fitz

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

SKIP_PATTERNS = [
    "panel members",
    "table of contents",
    "abbreviations",
]

SHARED_KEYWORDS = [
    "principles of",
    "supportive care",
    "response criteria",
    "staging",
    "biomarkers",
    "molecular analysis",
    "immunophenotyping",
    "genetic testing",
    "survivorship",
    "palliative",
    "performance status",
    "monitoring",
    "measurable residual",
    "chimeric antigen receptor",
    "car t-cell",
    "radiation therapy",
    "systemic therapy",
]

EVIDENCE_KEYWORDS = [
    "overview",
    "methodology",
    "literature search",
    "sensitive/inclusive",
    "language usage",
    "summary",
    "guidelines update",
    "risk factors",
    "classification and prognostic",
    "diagnostic evaluation",
    "pathologic evaluation",
    "clinical evaluation",
    "treatment approaches",
    "surveillance",
    "screening",
    "smoking cessation",
    "reconstruction",
]

CODE_PATTERN = re.compile(r"\(([A-Z][\w-]+-[A-Z0-9]+)\)\s*$")
EMBEDDED_PDF_PATTERN = re.compile(r"^ms_.*\.pdf$", re.IGNORECASE)

# Minimum text chars on a page to count as "content" (not just headers/footers)
MIN_PAGE_CONTENT = 200

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def extract_code(title: str) -> str | None:
    m = CODE_PATTERN.search(title)
    return m.group(1) if m else None


def clean_title(title: str) -> str:
    cleaned = CODE_PATTERN.sub("", title).strip()
    return re.sub(r"\s+", " ", cleaned)


def to_slug(title: str) -> str:
    cleaned = clean_title(title).lower()
    slug = re.sub(r"[^a-z0-9\s-]", "", cleaned)
    slug = re.sub(r"[\s]+", "-", slug).strip("-")
    slug = re.sub(r"-+", "-", slug)
    return slug[:80]  # cap length


def should_skip(title: str) -> bool:
    t = clean_title(title).lower()
    return any(p in t for p in SKIP_PATTERNS)


def is_embedded_bookmark(title: str) -> bool:
    return bool(EMBEDDED_PDF_PATTERN.match(title.strip()))


def fuzzy_match(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def classify_by_title(title: str) -> str:
    """Classify a chunk as shared/evidence/disease by title keywords."""
    t = clean_title(title).lower()
    if any(kw in t for kw in SHARED_KEYWORDS):
        return "shared"
    if any(kw in t for kw in EVIDENCE_KEYWORDS):
        return "evidence"
    return "disease"


def measure_text_density(doc: fitz.Document, page_start: int, page_end: int) -> float:
    """Measure average text chars per page for a range. High = narrative, low = flowchart."""
    total = 0
    count = 0
    for p in range(page_start, min(page_end + 1, len(doc) + 1)):
        idx = p - 1
        if 0 <= idx < len(doc):
            text = doc[idx].get_text("text").strip()
            # Strip common headers/footers (NCCN copyright line)
            lines = [l for l in text.splitlines() if not l.startswith("Version") and "NCCN" not in l[:20]]
            total += sum(len(l) for l in lines)
            count += 1
    return total / max(count, 1)


# ---------------------------------------------------------------------------
# Core: Build entries and chunks from TOC
# ---------------------------------------------------------------------------


def compute_page_ranges(entries: list[dict], total_pages: int) -> list[dict]:
    """Compute page_end for each entry based on the next sibling-or-higher entry."""
    for i, entry in enumerate(entries):
        next_start = None
        current_level = entry["level"]
        for j in range(i + 1, len(entries)):
            if entries[j]["level"] <= current_level:
                next_start = entries[j]["page_start"]
                break
        if next_start is not None and next_start > entry["page_start"]:
            entry["page_end"] = next_start - 1
        elif next_start is not None:
            entry["page_end"] = entry["page_start"]
        else:
            entry["page_end"] = total_pages
    return entries


def build_entries(toc_raw: list[tuple[int, str, int]], total_pages: int) -> list[dict]:
    """Convert raw TOC into a flat list of entries with page ranges.

    Skips embedded PDF bookmarks and entries with invalid pages.
    """
    entries = []
    for level, title, page in toc_raw:
        if page < 1:
            continue
        if is_embedded_bookmark(title):
            continue
        entries.append({
            "level": level,
            "title": title.replace("\r", " ").strip(),
            "page_start": page,
        })

    compute_page_ranges(entries, total_pages)

    for i, entry in enumerate(entries):
        entry["index"] = i
        entry["code"] = extract_code(entry["title"])
        entry["slug"] = to_slug(entry["title"])

    return entries


def select_chunk_entries(entries: list[dict]) -> list[dict]:
    """Select which entries become chunks. Strategy: finest available granularity.

    - If a L1 entry has L2 children → use L2 children as chunks (skip L1 parent)
    - If a L1 entry has no L2 children → use L1 as chunk
    - Never go deeper than L2
    """
    # Find L1s that have L2 children
    l1_with_children = set()
    for entry in entries:
        if entry["level"] == 2:
            for other in entries:
                if (other["level"] == 1
                        and other["page_start"] <= entry["page_start"]
                        and other.get("page_end", 9999) >= entry["page_start"]):
                    l1_with_children.add(other["index"])

    selected = []
    for entry in entries:
        if should_skip(entry["title"]):
            continue
        if entry["level"] == 1 and entry["index"] in l1_with_children:
            continue  # Skip parent; L2 children will be selected
        if entry["level"] > 2:
            continue
        selected.append(entry)

    return selected


def build_chunks(
    entries: list[dict],
    doc: fitz.Document | None = None,
) -> list[dict]:
    """Build chunk definitions from selected entries.

    Uses text density (if doc provided) to classify: dense text = evidence, sparse = algorithm.
    Falls back to title-keyword classification.
    """
    selected = select_chunk_entries(entries)
    chunks = []
    seen_ids = set()

    for entry in selected:
        title = entry["title"]
        slug = entry["slug"]
        page_start = entry["page_start"]
        page_end = entry.get("page_end", page_start)

        # Classify by title keywords
        category = classify_by_title(title)

        # Refine with text density if PDF doc available
        chunk_type = "disease-algorithm"
        if category == "shared":
            chunk_type = "shared-appendix"
        elif category == "evidence":
            chunk_type = "disease-manuscript"
        else:
            # Use density: narrative manuscript pages have >2000 chars/page avg
            if doc:
                density = measure_text_density(doc, page_start, page_end)
                if density > 2500:
                    chunk_type = "disease-manuscript"

        # Determine output file name
        if chunk_type == "disease-manuscript":
            output_file = f"{slug}-evidence.md"
            chunk_id = f"{slug}-manuscript"
        elif chunk_type == "shared-appendix":
            output_file = f"{slug}.md"
            chunk_id = f"{slug}-appendix"
        else:
            output_file = f"{slug}.md"
            chunk_id = f"{slug}-algorithm"

        # Deduplicate IDs
        if chunk_id in seen_ids:
            chunk_id = f"{chunk_id}-{page_start}"
            output_file = output_file.replace(".md", f"-{page_start}.md")
        seen_ids.add(chunk_id)

        chunks.append({
            "chunk_id": chunk_id,
            "title": title,
            "page_start": page_start,
            "page_end": page_end,
            "type": chunk_type,
            "output_file": output_file,
        })

    return chunks


def match_evidence_to_algorithm(chunks: list[dict]) -> list[dict]:
    """Try to pair evidence chunks with their algorithm counterparts."""
    algo_titles = {
        clean_title(c["title"]).lower(): c["chunk_id"]
        for c in chunks if c["type"] == "disease-algorithm"
    }

    for chunk in chunks:
        if chunk["type"] != "disease-manuscript":
            continue
        cleaned = clean_title(chunk["title"]).lower()
        if cleaned in algo_titles:
            chunk["matches_algorithm"] = algo_titles[cleaned]
            continue
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


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def extract_toc(pdf_path: str, output_path: str | None = None) -> dict:
    pdf_path = Path(pdf_path).resolve()
    if not pdf_path.exists():
        print(f"Error: PDF not found: {pdf_path}", file=sys.stderr)
        sys.exit(1)

    doc = fitz.open(str(pdf_path))
    total_pages = doc.page_count
    toc_raw = doc.get_toc(simple=True)

    entries = build_entries(toc_raw, total_pages)
    chunks = build_chunks(entries, doc=doc)
    chunks = match_evidence_to_algorithm(chunks)

    doc.close()

    result = {
        "source_pdf": pdf_path.name,
        "total_pages": total_pages,
        "entries": [
            {
                "index": e["index"],
                "level": e["level"],
                "title": e["title"],
                "page_start": e["page_start"],
                "page_end": e.get("page_end", e["page_start"]),
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

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    print_summary(result, output_path)
    return result


def print_summary(result: dict, output_path: Path) -> None:
    chunks = result["chunks"]
    algo = [c for c in chunks if c["type"] == "disease-algorithm"]
    evidence = [c for c in chunks if c["type"] == "disease-manuscript"]
    shared = [c for c in chunks if "shared" in c["type"]]

    print(f"Source:     {result['source_pdf']}")
    print(f"Pages:      {result['total_pages']}")
    print(f"TOC:        {len(result['entries'])} entries")
    print(f"Chunks:     {len(chunks)} ({len(algo)} algorithm, {len(evidence)} evidence, {len(shared)} shared)")
    print(f"Output:     {output_path}")


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
