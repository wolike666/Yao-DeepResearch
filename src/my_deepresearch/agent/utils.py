from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any
from urllib.parse import urlsplit

ANSWER_TAG = "answer"


def _is_zh_text(text: str) -> bool:
    content = (text or "").strip()
    if not content:
        return False
    return bool(re.search(r"[\u4e00-\u9fff]", content))


def _reference_header_for(text: str) -> str:
    return "参考文献：" if _is_zh_text(text) else "References:"


def extract_json_block(text: str) -> dict:
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        raise ValueError(f"Planner output is not valid JSON: {text}")
    return json.loads(match.group(0))


def extract_tag_content(text: str, tag: str) -> str:
    pattern = rf"<{tag}>[\s\S]*?</{tag}>"
    match = re.search(pattern, text, flags=re.IGNORECASE)
    if not match:
        return ""
    block = match.group(0)
    block = re.sub(rf"^<{tag}>", "", block, flags=re.IGNORECASE).strip()
    block = re.sub(rf"</{tag}>$", "", block, flags=re.IGNORECASE).strip()
    return block


def ensure_answer_tagged(text: str) -> str:
    if re.search(r"<answer>[\s\S]*?</answer>", text, flags=re.IGNORECASE):
        return text.strip()
    return f"<answer>\n{text.strip()}\n</answer>"


def has_inline_citations(text: str) -> bool:
    return bool(
        re.search(r"\[[^\]]+\]\(https?://[^)]+\)", text) or re.search(r"\[\d+\]", text)
    )


def _merge_reference_items(
    evidence: list[dict],
    read_sources: list[dict],
    sources: list[dict],
) -> list[dict]:
    merged: list[dict] = []
    seen: set[str] = set()
    for group in (evidence or [], read_sources or [], sources or []):
        for item in group:
            url = (item.get("url") or "").strip()
            if not url or url in seen:
                continue
            seen.add(url)
            merged.append(item)
    return merged


def _looks_like_url_title(text: str) -> bool:
    t = (text or "").strip().lower()
    if not t:
        return False
    return bool(
        re.fullmatch(r"[a-z0-9.-]+\.[a-z]{2,6}(/.*)?", t)
        or re.fullmatch(r"https?://[^\s]+", t)
        or re.fullmatch(r"[a-z0-9.-]+(/[a-z0-9._~%-]+)+", t)
    )


