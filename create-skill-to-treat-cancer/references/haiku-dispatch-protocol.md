# Haiku Dispatch Protocol

How to orchestrate parallel Haiku agents for chunk-to-markdown conversion within the Claude Code meta-skill workflow.

---

## 1. Architecture Overview

The conversion pipeline uses a **fan-out/fan-in** pattern:

```
                         ┌─── Haiku Worker 1 ─── converted/chunk-01.md ───┐
                         │                                                 │
Orchestrator ───fan-out──┼─── Haiku Worker 2 ─── converted/chunk-02.md ───┼──fan-in──► Assembly
  (Opus/Sonnet)          │                                                 │
                         └─── Haiku Worker N ─── converted/chunk-NN.md ───┘
```

- The **orchestrator** (Opus or Sonnet running in Claude Code) reads `toc.json`, dispatches one Haiku worker per chunk, and collects results.
- Each **worker** processes exactly one chunk independently -- it reads a `.txt` file and writes a `.md` file.
- Workers have no awareness of each other; all coordination happens in the orchestrator.

---

## 2. Dispatch Method: Claude Code Task Agents

The primary dispatch mechanism is the Claude Code **Agent tool** with `model: "haiku"`.

### Dispatch Loop (Pseudocode)

```python
# Read the table of contents
toc = read_json("toc.json")

for chunk in toc["chunks"]:
    Agent(
        model="haiku",
        subagent_type="general-purpose",
        prompt=assemble_prompt(chunk),   # see Section 4
        run_in_background=True
    )
```

### Key Parameters

| Parameter          | Value               | Reason                                      |
| ------------------ | ------------------- | ------------------------------------------- |
| `model`            | `"haiku"`           | Fast and cheap; sufficient for structured conversion |
| `subagent_type`    | `"general-purpose"` | Needs file read/write access                |
| `run_in_background`| `true`              | Enables parallel execution                  |

### What Each Worker Does

1. Reads the chunk file at `chunks/{chunk_id}.txt`
2. Applies the conversion prompt (algorithm or manuscript template)
3. Writes the result to `converted/{output_file}`

Launch **all** chunks in a single message by issuing multiple Agent tool calls simultaneously. This maximizes parallelism.

---

## 3. Concurrency Rules

Claude Code supports a maximum of **15 concurrent background agents**.

### Single Wave (chunks <= 15)

If the guideline has 15 or fewer chunks, launch them all at once:

```
Message 1: Launch Agent(chunk_1), Agent(chunk_2), ..., Agent(chunk_15)
           → wait for all to complete
           → verify outputs (Section 5)
```

### Multiple Waves (chunks > 15)

Batch into waves of 15:

```
Wave 1: Launch Agent(chunk_1)  ... Agent(chunk_15)  → wait → verify
Wave 2: Launch Agent(chunk_16) ... Agent(chunk_30)  → wait → verify
Wave 3: Launch Agent(chunk_31) ... Agent(chunk_N)   → wait → verify
```

Do not start Wave N+1 until all workers in Wave N have completed and passed quality checks. This prevents resource contention and makes error handling simpler.

---

## 4. Prompt Assembly

For each chunk, the orchestrator assembles a complete prompt before dispatching. Follow these steps in order.

### Step 1: Read the Chunk File

```python
chunk_text = read_file(f"chunks/{chunk['chunk_id']}.txt")
```

### Step 2: Extract Metadata from YAML Header

Each chunk file begins with a YAML front-matter block:

```yaml
---
chunk_id: disease-a-algorithm
title: "Disease Subtype A"
page_range: "12-15"
output_file: "disease-subtype-a.md"
type: algorithm   # or "manuscript"
---
```

Parse these fields: `chunk_id`, `title`, `page_range`, `output_file`, `type`.

### Step 3: Select the Prompt Template

Based on the `type` field, choose from `conversion-prompts.md`:

| `type`       | Template                        |
| ------------ | ------------------------------- |
| `algorithm`  | Template 1: Algorithm to Reference |
| `manuscript` | Template 2: Manuscript to Evidence |

### Step 4: Fill Placeholders

Replace these tokens in the selected template:

| Placeholder            | Source                              |
| ---------------------- | ----------------------------------- |
| `{{disease_name}}`     | Top-level field in `toc.json`       |
| `{{guideline_version}}`| Top-level field in `toc.json`       |
| `{{page_range}}`       | Chunk metadata `page_range`         |
| `{{chunk_id}}`         | Chunk metadata `chunk_id`           |

### Step 5: Append the Source Material

Concatenate the filled template with the chunk text:

```
<filled_prompt_template>

---

SOURCE MATERIAL (from pages {{page_range}}):

<chunk_text>
```

The final assembled string is the `prompt` argument passed to the Agent tool.

