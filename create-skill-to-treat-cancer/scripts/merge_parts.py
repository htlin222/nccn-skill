#!/usr/bin/env python3
"""Merge multi-part converted files back into single reference files.

When chunk_pdf.py splits a large chunk into parts (e.g., follicular-lymphoma-evidence-part1.md,
part2.md, part3.md), this script merges them into the final output file
(follicular-lymphoma-evidence.md) by concatenating the content.

Usage:
    python merge_parts.py --input-dir converted/ --output-dir merged/
"""

import argparse
import re
import sys
from collections import defaultdict
from pathlib import Path


PART_PATTERN = re.compile(r"^(.+)-part(\d+)(\.md)$")


def find_part_groups(input_dir: Path) -> dict[str, list[Path]]:
    """Group part files by their base name.

    Returns {base_output_file: [part1_path, part2_path, ...]} sorted by part number.
    Non-part files are returned as single-element lists.
    """
    groups: dict[str, list[tuple[int, Path]]] = defaultdict(list)
    standalone: dict[str, list[Path]] = {}

    for f in sorted(input_dir.glob("*.md")):
        m = PART_PATTERN.match(f.name)
        if m:
            base = f"{m.group(1)}{m.group(3)}"
            part_num = int(m.group(2))
            groups[base].append((part_num, f))
        else:
            standalone[f.name] = [f]

    # Sort parts by number
    result = {}
    for base, parts in groups.items():
        parts.sort(key=lambda x: x[0])
        result[base] = [p[1] for p in parts]

    # Add standalone files (no merging needed)
    for name, files in standalone.items():
        if name not in result:
            result[name] = files

    return result


def merge_content(parts: list[Path]) -> str:
    """Merge multiple part files into a single markdown document.

    - Takes the title and header from part 1
    - Strips duplicate titles/headers from subsequent parts
    - Concatenates all content with section dividers
    """
    if len(parts) == 1:
        return parts[0].read_text(encoding="utf-8")

    merged_lines = []

    for i, part_path in enumerate(parts):
        text = part_path.read_text(encoding="utf-8")
        lines = text.splitlines()

        if i == 0:
            # First part: include everything
            merged_lines.extend(lines)
        else:
            # Subsequent parts: skip the title line and HTML comments
            content_started = False
            for line in lines:
                if not content_started:
                    # Skip title (# ...), HTML comments (<!-- ... -->), and blank lines at start
                    if line.startswith("# ") or line.startswith("<!--") or line.strip() == "":
                        continue
                    # Skip TOC sections
                    if line.startswith("## Contents") or line.startswith("## Table of Contents"):
                        # Skip until next non-TOC heading
                        continue
                    if line.startswith("  - [") or line.startswith("- ["):
                        continue
                    content_started = True

                if content_started:
                    merged_lines.append(line)

    return "\n".join(merged_lines)


def update_page_range_in_header(text: str, all_parts: list[Path]) -> str:
    """Update the source comment to reflect the full page range across all parts."""
    # Find all page ranges from part headers
    all_pages = []
    for p in all_parts:
        content = p.read_text(encoding="utf-8")
        for m in re.finditer(r"pages (\d+)-(\d+)", content[:500]):
            all_pages.extend([int(m.group(1)), int(m.group(2))])

    if all_pages:
        min_page = min(all_pages)
        max_page = max(all_pages)
        # Update the first occurrence of "pages X-Y" in the header
        text = re.sub(
            r"(pages )\d+-\d+",
            f"\\g<1>{min_page}-{max_page}",
            text,
            count=1,
        )

    return text


def main():
    parser = argparse.ArgumentParser(
        description="Merge multi-part converted files into single reference files."
    )
    parser.add_argument(
        "--input-dir", type=Path, required=True,
        help="Directory containing converted .md files (may include -partN files)",
    )
    parser.add_argument(
        "--output-dir", type=Path, required=True,
        help="Output directory for merged files",
    )
    args = parser.parse_args()

    input_dir = args.input_dir.resolve()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    groups = find_part_groups(input_dir)

    merged_count = 0
    copied_count = 0

    for output_name, parts in sorted(groups.items()):
        if len(parts) > 1:
            content = merge_content(parts)
            content = update_page_range_in_header(content, parts)
            (output_dir / output_name).write_text(content, encoding="utf-8")
            merged_count += 1
            print(f"  MERGED {len(parts)} parts → {output_name}")
        else:
            content = parts[0].read_text(encoding="utf-8")
            (output_dir / output_name).write_text(content, encoding="utf-8")
            copied_count += 1

    print(f"\nMerged: {merged_count} files ({sum(len(p) for p in groups.values() if len(p) > 1)} parts)")
    print(f"Copied: {copied_count} standalone files")
    print(f"Total:  {merged_count + copied_count} output files")


if __name__ == "__main__":
    main()