def _looks_mojibake_title(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    markers = ["Ã", "Â", "æ", "ç", "ð", "�", "¤", "€", "™", "œ"]
    if any(m in t for m in markers):
        return True
    # Many latin-1 chars with little CJK tends to be mojibake for zh pages.
    latin1 = sum(1 for ch in t if "\u00c0" <= ch <= "\u00ff")
    cjk = sum(1 for ch in t if "\u4e00" <= ch <= "\u9fff")
    return latin1 >= 3 and cjk == 0


def _repair_mojibake_utf8_latin1(text: str) -> str:
    raw = (text or "").strip()
    if not raw:
        return ""
    try:
        fixed = raw.encode("latin-1", errors="strict").decode("utf-8", errors="strict").strip()
    except Exception:
        return raw
    if not fixed:
        return raw
    # Keep repaired text only when it is clearly better.
    if _looks_mojibake_title(raw) and not _looks_mojibake_title(fixed):
        return fixed
    return raw


def _recover_title_from_jina_title(text: str) -> str:
    raw = _repair_mojibake_utf8_latin1((text or "").strip())
    if not raw:
        return ""
    # Jina titles are often returned as "Title: xxx" or "标题: xxx".
    for prefix in ("Title:", "TITLE:", "标题:", "標題:"):
        if raw.startswith(prefix):
            raw = raw.split(":", 1)[1].strip()
            break
    return raw


def _fallback_title_from_url(url: str) -> str:
    u = (url or "").strip()
    if not u:
        return "source"
    try:
        parsed = urlsplit(u)
        domain = (parsed.netloc or "").strip()
        path = (parsed.path or "").strip("/")
        if path:
            leaf = path.split("/")[-1].strip()
            if leaf:
                return f"{domain}/{leaf}"[:180]
        return domain or "source"
    except Exception:
        return "source"


def _sanitize_ref_title(raw_title: str, url: str, snippet: str = "", summary: str = "") -> str:
    title = _recover_title_from_jina_title(raw_title)
    title = re.sub(r"\s+", " ", title)
    title = title.replace("…", "").replace("...", "").strip(" -:：")
    if title.startswith("[PDF]"):
        title = title[5:].strip()

    is_bad = (
        not title
        or title.lower() == "source"
        or len(title) < 4
        or _looks_mojibake_title(title)
        or _looks_like_url_title(title)
        or bool(re.fullmatch(r"[A-Za-z0-9_\-]{6,}", title))
    )
    if is_bad:
        # Prefer snippet/summary as a fallback only when the page title is unusable.
        for candidate in (snippet, summary):
            c = _recover_title_from_jina_title(candidate)
            c = re.sub(r"\s+", " ", (c or "").strip())
            c = c.replace("…", "").replace("...", "").strip(" -:：")
            if len(c) >= 8 and not _looks_mojibake_title(c) and not _looks_like_url_title(c):
                return c[:180]
        for candidate in (snippet, summary):
            c = re.sub(r"\s+", " ", (candidate or "").strip())
            c = c.replace("…", "").replace("...", "").strip(" -:：")
            if len(c) >= 8 and not _looks_mojibake_title(c):
                return c[:180]
        return _fallback_title_from_url(url)
    return title[:180]


def build_citation_catalog(
    evidence: list[dict],
    read_sources: list[dict],
    sources: list[dict],
    limit: int = 20,
) -> list[dict]:
    catalog: list[dict] = []
    merged = []
    seen_urls: set[str] = set()
    for group in (evidence or [], read_sources or []):
        for item in group:
            url = (item.get("url") or "").strip()
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            merged.append(item)
    if not merged:
        return catalog

    for idx, item in enumerate(merged, start=1):
        url = (item.get("url") or "").strip()
        if not url:
            continue
        title = _sanitize_ref_title(
            (item.get("title") or item.get("domain") or "").strip(),
            url=url,
            snippet=(item.get("snippet") or "").strip(),
            summary=(item.get("summary") or "").strip(),
        )
        catalog.append(
            {
                "id": idx,
                "url": url,
                "title": title or "source",
                "domain": (item.get("domain") or _domain_from_url(url) or "").strip(),
            }
        )
        if len(catalog) >= max(1, limit):
            break
    return catalog


def build_citation_fallback(
    evidence: list[dict],
    read_sources: list[dict],
    sources: list[dict],
    answer_text: str = "",
    limit: int = 6,
) -> str:
    items = build_citation_catalog(evidence, read_sources, sources, limit=max(limit, 6))
    refs: list[str] = []
    seen: set[str] = set()
    for item in items:
        url = (item.get("url") or "").strip()
        if not url or url in seen:
            continue
        title = _sanitize_ref_title(
            (item.get("title") or item.get("domain") or "").strip(),
            url=url,
        )
        refs.append(f"[{item['id']}] {url} - {title}")
        seen.add(url)
        if len(refs) >= limit:
            break
    if not refs:
        return ""
    return f"{_reference_header_for(answer_text)}\n" + "\n".join(refs)


def _domain_from_url(url: str) -> str:
    try:
        return urlsplit(url).netloc
    except Exception:
        return ""


def _strip_reference_section(text: str) -> str:
    pattern = re.compile(
        r"\n(?:References|参考文献)\s*[:：]?\s*\n(?:\[\d+\][^\n]*(?:\n|$))+",
        flags=re.IGNORECASE,
    )
    return pattern.sub("\n", text).strip()


def _limit_sentence_citations(text: str, max_citations_per_sentence: int = 3) -> str:
    if max_citations_per_sentence <= 0 or not text:
        return text

    citation_pattern = re.compile(r"\[(\d+)\]")
    sentence_boundary_pattern = re.compile(r"([。！？!?；;]+)")

    out_lines: list[str] = []
    for line in text.splitlines(keepends=True):
        # Keep bibliography lines unchanged.
        if re.match(r"^\s*\[\d+\]\s+https?://", line):
            out_lines.append(line)
            continue

        newline = "\n" if line.endswith("\n") else ""
        core = line[:-1] if newline else line

        parts = sentence_boundary_pattern.split(core)
        sentence_chunks: list[str] = []
        i = 0
        while i < len(parts):
            text_part = parts[i]
            boundary = parts[i + 1] if i + 1 < len(parts) else ""
            sentence_chunks.append(f"{text_part}{boundary}")
            i += 2

        limited_chunks: list[str] = []
        for chunk in sentence_chunks:
            out = []
            cursor = 0
            kept_count = 0
            seen_ids: set[int] = set()

            for match in citation_pattern.finditer(chunk):
                start, end = match.span()
                between = chunk[cursor:start]
                out.append(between)

                cid = int(match.group(1))
                if cid in seen_ids:
                    pass
                elif kept_count < max_citations_per_sentence:
                    out.append(f"[{cid}]")
                    kept_count += 1
                    seen_ids.add(cid)
                cursor = end

            out.append(chunk[cursor:])
            merged = "".join(out)
            merged = re.sub(r"\[(\d+)\](\s*\[\1\])+", r"[\1]", merged)
            limited_chunks.append(merged)

        out_lines.append("".join(limited_chunks) + newline)

    return "".join(out_lines)


def _replace_answer_block(tagged_text: str, answer_text: str) -> str:
    pattern = re.compile(r"(<answer>)[\s\S]*?(</answer>)", flags=re.IGNORECASE)
    if pattern.search(tagged_text):
        return pattern.sub(
            lambda m: f"{m.group(1)}\n{answer_text}\n{m.group(2)}",
            tagged_text,
            count=1,
        ).strip()
    return ensure_answer_tagged(answer_text)


def normalize_benchmark_citations(
    text: str,
    evidence: list[dict],
    read_sources: list[dict],
    sources: list[dict],
    limit: int = 20,
) -> tuple[str, list[dict]]:
    content = (text or "").strip()
    if not content:
        return content, []

    # Remove common placeholder tokens leaked by model drafts.
    content = re.sub(r"\[\s*(?:notes?|source)\s*\]", "", content, flags=re.IGNORECASE)
    content = re.sub(r"\bsource\s*列表\b", "来源列表", content, flags=re.IGNORECASE)

    catalog = build_citation_catalog(evidence, read_sources, sources, limit=limit)
    items = list(catalog)
    title_map: dict[str, str] = {}
    url_to_id: dict[str, int] = {}
    for item in items:
        url = (item.get("url") or "").strip()
        if not url or url in title_map:
            continue
        title = _sanitize_ref_title(
            (item.get("title") or item.get("domain") or "").strip(),
            url=url,
        )
        title_map[url] = title or "source"
        try:
            url_to_id[url] = int(item.get("id"))
        except Exception:
            continue

    allowed_ids = {int(item.get("id")) for item in items if item.get("id") is not None}

    content = re.sub(r"\[Evidence:[^\]]*\]", "", content, flags=re.IGNORECASE)
    content = _strip_reference_section(content)

    md_link_pattern = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")

    def _md_link_repl(match: re.Match) -> str:
        url = match.group(2).strip()
        idx = url_to_id.get(url)
        if idx is None:
            return match.group(1)
        return f"[{idx}]"

    content = md_link_pattern.sub(_md_link_repl, content)

    bare_url_pattern = re.compile(r"(?<!\()(https?://[^\s\])>]+)")

    def _bare_url_repl(match: re.Match) -> str:
        url = match.group(1).strip()
        idx = url_to_id.get(url)
        if idx is None:
            return ""
        return f"[{idx}]"

    content = bare_url_pattern.sub(_bare_url_repl, content)
    content = re.sub(r"\[(\d+)\](\s*\[\1\])+", r"[\1]", content)
    content = re.sub(r"[ \t]+\n", "\n", content).strip()
    content = _limit_sentence_citations(content, max_citations_per_sentence=3)

    used_ids: list[int] = []
    seen_used: set[int] = set()
    for x in re.findall(r"\[(\d+)\]", content):
        cid = int(x)
        if cid not in allowed_ids or cid in seen_used:
            continue
        seen_used.add(cid)
        used_ids.append(cid)

    if used_ids:
        old_to_new = {old_id: new_id for new_id, old_id in enumerate(used_ids, start=1)}

        def _relabel(match: re.Match) -> str:
            cid = int(match.group(1))
            new_id = old_to_new.get(cid)
            return f"[{new_id}]" if new_id is not None else ""

        content = re.sub(r"\[(\d+)\]", _relabel, content)
        content = re.sub(r"\[(\d+)\](\s*\[\1\])+", r"[\1]", content)
        content = re.sub(r"[ \t]+\n", "\n", content).strip()

    if not allowed_ids:
        return content, []

    if not used_ids:
        used_ids = [item["id"] for item in items[: max(1, min(6, len(items)))]]
        old_to_new = {old_id: new_id for new_id, old_id in enumerate(used_ids, start=1)}
    else:
        old_to_new = {old_id: new_id for new_id, old_id in enumerate(used_ids, start=1)}

    ref_lines = []
    id_to_item = {int(item["id"]): item for item in items if item.get("id") is not None}
    for cid in used_ids:
        item = id_to_item.get(cid)
        if not item:
            continue
        url = (item.get("url") or "").strip()
        title = _sanitize_ref_title(
            title_map.get(url, ""),
            url=url,
        )
        ref_lines.append(f"[{old_to_new.get(cid, cid)}] {url} - {title}")

    return content, [
        {
            "id": old_to_new.get(cid, cid),
            "url": (id_to_item[cid].get("url") or "").strip(),
            "title": title_map.get((id_to_item[cid].get("url") or "").strip(), _domain_from_url((id_to_item[cid].get("url") or "").strip()) or "source"),
        }
        for cid in used_ids
        if cid in id_to_item
    ]


def clamp_confidence(value: Any) -> float:
    try:
        num = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, num))


