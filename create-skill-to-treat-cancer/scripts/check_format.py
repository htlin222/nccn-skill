#!/usr/bin/env python3
"""Validate Vercel Skills protocol compliance."""

import argparse
import re
import sys
from pathlib import Path


def parse_frontmatter(content: str) -> tuple[dict[str, str] | None, str]:
    if not content.startswith('---'):
        return None, content
    parts = content.split('---', 2)
    if len(parts) < 3:
        return None, content
    fm_raw = parts[1].strip()
    fm = {}
    for line in fm_raw.splitlines():
        if ':' in line:
            key, _, val = line.partition(':')
            fm[key.strip()] = val.strip().strip('"').strip("'")
    return fm, parts[2]


def check_skill_md_exists(skill_dir: Path) -> tuple[bool, str]:
    exists = (skill_dir / 'SKILL.md').exists()
    return exists, "SKILL.md exists"


def check_frontmatter_valid(skill_dir: Path) -> tuple[bool, str]:
    content = (skill_dir / 'SKILL.md').read_text(encoding='utf-8')
    fm, _ = parse_frontmatter(content)
    if fm is None:
        return False, "SKILL.md has valid YAML frontmatter"
    return True, "SKILL.md has valid YAML frontmatter"


def check_name_field(skill_dir: Path) -> tuple[bool, str]:
    content = (skill_dir / 'SKILL.md').read_text(encoding='utf-8')
    fm, _ = parse_frontmatter(content)
    label = "Frontmatter 'name' field is valid"
    if fm is None:
        return False, label
    name = fm.get('name', '')
    if not name:
        return False, f"{label} (missing)"
    if len(name) > 64:
        return False, f"{label} (exceeds 64 chars: {len(name)})"
    if not re.match(r'^[a-z0-9]([a-z0-9-]*[a-z0-9])?$', name):
        return False, f"{label} (invalid format: '{name}')"
    return True, label


def check_description_field(skill_dir: Path) -> tuple[bool, str]:
    content = (skill_dir / 'SKILL.md').read_text(encoding='utf-8')
    fm, _ = parse_frontmatter(content)
    label = "Frontmatter 'description' field is valid"
    if fm is None:
        return False, label
    desc = fm.get('description', '')
    if not desc:
        return False, f"{label} (missing or empty)"
    if len(desc) > 1024:
        return False, f"{label} (exceeds 1024 chars: {len(desc)})"
    return True, label


def check_body_length(skill_dir: Path) -> tuple[bool, str]:
    content = (skill_dir / 'SKILL.md').read_text(encoding='utf-8')
    _, body = parse_frontmatter(content)
    line_count = len(body.strip().splitlines())
    label = f"SKILL.md body under 500 lines ({line_count} lines)"
    return line_count <= 500, label


def check_toc_in_long_files(skill_dir: Path) -> tuple[bool, list[str]]:
    refs_dir = skill_dir / 'references'
    if not refs_dir.is_dir():
        return True, []
    errors = []
    for md in sorted(refs_dir.glob('*.md')):
        lines = md.read_text(encoding='utf-8').splitlines()
        if len(lines) <= 100:
            continue
        header_lines = lines[:20]
        has_toc = any(
            re.search(r'contents|toc', line, re.IGNORECASE)
            for line in header_lines
            if re.match(r'^#{1,6}\s', line)
        )
        if not has_toc:
            errors.append(str(md.relative_to(skill_dir)))
    return len(errors) == 0, errors


def check_one_level_deep(skill_dir: Path) -> tuple[bool, list[str]]:
    refs_dir = skill_dir / 'references'
    if not refs_dir.is_dir():
        return True, []
    violations = []
    for md in sorted(refs_dir.glob('*.md')):
        content = md.read_text(encoding='utf-8')
        for m in re.finditer(r'\[([^\]]*)\]\(([^)]+)\)', content):
            target = m.group(2)
            if target.startswith(('http://', 'https://', 'mailto:')):
                continue
            path_part = target.partition('#')[0]
            if not path_part:
                continue
            resolved = (md.parent / path_part).resolve()
            try:
                resolved.relative_to(refs_dir.resolve())
                violations.append(f"  {md.relative_to(skill_dir)} -> {target}")
            except ValueError:
                pass
    return len(violations) == 0, violations


def main():
    parser = argparse.ArgumentParser(description='Validate Vercel Skills protocol compliance.')
    parser.add_argument('skill_dir', type=Path, help='Path to the skill output directory')
    args = parser.parse_args()

    skill_dir = args.skill_dir.resolve()
    if not skill_dir.is_dir():
        print(f"Error: {skill_dir} is not a directory")
        sys.exit(1)

    print("=== Format Validation ===\n")

    all_passed = True

    # Check 1: SKILL.md exists
    ok, msg = check_skill_md_exists(skill_dir)
    print(f"{'✓' if ok else '✗'} {msg}")
    if not ok:
        all_passed = False
        print("\nRESULT: FAIL")
        sys.exit(1)

    # Check 2: Valid frontmatter
    ok, msg = check_frontmatter_valid(skill_dir)
    print(f"{'✓' if ok else '✗'} {msg}")
    if not ok:
        all_passed = False

    # Check 3: Name field
    ok, msg = check_name_field(skill_dir)
    print(f"{'✓' if ok else '✗'} {msg}")
    if not ok:
        all_passed = False

    # Check 4: Description field
    ok, msg = check_description_field(skill_dir)
    print(f"{'✓' if ok else '✗'} {msg}")
    if not ok:
        all_passed = False

    # Check 5: Body length
    ok, msg = check_body_length(skill_dir)
    print(f"{'✓' if ok else '✗'} {msg}")
    if not ok:
        all_passed = False

    # Check 6: TOC in long reference files
    ok, missing_toc = check_toc_in_long_files(skill_dir)
    if ok:
        print("\u2713 All long reference files have a table of contents")
    else:
        print("\u2717 Reference files over 100 lines missing TOC:")
        for f in missing_toc:
            print(f"  {f}")
        all_passed = False

    # Check 7: One-level-deep rule (warning only — clinical cross-references are expected)
    ok, violations = check_one_level_deep(skill_dir)
    if ok:
        print("\u2713 No cross-references between reference files")
    else:
        print(f"\u26a0 Reference files with cross-links ({len(violations)} found, expected for NCCN guidelines)")

    print()
    if all_passed:
        print("RESULT: PASS")
        sys.exit(0)
    else:
        print("RESULT: FAIL")
        sys.exit(1)


if __name__ == '__main__':
    main()
