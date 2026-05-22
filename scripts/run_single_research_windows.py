from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


from src.my_deepresearch.config import load_settings
from src.my_deepresearch.engine import run_research


def _pick_question(args_question: str, settings_question: str) -> str:
    question = (args_question or "").strip()
    if question:
        return question
    fallback = (settings_question or "").strip()
    if fallback:
        return fallback
    return input("请输入研究问题: ").strip()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a single DeepResearch question on Windows")
    parser.add_argument("--question", default=os.getenv("QUESTION", ""), help="single research question")
    parser.add_argument(
        "--max-steps",
        type=int,
        default=None,
        help="Explicit max steps override (default: use COST_MODE/MAX_STEPS from config)",
    )
    parser.add_argument(
        "--cost-mode",
        default=os.getenv("COST_MODE", "standard"),
        choices=["low", "standard", "high"],
        help="Cost profile: low(cheap), standard(balanced), high(better quality)",
    )
    parser.add_argument(
        "--search-mode",
        default=os.getenv("SEARCH_MODE", "hybrid"),
        choices=["web", "scholar", "hybrid"],
    )
    parser.add_argument(
        "--source-policy",
        default=os.getenv("SOURCE_POLICY", "balanced"),
        choices=["balanced", "strict"],
    )
    parser.add_argument(
        "--save-dir",
        default=os.getenv("OUTPUT_PATH", "outputs"),
        help="directory for result json",
    )
    parser.add_argument("--quiet", action="store_true", help="disable step logs")
    return parser


def main() -> None:
    env_file = REPO_ROOT / ".env"
    if env_file.exists():
        load_dotenv(env_file, override=False)

    parser = build_parser()
    args = parser.parse_args()

    # Apply CLI cost profile first so config defaults follow this profile.
    os.environ["COST_MODE"] = args.cost_mode

    settings = load_settings()
    if args.max_steps is not None and args.max_steps > 0:
        settings.max_steps = args.max_steps
    settings.search_mode = args.search_mode
    settings.source_policy = args.source_policy

    question = _pick_question(args.question, os.getenv("QUESTION", ""))
    if not question:
        raise ValueError("question is empty")

    result = run_research(question, settings=settings, verbose=not args.quiet)

    save_dir = Path(args.save_dir)
    save_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    result_path = save_dir / f"result_{ts}.json"
    result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n===== Final Answer =====")
    print(result.get("answer", ""))
    print(f"\nSaved to: {result_path}")


if __name__ == "__main__":
    main()
