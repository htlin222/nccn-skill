# Chunking Strategy

## Overview

NCCN guideline PDFs have a two-part structure:
1. **Algorithm pages** (front half): Flowchart-style clinical pathways — diagnosis, workup, staging, treatment by line
2. **Manuscript pages** (back half): Narrative discussion with literature citations and evidence

The chunking strategy splits the PDF along semantic boundaries derived from its own TOC,
producing independent chunks that can be processed in parallel.

## Boundary Detection

### Algorithm/Manuscript Boundary
The manuscript section is marked by a Level 1 TOC entry with `page=-1`, typically named
like `ms_*.pdf` (an embedded PDF bookmark). The first Level 2 child entry after this
bookmark gives the actual start page of manuscript content.

### Per-Entry Page Ranges
Each TOC entry's page range is computed as:
- `page_start`: The entry's own page number
- `page_end`: The page before the next sibling-or-higher entry starts

## Chunk Types

| Type | Section | Granularity | Description |
|---|---|---|---|
| `shared-overview` | Algorithm | L1 shared entries | Diagnosis, initial evaluation |
| `disease-algorithm` | Algorithm | L1 disease entries | One per disease subtype |
| `shared-appendix` | Algorithm | L1 shared entries | Supportive care, response criteria, treatment principles |
| `disease-manuscript` | Manuscript | L2 disease entries | One per disease discussion |
| `shared-manuscript` | Manuscript | L2 shared entries | Overview, supportive care narrative |

## Rules

1. **Never split within a disease**: A disease-algorithm chunk contains ALL algorithm pages
   for that disease (diagnosis through treatment lines through follow-up)

2. **Pair algorithm + manuscript**: Each disease gets up to two output files:
   - `{slug}.md` — from the algorithm chunk
   - `{slug}-evidence.md` — from the manuscript chunk

3. **40-page cap**: If a disease section exceeds 40 pages, split at the next Level 2
   boundary within that section.

4. **Shared sections are independent**: Supportive Care, Response Criteria, Treatment
   Principles, etc. become their own files, not duplicated per disease.

5. **Page markers**: Extracted text includes `[PAGE XX]` markers at each page boundary
   for downstream citation tracing.

## Slug Generation

- Extract NCCN code if present: `"Disease Name (CODE-1)"` → code `CODE-1`
- Generate kebab-case from the disease name: `"Disease Name"` → `disease-name`
- Algorithm output: `disease-name.md`
- Evidence output: `disease-name-evidence.md`

## Classification Heuristics

Algorithm L1 entries are classified by keyword matching against cancer-agnostic terms:

| Keywords | Type |
|---|---|
| "Diagnosis", "Initial Evaluation", "Workup" | `shared-overview` |
| "Supportive Care", "Response Criteria", "Principles of...", "Staging", "Biomarkers" | `shared-appendix` |
| Everything else in algorithm section | `disease-algorithm` |

Manuscript L2 entries:
| Keywords | Type |
|---|---|
| "Overview", "Methodology", "Supportive Care" | `shared-manuscript` |
| Disease names matching algorithm entries | `disease-manuscript` |
