from __future__ import annotations

import argparse
import json
import os
from datetime import datetime
from pathlib import Path

from src.my_deepresearch.config import load_settings
from src.my_deepresearch.engine import run_research


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Minimal DeepResearch loop")
    parser.add_argument("--question", type=str, default="", help="Research question")
    parser.add_argument(
        "--max-steps",
        type=int,
        default=None,
        help="Explicit max steps override (default: use COST_MODE/MAX_STEPS from config)",
    )
    parser.add_argument(
        "--cost-mode",
        type=str,
        default="standard",
        choices=["low", "standard", "high"],
        help="Cost profile override: low|standard|high",
    )
    parser.add_argument(
        "--search-mode",
        type=str,
        default="hybrid",
        choices=["web", "scholar", "hybrid"],
        help="Search mode override: web|scholar|hybrid",
    )
    parser.add_argument(
        "--source-policy",
        type=str,
        default="balanced",
        choices=["balanced", "strict"],
        help="Source tier policy override: balanced|strict",
    )
    parser.add_argument(
        "--max-scholar-results",
        type=int,
        default=0,
        help="Override max scholar results when scholar/hybrid mode is active",
    )
    parser.add_argument("--quiet", action="store_true", help="Disable verbose logs")
    parser.add_argument(
        "--save-dir",
        type=str,
        default="outputs",
        help="Directory for result JSON",
    )
    return parser


def main() -> None:
    parser = build_arg_parser()
    args = parser.parse_args()

    question = args.question.strip()
    if not question:
        question = input("请输入研究问题: ").strip()

    os.environ["COST_MODE"] = args.cost_mode
    settings = load_settings()
    if args.max_steps is not None and args.max_steps > 0:
        settings.max_steps = args.max_steps
    if args.search_mode:
        settings.search_mode = args.search_mode
    if args.source_policy:
        settings.source_policy = args.source_policy
    if args.max_scholar_results > 0:
        settings.max_scholar_results = args.max_scholar_results

    result = run_research(question, settings=settings, verbose=not args.quiet)

    save_dir = Path(args.save_dir)
    save_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    file_path = save_dir / f"result_{ts}.json"
    file_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n===== Final Answer =====")
    print(result["answer"])
    print(f"\nSaved to: {file_path}")


if __name__ == "__main__":
    main()
