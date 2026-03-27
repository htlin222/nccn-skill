#!/usr/bin/env python3
"""Extract text chunks from an NCCN PDF based on a toc.json produced by extract_toc.py.

Large chunks are automatically split into sub-chunks by page boundaries to stay
within LLM context/output limits. The --max-chars flag controls the split threshold.
"""

import argparse
import json
import re
import sys
from pathlib import Path

import fitz


def clean_text(text: str) -> str:
    lines = text.split("\n")
    lines = [line.rstrip() for line in lines]
    cleaned = "\n".join(lines)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def extract_page_text(doc: fitz.Document, page_num: int) -> str:
    page_index = page_num - 1
    if page_index < 0 or page_index >= len(doc):
        return ""
    page = doc[page_index]
    return clean_text(page.get_text("text"))


def build_header(chunk: dict, source_pdf: str, part: int | None = None, total_parts: int | None = None) -> str:
    page_range = f"{chunk['page_start']}-{chunk['page_end']}"
    chunk_id = chunk["chunk_id"]
    output_file = chunk["output_file"]

    if part is not None:
        chunk_id = f"{chunk_id}-part{part}"
        base, ext = output_file.rsplit(".", 1)
        output_file = f"{base}-part{part}.{ext}"

    lines = [
        "---",
        f"chunk_id: {chunk_id}",
        f"title: {chunk['title']}",
        f"type: {chunk['type']}",
        f"type: {chunk['type']}",
        f"source_pdf: {source_pdf}",
        f"page_range: {page_range}",
        f"output_file: {output_file}",
    ]
    if part is not None:
        lines.append(f"part: {part}")
        lines.append(f"total_parts: {total_parts}")
    lines.append("---")
    return "\n".join(lines)


def split_chunk_by_pages(
    doc: fitz.Document, chunk: dict, max_chars: int
) -> list[dict]:
    """Split a chunk into sub-chunks that each fit within max_chars.

    Returns a list of sub-chunk dicts with updated page_start, page_end, chunk_id, output_file.
    """
    page_start = chunk["page_start"]
    page_end = chunk["page_end"]

    # Collect per-page text and sizes
    pages = []
    for p in range(page_start, page_end + 1):
        text = extract_page_text(doc, p)
        pages.append((p, text, len(f"\n[PAGE {p}]\n{text}")))

    # Greedily group pages into sub-chunks
    sub_chunks = []
    current_pages = []
    current_chars = 0

    for page_num, text, char_count in pages:
        if current_chars + char_count > max_chars and current_pages:
            sub_chunks.append(current_pages)
            current_pages = []
            current_chars = 0
        current_pages.append((page_num, text))
        current_chars += char_count

    if current_pages:
        sub_chunks.append(current_pages)

    if len(sub_chunks) <= 1:
        return [chunk]

    result = []
    for i, page_group in enumerate(sub_chunks, 1):
        sub = dict(chunk)
        sub["page_start"] = page_group[0][0]
        sub["page_end"] = page_group[-1][0]
        sub["chunk_id"] = f"{chunk['chunk_id']}-part{i}"
        base, ext = chunk["output_file"].rsplit(".", 1)
        sub["output_file"] = f"{base}-part{i}.{ext}"
        sub["_part"] = i
        sub["_total_parts"] = len(sub_chunks)
        sub["_page_texts"] = page_group
        result.append(sub)

    return result


def extract_chunk_text(doc: fitz.Document, chunk: dict) -> str:
    """Extract text for a chunk, using pre-extracted page texts if available."""
    if "_page_texts" in chunk:
        parts = []
        for page_num, text in chunk["_page_texts"]:
            parts.append(f"\n[PAGE {page_num}]\n{text}")
        return "\n".join(parts)

    parts = []
    for page_num in range(chunk["page_start"], chunk["page_end"] + 1):
        text = extract_page_text(doc, page_num)
        parts.append(f"\n[PAGE {page_num}]\n{text}")
    return "\n".join(parts)


def main():
    parser = argparse.ArgumentParser(
        description="Extract text chunks from an NCCN PDF using a toc.json."
    )
    parser.add_argument("pdf", type=Path, help="Path to the source NCCN PDF")
    parser.add_argument(
        "--toc", type=Path, default=None,
        help="Path to toc.json (default: toc.json next to PDF)",
    )
    parser.add_argument(
        "--output-dir", type=Path, default=None,
        help="Output directory for chunk .txt files (default: chunks/ next to PDF)",
    )
    parser.add_argument(
        "--max-chars", type=int, default=50000,
        help="Max characters per chunk before splitting (default: 50000)",
    )
    args = parser.parse_args()

    pdf_path = args.pdf.resolve()
    if not pdf_path.exists():
        print(f"Error: PDF not found: {pdf_path}", file=sys.stderr)
        sys.exit(1)

    pdf_dir = pdf_path.parent
    toc_path = args.toc.resolve() if args.toc else pdf_dir / "toc.json"
    if not toc_path.exists():
        print(f"Error: toc.json not found: {toc_path}", file=sys.stderr)
        sys.exit(1)

    output_dir = args.output_dir.resolve() if args.output_dir else pdf_dir / "chunks"
    output_dir.mkdir(parents=True, exist_ok=True)

    with open(toc_path) as f:
        toc = json.load(f)

    source_pdf = toc.get("source_pdf", pdf_path.name)
    chunks = toc["chunks"]
    doc = fitz.open(str(pdf_path))

    total_chars = 0
    total_output = 0
    splits = 0

    print(f"Processing {len(chunks)} chunks from {source_pdf}")
    print(f"Max chars per chunk: {args.max_chars:,}")
    print(f"Output directory: {output_dir}")
    print("-" * 60)

    # Also write an updated manifest with sub-chunks
    all_output_chunks = []

    for chunk in chunks:
        chunk_id = chunk["chunk_id"]
        page_start = chunk["page_start"]
        page_end = chunk["page_end"]

        # Check if chunk needs splitting
        sub_chunks = split_chunk_by_pages(doc, chunk, args.max_chars)

        if len(sub_chunks) > 1:
            splits += 1
            print(f"  {chunk_id}: pages {page_start}-{page_end} → SPLIT into {len(sub_chunks)} parts")

        for sc in sub_chunks:
            sc_id = sc["chunk_id"]
            body = extract_chunk_text(doc, sc)
            header = build_header(
                sc, source_pdf,
                part=sc.get("_part"),
                total_parts=sc.get("_total_parts"),
            )
            content = f"{header}\n{body}\n"

            out_file = output_dir / f"{sc_id}.txt"
            out_file.write_text(content, encoding="utf-8")

            char_count = len(body)
            total_chars += char_count
            total_output += 1

            part_label = f" (part {sc['_part']}/{sc['_total_parts']})" if "_part" in sc else ""
            print(f"  {sc_id}: pages {sc['page_start']}-{sc['page_end']}, {char_count:,} chars{part_label}")

            # Clean up internal keys before saving to manifest
            manifest_chunk = {k: v for k, v in sc.items() if not k.startswith("_")}
            all_output_chunks.append(manifest_chunk)

    doc.close()

    # Write updated manifest
    manifest_path = output_dir / "chunks-manifest.json"
    with open(manifest_path, "w") as f:
        json.dump(all_output_chunks, f, indent=2, ensure_ascii=False)

    print("-" * 60)
    print(f"Original chunks: {len(chunks)}")
    print(f"Output chunks:   {total_output} ({splits} split)")
    print(f"Total characters extracted: {total_chars:,}")
    print(f"Manifest: {manifest_path}")


if __name__ == "__main__":
    main()
