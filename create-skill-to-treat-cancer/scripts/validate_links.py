#!/usr/bin/env python3
"""Validate all markdown links in a generated skill package."""

import argparse
import re
import sys
import unicodedata
from pathlib import Path


def heading_to_slug(heading: str) -> str:
    text = heading.lower().strip()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[\s]+', '-', text)
    text = text.strip('-')
    return text


def extract_headings(filepath: Path) -> set[str]:
    slugs = set()
    try:
        for line in filepath.read_text(encoding='utf-8').splitlines():
            m = re.match(r'^(#{1,6})\s+(.+)', line)
            if m:
                slugs.add(heading_to_slug(m.group(2)))
    except (OSError, UnicodeDecodeError):
        pass
    return slugs


def extract_markdown_links(filepath: Path) -> list[tuple[int, str, str]]:
    links = []
    try:
        for i, line in enumerate(filepath.read_text(encoding='utf-8').splitlines(), 1):
            for m in re.finditer(r'\[([^\]]*)\]\(([^)]+)\)', line):
                links.append((i, m.group(1), m.group(2)))
    except (OSError, UnicodeDecodeError):
        pass
    return links


def check_relative_links(skill_dir: Path, all_files: list[Path]) -> list[str]:
    errors = []
    for filepath in all_files:
        for lineno, text, target in extract_markdown_links(filepath):
            if target.startswith(('http://', 'https://', 'mailto:')):
                continue
            path_part, _, anchor = target.partition('#')
            if path_part:
                resolved = (filepath.parent / path_part).resolve()
                if not resolved.exists():
                    errors.append(f"  {filepath.relative_to(skill_dir)}:{lineno} -> {target} (file not found)")
                elif anchor:
                    slugs = extract_headings(resolved)
                    if heading_to_slug(anchor) not in slugs:
                        errors.append(f"  {filepath.relative_to(skill_dir)}:{lineno} -> {target} (heading not found)")
            elif anchor:
                slugs = extract_headings(filepath)
                if heading_to_slug(anchor) not in slugs:
                    errors.append(f"  {filepath.relative_to(skill_dir)}:{lineno} -> #{anchor} (heading not found)")
    return errors


def check_orphan_files(skill_dir: Path, refs_dir: Path) -> list[str]:
    if not refs_dir.is_dir():
        return []
    skill_md = skill_dir / 'SKILL.md'
    if not skill_md.exists():
        return []

    linked_targets = set()
    for _, _, target in extract_markdown_links(skill_md):
        if target.startswith(('http://', 'https://', 'mailto:')):
            continue
        path_part = target.partition('#')[0]
        if path_part:
            resolved = (skill_md.parent / path_part).resolve()
            linked_targets.add(resolved)

    orphans = []
    for md in sorted(refs_dir.glob('*.md')):
        if md.resolve() not in linked_targets:
            orphans.append(f"  {md.relative_to(skill_dir)} (not linked from SKILL.md)")
    return orphans


def check_evidence_pairs(refs_dir: Path, skill_dir: Path) -> list[str]:
    if not refs_dir.is_dir():
        return []
    errors = []
    for md in sorted(refs_dir.glob('*-evidence.md')):
        base_name = md.name.replace('-evidence.md', '.md')
        base_path = refs_dir / base_name
        if not base_path.exists():
            errors.append(f"  {md.relative_to(skill_dir)} has no matching base file ({base_name})")
    return errors


def main():
    parser = argparse.ArgumentParser(description='Validate markdown links in a skill package.')
    parser.add_argument('skill_dir', type=Path, help='Path to the skill output directory')
    args = parser.parse_args()

    skill_dir = args.skill_dir.resolve()
    if not skill_dir.is_dir():
        print(f"Error: {skill_dir} is not a directory")
        sys.exit(1)

    refs_dir = skill_dir / 'references'
    all_files = []
    skill_md = skill_dir / 'SKILL.md'
    if skill_md.exists():
        all_files.append(skill_md)
    if refs_dir.is_dir():
        all_files.extend(sorted(refs_dir.glob('*.md')))

    all_passed = True

    print("=== Link Validation ===\n")

    # Check 1: Relative links resolve
    errors = check_relative_links(skill_dir, all_files)
    if errors:
        print("\u2717 Broken links found:")
        for e in errors:
            print(e)
        all_passed = False
    else:
        print("\u2713 All relative and anchor links resolve correctly")

    # Check 2: No orphan files
    orphans = check_orphan_files(skill_dir, refs_dir)
    if orphans:
        print("\u2717 Orphan files (not linked from SKILL.md):")
        for o in orphans:
            print(o)
        all_passed = False
    else:
        print("\u2713 No orphan files in references/")

    # Check 3: Evidence files have matching base files (warning only)
    evidence_errors = check_evidence_pairs(refs_dir, skill_dir)
    if evidence_errors:
        print("\u26a0 Evidence files without base counterpart (expected for manuscript-only diseases):")
        for e in evidence_errors:
            print(e)
    else:
        print("\u2713 All evidence files have matching base files")

    print()
    if all_passed:
        print("RESULT: PASS")
        sys.exit(0)
    else:
        print("RESULT: FAIL")
        sys.exit(1)


if __name__ == '__main__':
    main()
