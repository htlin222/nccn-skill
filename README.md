# create-skill-to-treat-cancer

A meta-skill that converts NCCN Clinical Practice Guideline PDFs into structured AI skill packages following the [Vercel Skills protocol](https://github.com/vercel-labs/skills).

**English** | [繁體中文](README.zh-TW.md)

## Disclaimer

> **This project is for research and testing purposes only.**
>
> The generated skill packages are **not intended as a replacement for official NCCN Clinical Practice Guidelines**. They are derived from NCCN content through automated extraction and AI-assisted conversion, which may introduce errors, omissions, or misrepresentations.
>
> - **For licensed healthcare professionals only.** This tool is designed to assist clinicians who are already familiar with NCCN guidelines. It should not be used by patients or non-medical personnel for clinical decision-making.
> - **Use with caution.** Always verify treatment recommendations against the original NCCN guideline PDF and current institutional protocols before making clinical decisions.
> - **Not a medical device.** This software has not been validated for clinical use and does not constitute medical advice.
> - **NCCN content is copyrighted.** Users are responsible for ensuring compliance with NCCN's terms of use. The source PDFs are not included in this repository.

## Overview

NCCN guideline PDFs are 300+ page documents covering cancer diagnosis, staging, treatment by line, supportive care, and evidence discussion. This project provides a pipeline to convert them into modular, navigable AI skill packages with progressive disclosure:

```
PDF (357 pages) → TOC extraction → Semantic chunking → Parallel Haiku conversion → Merge → Validate → Skill Package
```

**Output example** (B-Cell Lymphomas v3.2025):
- 34 reference files covering 15+ disease subtypes
- 8,592 lines of structured clinical content
- 3,479 page citations (`[p.XX]`) traceable to the source PDF
- Progressive disclosure: SKILL.md (147 lines) → disease algorithm → evidence summary

## Architecture

```
create-skill-to-treat-cancer/     # The meta-skill (cancer-agnostic)
├── SKILL.md                      # 6-step orchestration workflow
├── scripts/                      # Pipeline scripts (Python + PyMuPDF)
│   ├── extract_toc.py            # PDF TOC → toc.json
│   ├── chunk_pdf.py              # Semantic chunking with auto-split (--max-chars)
│   ├── merge_parts.py            # Merge multi-part converted files
│   ├── assemble_skill.py         # Generate SKILL.md + organize references/
│   ├── quality_gate.py           # Identify low-quality outputs for retry
│   ├── validate_links.py         # Anti-orphan: link integrity checks
│   ├── validate_citations.py     # Anti-hallucination: [p.XX] coverage
│   └── check_format.py           # Vercel Skills protocol compliance
├── references/                   # Conversion prompts, dispatch protocol, docs
└── assets/                       # Templates and example category files

nccn-cancer-skill/                # Generated skill packages (committed)
├── b-cell-lymphomas/             # 34 reference files, 8,592 lines, 3,479 citations
└── breast-cancer/                # 24 reference files, 4,008 lines, 1,866 citations

tmp/                              # Intermediate pipeline artifacts (gitignored)
└── <cancer-name>/                # toc.json, chunks/, converted/, merged/
```

## Quick Start

```bash
# Prerequisites
python3 -m venv .venv && source .venv/bin/activate
pip install pymupdf pyyaml

# Step 1-2: Extract and chunk
CANCER=breast-cancer  # change to your cancer type
mkdir -p tmp/${CANCER}

python create-skill-to-treat-cancer/scripts/extract_toc.py path/to/nccn.pdf --output tmp/${CANCER}/toc.json
python create-skill-to-treat-cancer/scripts/chunk_pdf.py path/to/nccn.pdf \
  --toc tmp/${CANCER}/toc.json --output-dir tmp/${CANCER}/chunks --max-chars 50000

# Step 3: Convert chunks via Haiku (see references/haiku-dispatch-protocol.md)
# Step 4: Merge and assemble
python create-skill-to-treat-cancer/scripts/merge_parts.py \
  --input-dir tmp/${CANCER}/converted --output-dir tmp/${CANCER}/merged
python create-skill-to-treat-cancer/scripts/assemble_skill.py \
  --chunks-dir tmp/${CANCER}/merged --toc tmp/${CANCER}/toc.json \
  --output-dir nccn-cancer-skill/${CANCER} \
  --template create-skill-to-treat-cancer/assets/skill-md-template.yaml \
  --guideline-name "<Guideline Name>" --version "<version>"

# Step 5: Validate
python create-skill-to-treat-cancer/scripts/validate_links.py nccn-cancer-skill/${CANCER}/
python create-skill-to-treat-cancer/scripts/validate_citations.py nccn-cancer-skill/${CANCER}/
python create-skill-to-treat-cancer/scripts/check_format.py nccn-cancer-skill/${CANCER}/
```

## Anti-Hallucination Design

Every factual claim in the generated skill must carry a `[p.XX]` page citation traceable to the source PDF. The pipeline enforces this through:

1. **`[PAGE XX]` markers** embedded during text extraction
2. **Haiku prompt instructions** requiring citations on every drug, dose, category, and recommendation
3. **`validate_citations.py`** flagging uncited zones and out-of-range page numbers
4. **`quality_gate.py`** identifying files below citation density thresholds for auto-retry
5. **Chunk splitting** (`--max-chars 50000`) preventing Haiku from truncating large inputs

## Citation

If you use this software in your research, please cite:

### AMA (American Medical Association) Style

Lin HT. create-skill-to-treat-cancer: NCCN Guideline PDF to AI Skill Package Converter. Published 2026. Accessed March 26, 2026. https://github.com/htlin222/nccn-skill

### BibTeX

```bibtex
@software{lin2026nccnskill,
  author       = {Lin, Hsieh-Ting},
  title        = {create-skill-to-treat-cancer: {NCCN} Guideline {PDF} to {AI} Skill Package Converter},
  year         = {2026},
  url          = {https://github.com/htlin222/nccn-skill},
  version      = {1.0.0},
  license      = {Apache-2.0}
}
```

### CITATION.cff

A machine-readable `CITATION.cff` file is included in the repository root.

## License

Apache-2.0. See [LICENSE](LICENSE) for details.

NCCN Clinical Practice Guidelines in Oncology are copyrighted by the National Comprehensive Cancer Network. This project does not include or redistribute NCCN content. Users must obtain their own licensed copies of NCCN guidelines.
