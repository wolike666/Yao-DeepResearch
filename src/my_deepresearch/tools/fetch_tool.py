from __future__ import annotations

import os
import re
import threading
import time
from collections import deque
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


_JINA_NO_KEY_LOCK = threading.Lock()
_JINA_NO_KEY_REQ_TIMES: deque[float] = deque()


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


def _jina_no_key_rpm() -> int:
    raw = (os.getenv("JINA_NO_KEY_RPM", "20") or "20").strip()
    try:
        rpm = int(raw)
    except Exception:
        rpm = 20
    return max(1, min(120, rpm))


def _wait_for_jina_no_key_slot() -> None:
    rpm = _jina_no_key_rpm()
    window_seconds = 60.0
    min_interval = window_seconds / float(rpm)
    while True:
        with _JINA_NO_KEY_LOCK:
            now = time.monotonic()
            while _JINA_NO_KEY_REQ_TIMES and now - _JINA_NO_KEY_REQ_TIMES[0] >= window_seconds:
                _JINA_NO_KEY_REQ_TIMES.popleft()

            if len(_JINA_NO_KEY_REQ_TIMES) < rpm:
                if _JINA_NO_KEY_REQ_TIMES:
                    elapsed = now - _JINA_NO_KEY_REQ_TIMES[-1]
                    if elapsed < min_interval:
                        wait_seconds = min_interval - elapsed
                    else:
                        _JINA_NO_KEY_REQ_TIMES.append(now)
                        return
                else:
                    _JINA_NO_KEY_REQ_TIMES.append(now)
                    return
            else:
                wait_seconds = window_seconds - (now - _JINA_NO_KEY_REQ_TIMES[0])

        time.sleep(max(0.05, wait_seconds))


def _fetch_via_jina_once(url: str, max_chars: int, key: str | None) -> str:
    jina_url = f"https://r.jina.ai/{url}"
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    if not key:
        _wait_for_jina_no_key_slot()
    resp = requests.get(jina_url, headers=headers, timeout=30)
    resp.raise_for_status()
    text = (resp.text or "").strip()
    if _is_error_like_text(text):
        return ""
    return text[:max_chars]


def _fetch_via_jina(url: str, max_chars: int) -> str:
    key = os.getenv("JINA_API_KEYS", "").strip().strip("\"'")
    if key:
        try:
            return _fetch_via_jina_once(url=url, max_chars=max_chars, key=key)
        except requests.HTTPError as exc:
            status = getattr(exc.response, "status_code", None)
            # Paid key may fail due to balance/auth issues; fall back to no-key path.
            if status not in {401, 402, 403, 429}:
                return ""
        except Exception:
            return ""

    try:
        return _fetch_via_jina_once(url=url, max_chars=max_chars, key=None)
    except Exception:
        return ""


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


def _looks_mojibake(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    markers = ["Ã", "Â", "æ", "ç", "ð", "�", "¤", "€", "™", "œ"]
    if any(m in t for m in markers):
        return True
    latin1 = sum(1 for ch in t if "\u00c0" <= ch <= "\u00ff")
    cjk = sum(1 for ch in t if "\u4e00" <= ch <= "\u9fff")
    return latin1 >= 3 and cjk == 0


def _recover_title_from_text(text: str) -> str:
    raw = (text or "").strip()
    if not raw:
        return ""
    for prefix in ("Title:", "TITLE:", "标题:", "標題:"):
        if raw.startswith(prefix):
            raw = raw.split(":", 1)[1].strip()
            break
    raw = _clean_title(raw)
    if _looks_mojibake(raw):
        return ""
    return raw


def _extract_title_from_html(resp_text: str, soup: BeautifulSoup) -> str:
    candidates: list[str] = []
    if soup.title and soup.title.string:
        candidates.append(_clean_title(soup.title.string))

    for meta_name in ("og:title", "twitter:title", "title"):
        tag = soup.find("meta", attrs={"property": meta_name}) or soup.find(
            "meta", attrs={"name": meta_name}
        )
        if tag and tag.get("content"):
            candidates.append(_clean_title(tag.get("content")))

    head_lines = [ln.strip() for ln in (resp_text or "").splitlines()[:20] if ln.strip()]
    for ln in head_lines:
        if ln.lower().startswith("title:") or ln.startswith("标题:") or ln.startswith("標題:"):
            candidates.append(_recover_title_from_text(ln))

    for cand in candidates:
        cand = _recover_title_from_text(cand)
        if cand:
            return cand
    return ""


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
    page_title = _extract_title_from_html(resp.text, soup)
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
    title = _extract_title_from_html(resp.text, soup)
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
            title = _recover_title_from_text(_extract_title_from_jina_text(text))
            if not title:
                title = _clean_title(_extract_title_from_html(text, BeautifulSoup(text, "html.parser")))
            return {
                "text": text,
                "title": title,
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
