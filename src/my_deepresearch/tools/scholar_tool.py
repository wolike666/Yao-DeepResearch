from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import requests
from dotenv import load_dotenv


def _load_shared_env() -> None:
    # 先加载当前项目 .env，再尝试加载同级 Alibaba 项目 .env（只补齐缺失变量）。
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


def _apply_source_policy(results: list[dict], source_policy: str) -> list[dict]:
    if source_policy != "strict":
        return results
    # scholar 结果天然属于 academic，严格模式仍保留。
    return results


def _normalize_scholar_item(item: dict) -> dict:
    url = (item.get("pdfUrl") or item.get("link") or "").strip()
    domain = urlparse(url).netloc.lower()
    publication = (item.get("publicationInfo") or "").strip()
    cited_by = item.get("citedBy", 0)
    year = item.get("year", "")

    snippet = (item.get("snippet") or "").strip()
    extra = []
    if publication:
        extra.append(f"publicationInfo: {publication}")
    if year:
        extra.append(f"year: {year}")
    if cited_by:
        extra.append(f"citedBy: {cited_by}")
    if extra:
        suffix = " | ".join(extra)
        snippet = f"{snippet} ({suffix})" if snippet else suffix

    return {
        "title": (item.get("title") or "").strip(),
        "url": url,
        "snippet": snippet,
        "domain": domain,
        "source_tier": "academic",
        "access_time": datetime.now().isoformat(timespec="seconds"),
        "relevance_score": 0.7,
        "citedBy": cited_by,
        "year": year,
    }


def _search_with_serper_scholar(query: str, max_results: int) -> list[dict]:
    key = os.getenv("SERPER_KEY_ID", "").strip().strip("\"'")
    if not key:
        return []

    headers = {
        "X-API-KEY": key,
        "Content-Type": "application/json",
    }
    payload = {"q": query}

    resp = requests.post(
        "https://google.serper.dev/scholar",
        json=payload,
        headers=headers,
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()

    organic = data.get("organic") or []
    out: list[dict] = []
    for item in organic[:max_results]:
        normalized = _normalize_scholar_item(item)
        if normalized["url"]:
            out.append(normalized)
    return out


def search_scholar(query: str, max_results: int = 5, source_policy: str = "balanced") -> list[dict]:
    try:
        results = _search_with_serper_scholar(query, max_results=max_results)
    except Exception:
        results = []
    return _apply_source_policy(results, source_policy)
