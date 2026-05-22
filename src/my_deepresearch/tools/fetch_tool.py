from __future__ import annotations

import os
import re
from pathlib import Path
from urllib.parse import urlsplit

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

from .pdf_tool import extract_pdf_text, extract_pdf_title


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}

MOBILE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Linux; Android 13; Pixel 7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Mobile Safari/537.36"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}


def _load_shared_env() -> None:
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


def _is_error_like_text(text: str) -> bool:
    content = (text or "").strip()
    if not content:
        return True
    lowered = content.lower()
    markers = [
        "404",
        "not found",
        "error code",
        "target url returned error",
        "系统错误",
        "页面不存在",
    ]
    return any(m in lowered or m in content for m in markers)


def _fetch_via_jina(url: str, max_chars: int) -> str:
    key = os.getenv("JINA_API_KEYS", "").strip().strip("\"'")
    if not key:
        return ""

    jina_url = f"https://r.jina.ai/{url}"
    headers = {"Authorization": f"Bearer {key}"}
    resp = requests.get(jina_url, headers=headers, timeout=30)
    resp.raise_for_status()

    text = (resp.text or "").strip()
    if _is_error_like_text(text):
        return ""
    return text[:max_chars]


def _extract_title_from_jina_text(text: str) -> str:
    if not text:
        return ""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    for ln in lines[:20]:
        low = ln.lower()
        if low.startswith("title:"):
            title = ln.split(":", 1)[1].strip()
            if title:
                return title[:160]
    for ln in lines[:20]:
        if len(ln) >= 4:
            return ln[:160]
    return ""


def _looks_like_pdf_url(url: str) -> bool:
    try:
        path = urlsplit(url).path.lower()
    except Exception:
        path = (url or "").lower()
    return path.endswith(".pdf")


def _fetch_pdf_direct(url: str, max_chars: int) -> tuple[str, str]:
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    text = extract_pdf_text(resp.content, max_chars=max_chars)
    if not text:
        raise ValueError("PDF text extraction returned empty")
    title = extract_pdf_title(resp.content)
    return text, title


def _clean_title(title: str) -> str:
    text = (title or "").strip()
    text = re.sub(r"\s+", " ", text)
    return text[:200]


def _fetch_via_requests_bs4(url: str, max_chars: int) -> tuple[str, str]:
    resp = requests.get(url, headers=HEADERS, timeout=20)
    resp.raise_for_status()

    content_type = (resp.headers.get("Content-Type") or "").lower()
    if "application/pdf" in content_type:
        text = extract_pdf_text(resp.content, max_chars=max_chars)
        if text:
            return text, extract_pdf_title(resp.content)
        raise ValueError("PDF fetched but text extraction returned empty")

    soup = BeautifulSoup(resp.text, "html.parser")
    page_title = ""
    if soup.title and soup.title.string:
        page_title = _clean_title(soup.title.string)
    for tag in soup(["script", "style", "noscript"]):
        tag.extract()

    text = "\n".join(line.strip() for line in soup.get_text("\n").splitlines() if line.strip())
    return text[:max_chars], page_title


def _build_zhihu_candidates(url: str) -> list[str]:
    u = (url or "").strip()
    out: list[str] = []
    if not u:
        return out
    out.append(u)
    if "zhuanlan.zhihu.com/p/" in u:
        # Mobile page is sometimes less strict than desktop anti-bot.
        out.append(u.replace("https://zhuanlan.zhihu.com/p/", "https://zhuanlan.zhihu.com/p/", 1) + "?utm_psn=1")
    return out


def _is_zhihu_url(url: str) -> bool:
    host = (urlsplit(url).netloc or "").lower()
    return host.endswith("zhihu.com")


def _fetch_zhihu_with_mobile_headers(url: str, max_chars: int) -> tuple[str, str]:
    resp = requests.get(url, headers=MOBILE_HEADERS, timeout=25, allow_redirects=True)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    title = ""
    if soup.title and soup.title.string:
        title = _clean_title(soup.title.string)
    for tag in soup(["script", "style", "noscript"]):
        tag.extract()
    text = "\n".join(line.strip() for line in soup.get_text("\n").splitlines() if line.strip())
    return text[:max_chars], title


def _get_wayback_snapshot_url(url: str) -> str:
    cdx_api = "https://web.archive.org/cdx/search/cdx"
    params = {
        "url": url,
        "output": "json",
        "fl": "timestamp,original,statuscode",
        "filter": "statuscode:200",
        "limit": "1",
        "from": "2010",
        "to": "2030",
        "sort": "reverse",
        "collapse": "digest",
    }
    resp = requests.get(cdx_api, params=params, timeout=20)
    resp.raise_for_status()
    data = resp.json()
    if not isinstance(data, list) or len(data) < 2:
        return ""
    row = data[1]
    if not isinstance(row, list) or len(row) < 2:
        return ""
    ts, original = row[0], row[1]
    if not ts or not original:
        return ""
    return f"https://web.archive.org/web/{ts}id_/{original}"


def _fetch_via_wayback(url: str, max_chars: int) -> tuple[str, str]:
    try:
        snapshot_url = _get_wayback_snapshot_url(url)
    except Exception:
        return "", ""
    if not snapshot_url:
        return "", ""
    if _looks_like_pdf_url(snapshot_url):
        try:
            return _fetch_pdf_direct(snapshot_url, max_chars=max_chars)
        except Exception:
            pass
    try:
        text, title = _fetch_via_requests_bs4(snapshot_url, max_chars=max_chars)
        if text and not _is_error_like_text(text):
            return text, title
    except Exception:
        return "", ""
    return "", ""


def fetch_page_bundle(url: str, max_chars: int = 8000) -> dict:
    # Prefer direct PDF parsing, then Jina/HTML; if failed, try Wayback snapshot.
    if _looks_like_pdf_url(url):
        try:
            text, title = _fetch_pdf_direct(url, max_chars=max_chars)
            return {"text": text, "title": _clean_title(title), "source": "pdf_direct"}
        except Exception:
            pass

    try:
        text = _fetch_via_jina(url, max_chars=max_chars)
        if text:
            return {
                "text": text,
                "title": _clean_title(_extract_title_from_jina_text(text)),
                "source": "jina",
            }
    except Exception:
        pass

    try:
        text, title = _fetch_via_requests_bs4(url, max_chars=max_chars)
        if text and not _is_error_like_text(text):
            return {"text": text, "title": _clean_title(title), "source": "requests_bs4"}
    except Exception:
        pass

    # Site-specific fallback: Zhihu pages often return 403 for desktop crawler.
    if _is_zhihu_url(url):
        for candidate in _build_zhihu_candidates(url):
            try:
                text, title = _fetch_zhihu_with_mobile_headers(candidate, max_chars=max_chars)
                if text and not _is_error_like_text(text):
                    return {"text": text, "title": _clean_title(title), "source": "zhihu_mobile"}
            except Exception:
                continue

    text, title = _fetch_via_wayback(url, max_chars=max_chars)
    if text:
        return {"text": text, "title": _clean_title(title), "source": "wayback"}

    raise ValueError(f"Failed to fetch useful content for URL: {url}")


def fetch_page_text(url: str, max_chars: int = 8000) -> str:
    bundle = fetch_page_bundle(url, max_chars=max_chars)
    return (bundle.get("text") or "").strip()
