#!/usr/bin/env python3
"""Validate citation coverage in reference files to detect potential hallucination."""

import argparse
import re
import sys
from pathlib import Path


def parse_page_range(content: str) -> tuple[int | None, int | None]:
    m = re.search(r'pages?\s+(\d+)\s*[-\u2013]\s*(\d+)', content, re.IGNORECASE)
    if m:
        return int(m.group(1)), int(m.group(2))
    return None, None


def extract_citations(content: str) -> list[tuple[int, int]]:
    citations = []
    for i, line in enumerate(content.splitlines(), 1):
        for m in re.finditer(r'\[p\.?\s*(\d+)\]', line):
            citations.append((i, int(m.group(1))))
    return citations


def find_uncited_zones(content: str) -> list[tuple[int, int]]:
    lines = content.splitlines()
    zones = []
    run_start = None
    run_len = 0

    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        is_content = bool(stripped) and not re.match(r'^#{1,6}\s', line)
        has_citation = bool(re.search(r'\[p\.?\s*\d+\]', line))

        if is_content and not has_citation:
            if run_start is None:
                run_start = i
            run_len += 1
        else:
            if run_len >= 3:
                zones.append((run_start, run_start + run_len - 1))
            run_start = None
            run_len = 0

    if run_len >= 3:
        zones.append((run_start, run_start + run_len - 1))

    return zones


def count_content_lines(content: str) -> int:
    count = 0
    for line in content.splitlines():
        stripped = line.strip()
        if stripped and not re.match(r'^#{1,6}\s', stripped):
            count += 1
    return count


def validate_file(filepath: Path, skill_dir: Path) -> bool:
    content = filepath.read_text(encoding='utf-8')
    rel = filepath.relative_to(skill_dir)
    print(f"--- {rel} ---")

    citations = extract_citations(content)
    total_citations = len(citations)
    print(f"  Citations found: {total_citations}")

    page_start, page_end = parse_page_range(content)
    passed = True

    if page_start is not None and page_end is not None:
        out_of_range = [(ln, p) for ln, p in citations if p < page_start or p > page_end]
        if out_of_range:
            print(f"  \u2717 Out-of-range citations (declared pages {page_start}-{page_end}):")
            for ln, p in out_of_range:
                print(f"    line {ln}: [p.{p}]")
            passed = False
        else:
            print(f"  \u2713 All citations within declared range ({page_start}-{page_end})")
    else:
        print("  - No page range declared in header")

    zones = find_uncited_zones(content)
    if zones:
        print(f"  \u2717 Uncited zones ({len(zones)}):")
        for start, end in zones:
            print(f"    lines {start}-{end}")
        passed = False
    else:
        print("  \u2713 No uncited zones")

    content_lines = count_content_lines(content)
    if content_lines > 0:
        density = total_citations / content_lines
        status = "\u2713" if density >= 0.1 else "\u2717"
        print(f"  {status} Citation density: {density:.3f} ({total_citations}/{content_lines})")
        if density < 0.1:
            print("    WARNING: density below 0.1 threshold")
            passed = False
    else:
        print("  - No content lines found")

    return passed


def main():
    parser = argparse.ArgumentParser(description='Validate citation coverage in reference files.')
    parser.add_argument('skill_dir', type=Path, help='Path to the skill output directory')
    args = parser.parse_args()

    skill_dir = args.skill_dir.resolve()
    if not skill_dir.is_dir():
        print(f"Error: {skill_dir} is not a directory")
        sys.exit(1)

    refs_dir = skill_dir / 'references'
    if not refs_dir.is_dir():
        print("No references/ directory found.")
        sys.exit(0)

    md_files = sorted(refs_dir.glob('*.md'))
    if not md_files:
        print("No markdown files in references/.")
        sys.exit(0)

    print("=== Citation Validation ===\n")

    all_passed = True
    for md in md_files:
        if not validate_file(md, skill_dir):
            all_passed = False
        print()

    if all_passed:
        print("RESULT: PASS")
        sys.exit(0)
    else:
        print("RESULT: FAIL")
        sys.exit(1)


if __name__ == '__main__':
    main()
