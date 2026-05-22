from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


def _load_shared_env() -> None:
    # Load local env first, then sibling Alibaba env without overriding local values.
    load_dotenv(override=False)

    env_path = os.getenv("ALIBABA_ENV_PATH", "").strip()
    if env_path:
        load_dotenv(env_path, override=False)
        return

    project_root = Path(__file__).resolve().parents[3]
    sibling_env = project_root.parent / "Alibaba-NLP-DeepResearch" / ".env"
    if sibling_env.exists():
        load_dotenv(str(sibling_env), override=False)


_load_shared_env()


@dataclass
class Settings:
    openai_api_key: str
    openai_base_url: str
    openai_model: str
    max_steps: int
    max_search_results: int
    max_page_chars: int
    search_mode: str
    source_policy: str
    max_scholar_results: int
    cost_mode: str


def _read_int(name: str, default: int) -> int:
    raw = os.getenv(name, str(default)).strip()
    try:
        return int(raw)
    except ValueError:
        return default


def _read_choice(name: str, default: str, choices: tuple[str, ...]) -> str:
    raw = os.getenv(name, default).strip().lower()
    if raw in choices:
        return raw
    return default


def _read_first_non_empty(names: tuple[str, ...], default: str = "") -> str:
    for name in names:
        value = os.getenv(name, "").strip()
        if value:
            return value
    return default


def _profile_defaults(cost_mode: str) -> dict[str, int]:
    # Cost profiles:
    # low: cheap/fast; standard: balanced; high: better quality at higher cost.
    table = {
        "low": {
            "max_steps": 3,
            "max_search_results": 3,
            "max_page_chars": 5000,
            "max_scholar_results": 3,
        },
        "standard": {
            "max_steps": 5,
            "max_search_results": 5,
            "max_page_chars": 8000,
            "max_scholar_results": 5,
        },
        "high": {
            "max_steps": 8,
            "max_search_results": 8,
            "max_page_chars": 12000,
            "max_scholar_results": 8,
        },
    }
    return table.get(cost_mode, table["standard"])


def load_settings() -> Settings:
    cost_mode = _read_choice("COST_MODE", "standard", ("low", "standard", "high"))
    defaults = _profile_defaults(cost_mode)

    return Settings(
        openai_api_key=_read_first_non_empty(("OPENAI_API_KEY", "API_KEY")),
        openai_base_url=_read_first_non_empty(
            ("OPENAI_BASE_URL", "API_BASE", "INFER_API_BASE"),
            default="https://api.openai.com/v1",
        ),
        openai_model=_read_first_non_empty(
            ("OPENAI_MODEL", "INFER_MODEL_NAME", "MODEL_PATH"),
            default="qwen-plus-latest",
        ),
        max_steps=_read_int("MAX_STEPS", defaults["max_steps"]),
        max_search_results=_read_int("MAX_SEARCH_RESULTS", defaults["max_search_results"]),
        max_page_chars=_read_int("MAX_PAGE_CHARS", defaults["max_page_chars"]),
        search_mode=_read_choice("SEARCH_MODE", "hybrid", ("web", "scholar", "hybrid")),
        source_policy=_read_choice("SOURCE_POLICY", "balanced", ("balanced", "strict")),
        max_scholar_results=_read_int("MAX_SCHOLAR_RESULTS", defaults["max_scholar_results"]),
        cost_mode=cost_mode,
    )
