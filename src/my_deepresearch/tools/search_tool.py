from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import requests
from dotenv import load_dotenv

try:
    from ddgs import DDGS
except ImportError:  # pragma: no cover - fallback for older environments
    from duckduckgo_search import DDGS


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


def _infer_source_tier(domain: str) -> str:
    # 规则化信源分层：官方/学术优先，新闻其次，社区与其他降权。
    text = (domain or "").lower()
    if not text:
        return "general"
    if text.endswith((".gov", ".gov.cn", ".edu", ".edu.cn", ".ac", ".ac.cn")):
        return "official"
    if any(token in text for token in ["arxiv", "acm", "ieee", "nature", "science", "springer", "acl"]):
        return "academic"
    if any(token in text for token in ["news", "xinhuanet", "reuters", "bbc", "nytimes"]):
        return "news"
    if any(token in text for token in ["reddit", "medium", "youtube", "bilibili"]):
        return "community"
    return "general"


def _normalize_result(title: str, url: str, snippet: str) -> dict:
    domain = urlparse(url).netloc.lower()
    return {
        "title": title,
        "url": url,
        "snippet": snippet,
        "domain": domain,
        "source_tier": _infer_source_tier(domain),
        "access_time": datetime.now().isoformat(timespec="seconds"),
        "relevance_score": 0.5,
    }


def _apply_source_policy(results: list[dict], source_policy: str) -> list[dict]:
    if source_policy != "strict":
        return results
    allowed = {"official", "academic", "news"}
    filtered = [item for item in results if (item.get("source_tier") or "general") in allowed]
    return filtered if filtered else results


def _search_with_serper(query: str, max_results: int) -> list[dict]:
    # 调用 Serper 搜索接口，返回统一结构的 title/url/snippet 列表。
    key = os.getenv("SERPER_KEY_ID", "").strip().strip("\"'")
    if not key:
        return []

    headers = {
        "X-API-KEY": key,
        "Content-Type": "application/json",
    }
    payload = {"q": query}

    resp = requests.post(
        "https://google.serper.dev/search",
        json=payload,
        headers=headers,
        timeout=20,
    )
    resp.raise_for_status()

    data = resp.json()
    organic = data.get("organic") or []

    results: list[dict] = []
    for item in organic[:max_results]:
        results.append(
            _normalize_result(
                title=item.get("title", ""),
                url=item.get("link", ""),
                snippet=item.get("snippet", ""),
            )
        )
    return results


def _search_with_ddgs(query: str, max_results: int) -> list[dict]:
    # DDGS 回退实现：在 Serper 不可用时维持搜索能力。
    results: list[dict] = []
    with DDGS() as ddgs:
        for item in ddgs.text(query, max_results=max_results):
            results.append(
                _normalize_result(
                    title=item.get("title", ""),
                    url=item.get("href", ""),
                    snippet=item.get("body", ""),
                )
            )
    return results


def search_web(query: str, max_results: int = 5, source_policy: str = "balanced") -> list[dict]:
    # 优先复用 Alibaba 配置的 Serper 搜索，失败后回退 DDGS。
    try:
        serper_results = _search_with_serper(query, max_results=max_results)
        if serper_results:
            return _apply_source_policy(serper_results, source_policy)
    except Exception:
        pass

    ddgs_results = _search_with_ddgs(query, max_results=max_results)
    return _apply_source_policy(ddgs_results, source_policy)
