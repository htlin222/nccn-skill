#!/usr/bin/env python3
"""Assemble converted markdown chunks into a complete NCCN skill package.

Cancer-agnostic: categories are derived from chunk types in toc.json, not
from hardcoded disease-specific keywords.

Usage:
    python assemble_skill.py \
        --chunks-dir converted/ \
        --toc toc.json \
        --output-dir nccn-<guideline>/ \
        --template assets/skill-md-template.yaml \
        [--categories categories.json]
"""

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

import yaml


# ---------------------------------------------------------------------------
# Cancer-agnostic category system
# ---------------------------------------------------------------------------

# Shared-resource keywords are universal across all NCCN guidelines.
# Disease categories are NOT hardcoded — diseases are grouped under
# a generic "Disease Subtypes" heading, or under categories supplied
# via an optional --categories JSON file.
SHARED_KEYWORDS: list[str] = [
    "diagnosis",
    "supportive care",
    "response criteria",
    "principles of",
    "radiation therapy",
    "imaging",
    "surgical",
    "pathology",
    "biomarkers",
    "genetic testing",
    "immunophenotyping",
    "staging",
    "performance status",
    "survivorship",
    "palliative",
    "overview",
    "guidelines update",
    "methodology",
    "sensitive/inclusive",
    "language usage",
    "car t-cell",
    "car-t",
    "chimeric antigen receptor",
]

# Special-population keywords are universal across cancer types.
SPECIAL_POPULATION_KEYWORDS: list[str] = [
    "hiv",
    "post-transplant",
    "posttransplant",
    "transplant",
    "pediatric",
    "adolescent",
    "pregnancy",
    "elderly",
    "geriatric",
    "older adult",
]

# Description templates for different chunk types
ALGO_DESC = "Staging, workup, and treatment pathways"
EVIDENCE_DESC = "Discussion of clinical evidence and rationale"

# Shared-resource description lookup (cancer-agnostic)
SHARED_DESCRIPTIONS: dict[str, str] = {
    "diagnosis": "Initial evaluation and diagnostic workup",
    "supportive care": "Supportive care guidelines",
    "response criteria": "Standardized response assessment criteria",
    "radiation": "Radiation therapy guidelines",
    "surgical": "Surgical treatment principles",
    "pathology": "Pathologic evaluation guidelines",
    "biomarkers": "Biomarker testing guidelines",
    "imaging": "Imaging and surveillance guidelines",
    "car t": "CAR T-cell therapy protocols",
    "car-t": "CAR T-cell therapy protocols",
    "immunophenotyping": "Immunophenotyping and genetic testing panels",
    "genetic testing": "Molecular and genetic testing panels",
    "staging": "Staging classification",
    "survivorship": "Survivorship care guidelines",
    "palliative": "Palliative and end-of-life care",
    "principles": "General treatment principles",
}