---

## 5. Output Collection

Each Haiku worker writes its output to:

```
converted/{output_file}
```

For example, a chunk with `output_file: "foll-first-line-therapy.md"` produces `converted/foll-first-line-therapy.md`.

After every worker in a wave completes, the orchestrator must **verify each output file exists**:

```python
for chunk in wave_chunks:
    path = f"converted/{chunk['output_file']}"
    assert file_exists(path), f"Missing output for {chunk['chunk_id']}"
```

---

## 6. Error Handling

### Retry Policy

| Failure                        | Action                                          |
| ------------------------------ | ------------------------------------------------ |
| No output file produced        | Retry the worker up to **2 times**               |
| Output missing `[p.XX]` citations | Flag for manual review; do **not** block the pipeline |
| Output exceeds 1000 lines      | Split into sub-sections (rare; log a warning)    |
| Worker timeout                 | Treat as failure; retry                          |

### Retry Implementation

```python
MAX_RETRIES = 2

for chunk in failed_chunks:
    for attempt in range(MAX_RETRIES):
        re_dispatch(chunk)
        if output_exists(chunk):
            break
    else:
        report_failure(chunk)
```

### Conversion Report

Track all outcomes in `conversion-report.json`:

```json
{
  "guideline": "example-cancer-guideline",
  "version": "2.2026",
  "timestamp": "2026-03-26T14:30:00Z",
  "total_chunks": 22,
  "succeeded": 21,
  "failed": 1,
  "flagged_for_review": 2,
  "chunks": [
    {
      "chunk_id": "FOLL-3",
      "status": "success",
      "output_file": "converted/foll-first-line-therapy.md",
      "retries": 0,
      "quality_checks": {
        "file_exists": true,
        "has_citations": true,
        "starts_with_heading": true,
        "no_placeholders": true
      }
    },
    {
      "chunk_id": "FOLL-7",
      "status": "flagged",
      "output_file": "converted/foll-relapsed-therapy.md",
      "retries": 0,
      "quality_checks": {
        "file_exists": true,
        "has_citations": false,
        "starts_with_heading": true,
        "no_placeholders": true
      },
      "flag_reason": "No [p.XX] citations found"
    }
  ]
}
```

---

## 7. Quality Checks (Per Worker)

Run these four checks immediately after each worker completes. All checks must pass for a chunk to be marked `"success"`.

### Check 1: File Exists and Non-Empty

```python
path = f"converted/{chunk['output_file']}"
assert file_exists(path) and file_size(path) > 0
```

### Check 2: Contains Page Citations

```python
content = read_file(path)
assert "[p." in content  # at least one citation
```

If this fails, the chunk is **flagged for manual review** but does not block the pipeline.

### Check 3: Starts with a Markdown Heading

```python
first_line = content.strip().split("\n")[0]
assert first_line.startswith("#")
```

### Check 4: No Remaining Placeholders

```python
assert "{{" not in content
```

If `{{` appears in the output, the prompt was not fully assembled -- this is an orchestrator bug, not a worker bug.

### Orchestrator Action Summary

| Check Result          | Action                                  |
| --------------------- | --------------------------------------- |
| All 4 pass            | Mark `success`                          |
| Check 1 fails         | Retry (up to 2 times)                   |
| Check 2 fails only    | Mark `flagged`, continue                |
| Check 3 or 4 fails    | Retry (likely prompt assembly error)    |

---

## 8. Alternative Method: Anthropic Batch API

For running the conversion pipeline outside Claude Code (e.g., in a standalone Python script), use the Anthropic Python SDK's message batches API.

### Setup

```bash
uv pip install anthropic
```

### Submit a Batch

```python
import anthropic
import json

client = anthropic.Anthropic()

# Build requests -- one per chunk
requests = []
for chunk in toc["chunks"]:
    requests.append({
        "custom_id": chunk["chunk_id"],
        "params": {
            "model": "claude-haiku-4-20250414",
            "max_tokens": 8192,
            "messages": [
                {"role": "user", "content": assemble_prompt(chunk)}
            ]
        }
    })

# Submit
batch = client.messages.batches.create(requests=requests)
print(f"Batch ID: {batch.id}")
```

### Poll and Collect Results

```python
import time

while True:
    status = client.messages.batches.retrieve(batch.id)
    if status.processing_status == "ended":
        break
    time.sleep(30)

# Stream results
for result in client.messages.batches.results(batch.id):
    chunk_id = result.custom_id
    output = result.result.message.content[0].text
    output_file = chunk_map[chunk_id]["output_file"]
    write_file(f"converted/{output_file}", output)
```

This method is useful for bulk processing or CI pipelines where Claude Code is not available. The same prompt assembly logic (Section 4) and quality checks (Section 7) apply.
