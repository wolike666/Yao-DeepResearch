#!/usr/bin/env python3
"""Convert `answer` content in a DeepResearch result JSON file into Markdown.

Usage:
  python scripts/json_answer_to_md.py \
      --input outputs/result_20260413_115310.json

By default, markdown files are written to:
  outputs/md_exports
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


ANSWER_TAGGED_PATTERN = re.compile(r"<answer>\s*([\s\S]*?)\s*</answer>", re.IGNORECASE)


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"Top-level JSON must be an object: {path}")
    return data


def extract_answer(data: dict[str, Any], src: Path) -> str:
    answer = data.get("answer")
    if isinstance(answer, str) and answer.strip():
        return answer.strip()

    tagged = data.get("answer_tagged")
    if isinstance(tagged, str) and tagged.strip():
        match = ANSWER_TAGGED_PATTERN.search(tagged)
        if match:
            return match.group(1).strip()

    raise ValueError(
        "No usable answer found. Expected non-empty 'answer' or '<answer>...</answer>' in 'answer_tagged': "
        f"{src}"
    )


def write_markdown(answer_text: str, input_json: Path, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{input_json.stem}.md"
    output_path.write_text(answer_text + "\n", encoding="utf-8")
    return output_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract markdown answer from a DeepResearch result JSON file."
    )
    parser.add_argument(
        "--input",
        required=True,
        help="Path to a result JSON file, e.g. outputs/result_20260413_115310.json",
    )
    parser.add_argument(
        "--out-dir",
        default="My-DeepResearch-2\outputs\md_exports",
        help="Output directory for generated markdown files (default: outputs/md_exports)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    input_path = Path(args.input).resolve()
    out_dir = Path(args.out_dir).resolve()

    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    data = load_json(input_path)
    answer_text = extract_answer(data, input_path)
    output_path = write_markdown(answer_text, input_path, out_dir)

    print(f"OK: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