# Pattern for cross-disease references: "See NSCLC-1", "see FOLL-A 2 of 5", etc.
# This is cancer-agnostic — it matches any NCCN page code format.
CROSS_REF_PATTERN = re.compile(
    r"\bSee\s+([A-Z][A-Z0-9]+-[A-Z]?\d+(?:\s+of\s+\d+)?)",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def load_json(path: Path) -> dict:
    with open(path) as f:
        return json.load(f)


def load_yaml(path: Path) -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def classify_disease(
    title: str, chunk_type: str, custom_categories: dict[str, list[str]] | None = None
) -> str:
    """Classify a chunk title into a navigation category.

    Uses chunk_type for shared resources, optional custom_categories for
    guideline-specific grouping, and falls back to "Disease Subtypes" for
    unmatched disease entries. No cancer-specific terms are hardcoded.
    """
    if chunk_type.startswith("shared"):
        return "Shared Resources"

    title_lower = title.lower()

    # Check shared keywords (universal across all NCCN guidelines)
    for keyword in SHARED_KEYWORDS:
        if keyword in title_lower:
            return "Shared Resources"

    # Check special populations (universal)
    for keyword in SPECIAL_POPULATION_KEYWORDS:
        if keyword in title_lower:
            return "Special Populations"

    # Check custom categories if provided (from --categories file)
    if custom_categories:
        best_category = None
        best_score = 0
        for category, keywords in custom_categories.items():
            for keyword in keywords:
                if keyword.lower() in title_lower:
                    score = len(keyword)
                    if score > best_score:
                        best_score = score
                        best_category = category
        if best_category:
            return best_category

    # Default: all disease entries go under "Disease Subtypes"
    return "Disease Subtypes"


def get_shared_description(title: str) -> str:
    """Return a contextual description for a shared resource based on its title."""
    title_lower = title.lower()
    for keyword, desc in SHARED_DESCRIPTIONS.items():
        if keyword in title_lower:
            return desc
    return "Shared clinical resource"


def build_code_to_file_map(chunks: list[dict], entries: list[dict]) -> dict[str, str]:
    """Build a mapping from NCCN page codes (e.g., FOLL-1) to output filenames.

    Uses entries from toc.json to find codes, then maps the code prefix to the
    output_file from the corresponding chunk.
    """
    code_prefix_to_file: dict[str, str] = {}
    slug_to_file: dict[str, str] = {}

    # Build slug -> output_file from chunks
    for chunk in chunks:
        slug = chunk.get("chunk_id", "").replace("-algorithm", "").replace("-manuscript", "")
        slug_to_file[slug] = chunk["output_file"]

    # Map code prefixes to output files via entries
    for entry in entries:
        code = entry.get("code")
        if not code:
            continue
        # Extract the prefix from the code: "FOLL-1" -> "FOLL"
        prefix = code.rsplit("-", 1)[0] if "-" in code else code
        slug = entry.get("slug", "")
        if slug in slug_to_file and prefix not in code_prefix_to_file:
            code_prefix_to_file[prefix] = slug_to_file[slug]

    return code_prefix_to_file


def resolve_cross_references(text: str, code_to_file: dict[str, str]) -> str:
    """Replace cross-disease references like 'See CODE-1' with markdown links."""

    def replace_ref(match: re.Match) -> str:
        full_ref = match.group(1)
        # Extract prefix: "CODE-1" -> "CODE", "CODE-A 2 of 5" -> "CODE"
        prefix = re.split(r"-[A-Z]?\d+", full_ref)[0]
        if prefix in code_to_file:
            target_file = code_to_file[prefix]
            return f"See [{full_ref}]({target_file})"
        return match.group(0)

    return CROSS_REF_PATTERN.sub(replace_ref, text)


def render_frontmatter(template: dict, variables: dict[str, str]) -> str:
    """Render the YAML frontmatter by substituting template variables."""
    rendered = yaml.dump(template, default_flow_style=False, allow_unicode=True, sort_keys=False)
    for key, value in variables.items():
        rendered = rendered.replace(f"{{{{{key}}}}}", value)
    return f"---\n{rendered}---"


def clean_title(title: str) -> str:
    """Remove NCCN page codes from a title string."""
    return re.sub(r"\s*\([A-Z][\w-]+-[A-Z0-9]+\)\s*$", "", title).strip()


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------


def group_chunks_by_disease(
    chunks: list[dict], custom_categories: dict[str, list[str]] | None = None
) -> dict[str, dict]:
    """Group chunks into disease records with algorithm and evidence files.

    Returns {slug: {title, category, algorithm_file, evidence_file}}.
    """
    diseases: dict[str, dict] = {}

    for chunk in chunks:
        chunk_type = chunk["type"]
        title = clean_title(chunk["title"])
        output_file = chunk["output_file"]
        category = classify_disease(title, chunk_type, custom_categories)

        # Determine slug key for grouping
        if chunk_type == "disease-manuscript":
            # Match to algorithm via matches_algorithm or derive from slug
            slug = chunk.get("matches_algorithm", "").replace("-algorithm", "")
            if not slug:
                slug = output_file.replace("-evidence.md", "")
        elif chunk_type == "disease-algorithm":
            slug = output_file.replace(".md", "")
        else:
            # Shared resources: use output filename as key
            slug = output_file.replace(".md", "")

        if slug not in diseases:
            diseases[slug] = {
                "title": title,
                "category": category,
                "algorithm_file": None,
                "evidence_file": None,
            }

        if chunk_type == "disease-manuscript":
            diseases[slug]["evidence_file"] = output_file
        elif chunk_type == "disease-algorithm":
            diseases[slug]["algorithm_file"] = output_file
        else:
            # Shared: treat as algorithm (single file)
            diseases[slug]["algorithm_file"] = output_file

    return diseases


def render_skill_md(
    diseases: dict[str, dict],
    frontmatter: str,
    guideline_name: str,
    version: str,
) -> str:
    """Render the complete SKILL.md content."""
    lines: list[str] = [frontmatter, ""]
    lines.append(f"# NCCN Guidelines: {guideline_name}")
    lines.append("")
    lines.append(
        f"> Clinical decision support derived from NCCN Clinical Practice Guidelines in\n"
        f"> Oncology. Version {version}."
    )
    lines.append("")

    # Group by category, preserving insertion order within each
    categories: dict[str, list[tuple[str, dict]]] = {}
    for slug, info in diseases.items():
        cat = info["category"]
        if cat not in categories:
            categories[cat] = []
        categories[cat].append((slug, info))

    # Desired category order: disease subtypes first, then special pops, shared last
    # Any custom categories from --categories file appear in their natural order
    known_order = ["Disease Subtypes", "Special Populations", "Shared Resources"]
    custom_cats = [c for c in categories if c not in known_order]
    ordered = custom_cats + known_order
    for cat in ordered:
        if cat not in categories:
            continue
        entries = categories[cat]
        lines.append(f"## {cat}")
        lines.append("")

        for slug, info in entries:
            title = info["title"]
            algo = info["algorithm_file"]
            evidence = info["evidence_file"]

            lines.append(f"### {title}")
            lines.append("")

            has_content = algo or evidence
            if not has_content:
                # Skip entries with no linked files
                # Remove the heading we just added
                lines.pop()  # empty line
                lines.pop()  # ### heading
                continue

            if info["category"] == "Shared Resources":
                desc = get_shared_description(title)
                if algo:
                    lines.append(f"- [{title}](references/{algo}) -- {desc}")
                if evidence:
                    lines.append(f"- [{title} (Evidence)](references/{evidence}) -- {desc}")
            else:
                if algo:
                    lines.append(f"- [Algorithm: {title}](references/{algo}) -- {ALGO_DESC}")
                if evidence:
                    lines.append(f"- [Evidence: {title}](references/{evidence}) -- {EVIDENCE_DESC}")

            lines.append("")

    # Citation footer
    lines.append("---")
    lines.append("")
    lines.append(
        f"> **Citation**: NCCN Clinical Practice Guidelines in Oncology: {guideline_name},\n"
        f"> Version {version}. National Comprehensive Cancer Network. Available at nccn.org.\n"
        f">\n"
        f"> This skill references copyrighted NCCN content. Refer to nccn.org for the\n"
        f"> authoritative source and full terms of use."
    )
    lines.append("")

    return "\n".join(lines)


def verify_completeness(chunks: list[dict], refs_dir: Path) -> list[str]:
    """Check that every chunk in toc.json has a corresponding output file.

    Returns a list of missing file descriptions.
    """
    missing = []
    for chunk in chunks:
        expected = refs_dir / chunk["output_file"]
        if not expected.exists():
            missing.append(f"  {chunk['chunk_id']} -> {chunk['output_file']}")
    return missing


def assemble(
    chunks_dir: Path,
    toc_path: Path,
    output_dir: Path,
    template_path: Path,
    guideline_name: str | None = None,
    version: str | None = None,
    categories_path: Path | None = None,
) -> None:
    """Main assembly routine."""
    # Load inputs
    toc = load_json(toc_path)
    template = load_yaml(template_path)
    chunks = toc["chunks"]
    entries = toc.get("entries", [])

    # Load optional custom categories (cancer-specific groupings)
    custom_categories = None
    if categories_path and categories_path.exists():
        custom_categories = load_json(categories_path)
        print(f"  Custom categories: {list(custom_categories.keys())}")

    # Derive guideline name from the toc source if not given
    if not guideline_name:
        pdf_name = toc.get("source_pdf", "guideline")
        guideline_name = re.sub(r"\.pdf$", "", pdf_name, flags=re.IGNORECASE)
        guideline_name = re.sub(r"[-_]", " ", guideline_name).strip().title()

    if not version:
        version = template.get("metadata", {}).get("version", "{{version}}")

    guideline_slug = re.sub(r"[^a-z0-9]+", "-", guideline_name.lower()).strip("-")

    # Template variables
    variables = {
        "guideline_slug": guideline_slug,
        "guideline_name": guideline_name,
        "version": version,
    }

    # Create output structure
    refs_dir = output_dir / "references"
    refs_dir.mkdir(parents=True, exist_ok=True)

    # Build cross-reference map
    code_to_file = build_code_to_file_map(chunks, entries)

    # Copy and cross-link converted chunks
    copied = 0
    for chunk in chunks:
        output_file = chunk["output_file"]
        src = chunks_dir / output_file
        dst = refs_dir / output_file

        if not src.exists():
            # Try finding by chunk_id as fallback
            alt_src = chunks_dir / f"{chunk['chunk_id']}.md"
            if alt_src.exists():
                src = alt_src
            else:
                print(f"  WARN: missing chunk file: {src.name}", file=sys.stderr)
                continue

        content = src.read_text(encoding="utf-8")
        content = resolve_cross_references(content, code_to_file)
        dst.write_text(content, encoding="utf-8")
        copied += 1

    # Group and render SKILL.md
    diseases = group_chunks_by_disease(chunks, custom_categories)
    frontmatter = render_frontmatter(template, variables)
    skill_content = render_skill_md(diseases, frontmatter, guideline_name, version)

    skill_path = output_dir / "SKILL.md"
    skill_path.write_text(skill_content, encoding="utf-8")

    # Verify completeness
    missing = verify_completeness(chunks, refs_dir)

    # Summary
    print(f"Skill package assembled: {output_dir}")
    print(f"  SKILL.md:        {skill_path}")
    print(f"  Reference files:  {copied}/{len(chunks)} copied")
    print(f"  Cross-ref codes:  {len(code_to_file)} mapped")

    if missing:
        print(f"\n  WARNING: {len(missing)} missing reference file(s):")
        for m in missing:
            print(m)
        sys.exit(1)
    else:
        print("  Completeness:     OK (all chunks present)")


def main():
    parser = argparse.ArgumentParser(
        description="Assemble converted markdown chunks into a complete NCCN skill package."
    )
    parser.add_argument(
        "--chunks-dir",
        type=Path,
        required=True,
        help="Directory containing converted .md files from Haiku workers",
    )
    parser.add_argument(
        "--toc",
        type=Path,
        required=True,
        help="Path to toc.json produced by extract_toc.py",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="Output directory for the skill package (e.g., nccn-nsclc/)",
    )
    parser.add_argument(
        "--template",
        type=Path,
        required=True,
        help="Path to the YAML frontmatter template (e.g., assets/skill-md-template.yaml)",
    )
    parser.add_argument(
        "--guideline-name",
        type=str,
        default=None,
        help="Human-readable guideline name (default: derived from source PDF name)",
    )
    parser.add_argument(
        "--version",
        type=str,
        default=None,
        help="Guideline version string (default: from template YAML)",
    )
    parser.add_argument(
        "--categories",
        type=Path,
        default=None,
        help="Optional JSON file mapping category names to keyword lists for grouping diseases",
    )
    args = parser.parse_args()

    chunks_dir = args.chunks_dir.resolve()
    toc_path = args.toc.resolve()
    output_dir = args.output_dir.resolve()
    template_path = args.template.resolve()

    if not chunks_dir.is_dir():
        print(f"Error: chunks directory not found: {chunks_dir}", file=sys.stderr)
        sys.exit(1)
    if not toc_path.exists():
        print(f"Error: toc.json not found: {toc_path}", file=sys.stderr)
        sys.exit(1)
    if not template_path.exists():
        print(f"Error: template not found: {template_path}", file=sys.stderr)
        sys.exit(1)

    assemble(
        chunks_dir=chunks_dir,
        toc_path=toc_path,
        output_dir=output_dir,
        template_path=template_path,
        guideline_name=args.guideline_name,
        version=args.version,
        categories_path=args.categories,
    )


if __name__ == "__main__":
    main()
