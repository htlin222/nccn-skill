# Output SKILL.md Template Reference

This document describes the exact structure that `assemble_skill.py` generates for a
complete SKILL.md file. The template values come from `assets/skill-md-template.yaml`.

---

## YAML Frontmatter Format

```yaml
---
name: "nccn-{{guideline_slug}}"
description: "NCCN clinical practice guideline navigation for {{guideline_name}}. Use when a clinician needs treatment decisions, staging, workup, or evidence for {{guideline_name}} based on NCCN Guidelines version {{version}}."
metadata:
  author: "nccn-skill-generator"
  version: "{{version}}"
  source: "NCCN Clinical Practice Guidelines in Oncology"
  guideline: "{{guideline_name}}"
license: "See NCCN terms of use"
---
```

### Placeholder Variables

| Variable              | Source                        | Example (NSCLC)              | Example (Breast)          |
|-----------------------|-------------------------------|------------------------------|---------------------------|
| `{{guideline_slug}}`  | Derived from guideline name   | `non-small-cell-lung-cancer` | `breast-cancer`           |
| `{{guideline_name}}`  | From toc.json or CLI arg      | `Non-Small Cell Lung Cancer` | `Breast Cancer`           |
| `{{version}}`         | From template YAML or CLI arg | `3.2025`                     | `2.2025`                  |

---

## Navigation Section Structure

The SKILL.md body is organized into sections derived from the chunk types in `toc.json`.
By default, all disease chunks go under "Disease Subtypes". If a `--categories` JSON file
is provided, diseases are grouped under custom headings.

### Default (no --categories file)

```markdown
# NCCN Guidelines: {{guideline_name}}

> Clinical decision support derived from NCCN Clinical Practice Guidelines in
> Oncology. Version {{version}}.

## Disease Subtypes

### Disease A

- [Algorithm: Disease A](references/disease-a.md) -- Staging, workup, and treatment pathways
- [Evidence: Disease A](references/disease-a-evidence.md) -- Discussion of clinical evidence and rationale

### Disease B

- [Algorithm: Disease B](references/disease-b.md) -- Staging, workup, and treatment pathways

## Special Populations

### Elderly/Geriatric Considerations

- [Algorithm: Elderly Considerations](references/elderly-considerations.md) -- ...

## Shared Resources

### Diagnosis

- [Diagnosis](references/diagnosis.md) -- Initial evaluation and diagnostic workup

### Supportive Care

- [Supportive Care](references/supportive-care.md) -- Supportive care guidelines
```

### With --categories file

Supply a JSON file mapping category names to keyword lists:

```json
{
  "Indolent Lymphomas": ["follicular", "marginal zone", "indolent"],
  "Aggressive Lymphomas": ["mantle cell", "diffuse large", "burkitt", "high-grade"]
}
```

Custom categories appear before "Special Populations" and "Shared Resources".
Unmatched diseases fall into "Disease Subtypes".

---

## Disease Entry Format

Each disease that has both an algorithm chunk and an evidence (manuscript) chunk
produces two links:

```markdown
### Disease Title

- [Algorithm: Disease Title](references/disease-slug.md) -- Staging, workup, and treatment pathways
- [Evidence: Disease Title](references/disease-slug-evidence.md) -- Discussion of clinical evidence and rationale
```

Diseases with only an algorithm file omit the evidence line. Shared resources
(diagnosis, supportive care, appendices) get a single link with a contextual
description.

---

## Cross-Disease References

Within reference files, patterns like "See NSCLC-1" or "See BREAST-1" are detected
and converted to markdown links:

```
Before: See NSCLC-7 for treatment options.
After:  See [NSCLC-7](non-small-cell-lung-cancer.md) for treatment options.
```

The code-to-filename mapping is derived from toc.json entries that have an NCCN
page code (e.g., `NSCLC-1`, `BREAST-1`). This works for any cancer type.

---

## Citation Note

The SKILL.md ends with a standard citation note:

```markdown
---

> **Citation**: NCCN Clinical Practice Guidelines in Oncology: {{guideline_name}},
> Version {{version}}. National Comprehensive Cancer Network. Available at nccn.org.
>
> This skill references copyrighted NCCN content. Refer to nccn.org for the
> authoritative source and full terms of use.
```

---

## Complete Example

For a hypothetical "Non-Small Cell Lung Cancer" guideline:

```markdown
---
name: "nccn-non-small-cell-lung-cancer"
description: "NCCN clinical practice guideline navigation for Non-Small Cell Lung Cancer. Use when a clinician needs treatment decisions, staging, workup, or evidence for NSCLC based on NCCN Guidelines version 3.2025."
metadata:
  author: "nccn-skill-generator"
  version: "3.2025"
  source: "NCCN Clinical Practice Guidelines in Oncology"
  guideline: "Non-Small Cell Lung Cancer"
license: "See NCCN terms of use"
---

# NCCN Guidelines: Non-Small Cell Lung Cancer

> Clinical decision support derived from NCCN Clinical Practice Guidelines in
> Oncology. Version 3.2025.

## Disease Subtypes

### Adenocarcinoma

- [Algorithm: Adenocarcinoma](references/adenocarcinoma.md) -- Staging, workup, and treatment pathways
- [Evidence: Adenocarcinoma](references/adenocarcinoma-evidence.md) -- Discussion of clinical evidence and rationale

### Squamous Cell Carcinoma

- [Algorithm: Squamous Cell Carcinoma](references/squamous-cell-carcinoma.md) -- Staging, workup, and treatment pathways
- [Evidence: Squamous Cell Carcinoma](references/squamous-cell-carcinoma-evidence.md) -- Discussion of clinical evidence and rationale

## Shared Resources

### Diagnosis

- [Diagnosis](references/diagnosis.md) -- Initial evaluation and diagnostic workup

### Principles of Systemic Therapy

- [Principles of Systemic Therapy](references/systemic-therapy.md) -- Systemic therapy guidelines

### Principles of Radiation Therapy

- [Principles of Radiation Therapy](references/radiation-therapy.md) -- Radiation therapy guidelines

---

> **Citation**: NCCN Clinical Practice Guidelines in Oncology: Non-Small Cell Lung Cancer,
> Version 3.2025. National Comprehensive Cancer Network. Available at nccn.org.
>
> This skill references copyrighted NCCN content. Refer to nccn.org for the
> authoritative source and full terms of use.
```
