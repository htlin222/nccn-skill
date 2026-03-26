# Validation Pipeline

Five machine-checkable validation stages ensure the generated skill package is
free of orphan links, hallucinated content, and protocol violations.

**All five stages must pass before the skill is considered ready.**

## Stage 1: Link Integrity

**Script**: `scripts/validate_links.py`

**Checks**:
- Every `[text](path)` link in SKILL.md resolves to an existing file
- Every `[text](file.md#heading)` anchor link resolves to a real heading
- Every `.md` file in `references/` is linked from SKILL.md (no orphan files)
- Every `-evidence.md` file has a matching base algorithm file

**Failure action**: Fix broken links in SKILL.md or regenerate missing files.

## Stage 2: Citation Coverage

**Script**: `scripts/validate_citations.py`

**Checks**:
- Every `.md` file in `references/` contains `[p.XX]` page citations
- Every cited page number falls within the file's declared source page range
- No block of 3+ consecutive content lines lacks a citation (potential hallucination)
- Citation density is adequate: ≥0.1 citations per content line

**Failure action**:
- Out-of-range citations → likely hallucination, re-run the Haiku worker for that chunk
- Uncited zones → may be acceptable for structural content (headings, lists), but
  flag dense prose blocks without citations for re-processing
- Low density → re-run with stronger citation instructions in the prompt

## Stage 3: Cross-Reference Consistency

**Script**: `scripts/validate_links.py` (second pass)

**Checks**:
- Every disease listed in SKILL.md navigation has a reference file
- Every reference file linked from SKILL.md exists
- Cross-disease references within files (e.g., "See disease-subtype-a.md") resolve

**Failure action**: Update SKILL.md or regenerate the cross-reference links.

## Stage 4: Content Completeness

**Script**: `scripts/assemble_skill.py --verify-only`

**Checks**:
- Every chunk in `toc.json` has a corresponding converted file
- Every L1 disease in the source PDF has at least an algorithm reference file
- Shared sections (supportive care, response criteria) are present

**Failure action**: Re-run Haiku workers for missing chunks.

## Stage 5: Format Compliance

**Script**: `scripts/check_format.py`

**Checks**:
- `SKILL.md` exists with valid YAML frontmatter
- `name` field: ≤64 chars, lowercase alphanumeric + hyphens
- `description` field: non-empty, ≤1024 chars
- SKILL.md body: <500 lines
- Reference files >100 lines have a table of contents
- No nested references (reference files don't link to other reference files as primary content)

**Failure action**: Edit SKILL.md to fix frontmatter, trim content, or add TOC to long files.

## Anti-Hallucination Design

The citation system is the primary hallucination defense:

1. **Haiku workers** are instructed to cite `[p.XX]` on every factual claim
2. **validate_citations.py** flags any prose block without citations
3. **Page range checking** catches invented page numbers
4. **No information can exist in the output that isn't traceable to a source page**

If a Haiku worker hallucinates a treatment recommendation:
- It either omits a citation → **flagged by uncited zone check**
- Or invents a page number outside its range → **flagged by range check**
- Or invents a page number inside its range → **caught by manual spot-check in Step 6**

The third case is the hardest to catch automatically. This is why Step 6 (manual review)
includes spot-checking 3 random recommendations against the source PDF.

## Running All Validators

```bash
# Run in sequence — each must pass
python scripts/validate_links.py <skill-dir>/
python scripts/validate_citations.py <skill-dir>/
python scripts/check_format.py <skill-dir>/
```

Or run all at once and check exit codes:

```bash
python scripts/validate_links.py <skill-dir>/ && \
python scripts/validate_citations.py <skill-dir>/ && \
python scripts/check_format.py <skill-dir>/ && \
echo "ALL VALIDATIONS PASSED"
```
