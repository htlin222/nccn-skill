#!/usr/bin/env python3
"""Quality gate: check converted files and identify those needing retry.

Checks each converted .md file for:
1. Existence and non-empty
2. Starts with markdown heading
3. Citation density above threshold
4. Output-to-input ratio above threshold

Outputs a JSON list of chunk IDs that failed and need re-processing.

Usage:
    python quality_gate.py --converted-dir converted/ --chunks-dir chunks/ [--min-density 0.05] [--min-ratio 1.5]
"""

import argparse
import json
import re
import sys
from pathlib import Path


def check_file(converted_path: Path, chunk_path: Path, min_density: float, min_ratio: float) -> dict:
    result = {"file": converted_path.name, "passed": True, "issues": []}

    if not converted_path.exists():
        result["passed"] = False
        result["issues"].append("file missing")
        return result

    text = converted_path.read_text(encoding="utf-8")
    lines = text.splitlines()

    if len(lines) < 3:
        result["passed"] = False
        result["issues"].append(f"too short ({len(lines)} lines)")
        return result

    if not lines[0].startswith("#"):
        result["issues"].append("missing heading")

    # Citation density
    content_lines = [l for l in lines if l.strip() and not l.startswith("#") and not l.startswith("<!--")]
    citations = len(re.findall(r"\[p\.\d+\]", text))
    density = citations / max(len(content_lines), 1)
    result["citations"] = citations
    result["density"] = round(density, 3)
    result["lines"] = len(lines)

    if density < min_density:
        result["passed"] = False
        result["issues"].append(f"low citation density ({density:.3f} < {min_density})")

    # Output-to-input ratio
    if chunk_path.exists():
        input_chars = len(chunk_path.read_text(encoding="utf-8"))
        output_lines = len(lines)
        ratio = output_lines / (input_chars / 1000)
        result["ratio"] = round(ratio, 2)

        if ratio < min_ratio:
            result["passed"] = False
            result["issues"].append(f"low output ratio ({ratio:.1f} < {min_ratio})")

    return result


def main():
    parser = argparse.ArgumentParser(description="Quality gate for converted markdown files.")
    parser.add_argument("--converted-dir", type=Path, required=True)
    parser.add_argument("--chunks-dir", type=Path, required=True)
    parser.add_argument("--min-density", type=float, default=0.05)
    parser.add_argument("--min-ratio", type=float, default=1.5)
    parser.add_argument("--output", type=Path, default=None, help="Write retry list to JSON")
    args = parser.parse_args()

    converted_dir = args.converted_dir.resolve()
    chunks_dir = args.chunks_dir.resolve()

    # Build mapping from output file to chunk file
    manifest_path = chunks_dir / "chunks-manifest.json"
    if manifest_path.exists():
        with open(manifest_path) as f:
            manifest = json.load(f)
    else:
        manifest = []

    results = []
    retry_ids = []

    for md_file in sorted(converted_dir.glob("*.md")):
        # Find matching chunk file
        chunk_id = md_file.stem
        chunk_path = chunks_dir / f"{chunk_id}.txt"

        result = check_file(md_file, chunk_path, args.min_density, args.min_ratio)
        results.append(result)

        if not result["passed"]:
            retry_ids.append(chunk_id)

    # Summary
    passed = sum(1 for r in results if r["passed"])
    failed = len(results) - passed

    print(f"Quality Gate Results")
    print(f"{'=' * 60}")
    print(f"Files checked: {len(results)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")

    if failed > 0:
        print(f"\nFiles needing retry:")
        for r in results:
            if not r["passed"]:
                issues = ", ".join(r["issues"])
                print(f"  ✗ {r['file']}: {issues}")

    if args.output and retry_ids:
        with open(args.output, "w") as f:
            json.dump(retry_ids, f, indent=2)
        print(f"\nRetry list written to: {args.output}")

    sys.exit(1 if failed > 0 else 0)


if __name__ == "__main__":
    main()