def dedupe_keep_order(items: list[str], limit: int = 8) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        text = (item or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
        if len(out) >= limit:
            break
    return out


def merge_sources(existing: list[dict], incoming: list[dict]) -> list[dict]:
    seen_urls = {(item.get("url") or "").strip() for item in existing}
    merged = list(existing)
    for item in incoming:
        url = (item.get("url") or "").strip()
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        if "source_tier" not in item:
            item["source_tier"] = "general"
        if "domain" not in item:
            item["domain"] = ""
        if "access_time" not in item:
            item["access_time"] = datetime.now().isoformat(timespec="seconds")
        if "relevance_score" not in item:
            item["relevance_score"] = 0.5
        merged.append(item)
    return merged


def pick_unvisited_url(state_sources: list[dict], visited_urls: set[str], source_policy: str = "balanced") -> str:
    tier_rank = {
        "official": 0,
        "academic": 1,
        "news": 2,
        "community": 3,
        "general": 4,
    }
    candidates: list[tuple[int, int, str]] = []
    for idx, item in enumerate(state_sources):
        url = (item.get("url") or "").strip()
        if not url or url in visited_urls:
            continue
        tier = (item.get("source_tier") or "general").strip().lower()
        if source_policy == "strict" and tier not in {"official", "academic", "news"}:
            continue
        candidates.append((tier_rank.get(tier, 4), idx, url))

    if candidates:
        candidates.sort(key=lambda x: (x[0], x[1]))
        return candidates[0][2]

    if source_policy == "strict":
        for item in reversed(state_sources):
            url = (item.get("url") or "").strip()
            if url and url not in visited_urls:
                return url
    return ""


def looks_academic_question(text: str) -> bool:
    lowered = (text or "").lower()
    keywords = ["paper", "arxiv", "benchmark", "scholar", "论文", "评测", "学术", "研究"]
    return any(token in lowered for token in keywords)


def _empty_usage_bucket() -> dict:
    return {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "call_count": 0,
    }


def record_llm_usage(state: Any, usage: dict | None) -> None:
    if not usage:
        return

    prompt_tokens = int(usage.get("prompt_tokens") or 0)
    completion_tokens = int(usage.get("completion_tokens") or 0)
    total_tokens = int(usage.get("total_tokens") or (prompt_tokens + completion_tokens))
    purpose = str(usage.get("purpose") or "unknown").strip() or "unknown"
    step = usage.get("step")
    source = str(usage.get("source") or "estimated").strip() or "estimated"

    call_record = {
        "step": step,
        "purpose": purpose,
        "model": usage.get("model"),
        "source": source,
        "estimated": bool(usage.get("estimated", source != "official")),
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
    }
    state.llm_calls.append(call_record)

    totals = state.token_usage.setdefault("totals", _empty_usage_bucket())
    totals["prompt_tokens"] += prompt_tokens
    totals["completion_tokens"] += completion_tokens
    totals["total_tokens"] += total_tokens
    totals["call_count"] += 1

    by_purpose = state.token_usage.setdefault("by_purpose", {})
    purpose_bucket = by_purpose.setdefault(purpose, _empty_usage_bucket())
    purpose_bucket["prompt_tokens"] += prompt_tokens
    purpose_bucket["completion_tokens"] += completion_tokens
    purpose_bucket["total_tokens"] += total_tokens
    purpose_bucket["call_count"] += 1

    if step is not None:
        step_key = str(step)
        by_step = state.token_usage.setdefault("by_step", {})
        step_bucket = by_step.setdefault(step_key, _empty_usage_bucket())
        step_bucket["prompt_tokens"] += prompt_tokens
        step_bucket["completion_tokens"] += completion_tokens
        step_bucket["total_tokens"] += total_tokens
        step_bucket["call_count"] += 1

    sources = state.token_usage.setdefault(
        "sources",
        {"official_call_count": 0, "estimated_call_count": 0},
    )
    if source == "official":
        sources["official_call_count"] += 1
    else:
        sources["estimated_call_count"] += 1


def build_result_payload(state: Any) -> dict:
    tagged_raw = ensure_answer_tagged(state.draft_answer)
    plain = extract_tag_content(tagged_raw, ANSWER_TAG)
    if not plain:
        plain = tagged_raw

    catalog = build_citation_catalog(
        getattr(state, "evidence", []),
        getattr(state, "read_sources", []),
        state.sources,
        limit=20,
    )
    plain, used_catalog = normalize_benchmark_citations(
        plain,
        getattr(state, "evidence", []),
        getattr(state, "read_sources", []),
        state.sources,
        limit=20,
    )
    if not has_inline_citations(plain):
        fallback = build_citation_fallback(
            getattr(state, "evidence", []),
            getattr(state, "read_sources", []),
            state.sources,
            answer_text=plain,
        )
        if fallback:
            plain = f"{plain} [1]\n\n{fallback}"
    else:
        if used_catalog:
            ref_lines = []
            for item in used_catalog:
                ref_lines.append(
                    f"[{item['id']}] {item['url']} - {item.get('title') or 'source'}"
                )
            if ref_lines:
                plain = _strip_reference_section(plain)
                plain = f"{plain}\n\n{_reference_header_for(plain)}\n" + "\n".join(ref_lines)
    tagged = _replace_answer_block(tagged_raw, plain)
    return {
        "prompt": state.question,
        "question": state.question,
        "answer": plain,
        "answer_tagged": tagged,
        "article": plain,
        "steps": state.steps,
        "notes": state.notes,
        "sources": state.sources,
        "read_sources": getattr(state, "read_sources", []),
        "reflections": state.reflections,
        "token_usage": getattr(state, "token_usage", {}),
        "llm_calls": getattr(state, "llm_calls", []),
    }
