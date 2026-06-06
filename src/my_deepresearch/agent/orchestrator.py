from __future__ import annotations

import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from urllib.parse import urlsplit

from ..config import Settings
from ..llm_client import LLMClient
from ..prompts import EXTRACTOR_SYSTEM_PROMPT, PLANNER_SYSTEM_PROMPT, SYNTHESIZE_SYSTEM_PROMPT
from ..tools.fetch_tool import fetch_page_bundle, fetch_page_text
from ..tools.scholar_tool import search_scholar
from ..tools.search_tool import search_web
from .planner import planner_user_prompt
from .reflector import reflect_step
from .state import ResearchState
from .utils import (
    build_result_payload,
    build_citation_catalog,
    dedupe_keep_order,
    ensure_answer_tagged,
    extract_json_block,
    looks_academic_question,
    merge_sources,
    pick_unvisited_url,
    _sanitize_ref_title,
)


def _find_source_meta(sources: list[dict], url: str) -> dict:
    for item in sources:
        if (item.get("url") or "").strip() == url:
            return item
    return {}


def _best_source_title(url: str, page_title: str, source_meta: dict, summary: str = "") -> str:
    return _sanitize_ref_title(
        page_title or (source_meta.get("title") or "").strip(),
        url=url,
        snippet=(source_meta.get("snippet") or "").strip(),
        summary=summary,
    )


def _summarize_page(llm: LLMClient, question: str, url: str, page_text: str) -> str:
    user_prompt = (
        f"Question: {question}\n"
        f"URL: {url}\n"
        "Task:\n"
        "1) locate passages directly relevant to the question;\n"
        "2) extract key evidence with context;\n"
        "3) summarize contribution and reliability.\n"
        "If page is irrelevant, explicitly say no useful information.\n\n"
        f"Page content:\n{page_text}"
    )
    return llm.chat(EXTRACTOR_SYSTEM_PROMPT, user_prompt)


def _extract_page_evidence(llm: LLMClient, question: str, url: str, page_text: str) -> dict:
    user_prompt = (
        f"Question: {question}\n"
        f"URL: {url}\n"
        "Return ONLY one JSON object with this schema:\n"
        "{\n"
        '  "is_relevant": true,\n'
        '  "evidence_count": 0,\n'
        '  "key_facts": ["fact1"],\n'
        '  "summary": "short summary",\n'
        '  "reason": "why relevant or not"\n'
        "}\n"
        "Rules:\n"
        "- evidence_count counts concrete facts useful for answering the question.\n"
        "- key_facts must be concise and verifiable from page text.\n"
        "- if no useful info, set is_relevant=false, evidence_count=0.\n\n"
        f"Page content:\n{page_text}"
    )
    try:
        raw = llm.chat(EXTRACTOR_SYSTEM_PROMPT, user_prompt)
    except Exception as exc:
        return _heuristic_extract_page_evidence(question, page_text, reason=f"extractor_call_failed: {exc}")
    try:
        data = extract_json_block(raw)
    except Exception:
        data = {
            "is_relevant": False,
            "evidence_count": 0,
            "key_facts": [],
            "summary": "",
            "reason": "extractor_json_parse_failed",
        }

    if not isinstance(data, dict):
        data = {}
    is_relevant = bool(data.get("is_relevant", False))
    try:
        evidence_count = int(data.get("evidence_count", 0))
    except Exception:
        evidence_count = 0
    key_facts = data.get("key_facts") or []
    if not isinstance(key_facts, list):
        key_facts = []
    key_facts = [str(x).strip() for x in key_facts if str(x).strip()][:8]
    summary = str(data.get("summary") or "").strip()
    reason = str(data.get("reason") or "").strip()
    # Fallback: extractor sometimes returns evidence_count=0 but still provides key facts/summary.
    if evidence_count <= 0 and key_facts:
        evidence_count = len(key_facts)
    if evidence_count <= 0 and summary and not _is_low_value_note(summary):
        evidence_count = 1
    return {
        "is_relevant": is_relevant,
        "evidence_count": max(0, evidence_count),
        "key_facts": key_facts,
        "summary": summary,
        "reason": reason,
    }


def _extract_keywords(text: str) -> list[str]:
    raw = (text or "").strip().lower()
    if not raw:
        return []
    zh_terms = re.findall(r"[\u4e00-\u9fff]{2,8}", raw)
    en_terms = re.findall(r"[a-z]{4,}", raw)
    stop = {
        "目前",
        "中国",
        "实际",
        "特别",
        "研究",
        "得出",
        "哪些",
        "等等",
        "report",
        "about",
        "with",
        "from",
        "that",
        "this",
        "those",
    }
    out: list[str] = []
    seen: set[str] = set()
    for term in zh_terms + en_terms:
        if term in stop:
            continue
        if term in seen:
            continue
        seen.add(term)
        out.append(term)
        if len(out) >= 12:
            break
    return out


def _query_decompose_enabled() -> bool:
    raw = (os.getenv("ENABLE_QUERY_DECOMPOSE", "1") or "1").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def _query_decompose_limit() -> int:
    raw = (os.getenv("QUERY_DECOMPOSE_MAX", "6") or "6").strip()
    try:
        val = int(raw)
    except Exception:
        val = 6
    return max(2, min(10, val))


def _en_query_fallback_enabled() -> bool:
    raw = (os.getenv("ENABLE_EN_QUERY_FALLBACK", "1") or "1").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def _decompose_interpretation_enabled() -> bool:
    raw = (os.getenv("ENABLE_INTERPRETATION_QUERY", "1") or "1").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def _one_en_fallback_query(question: str) -> str:
    q = (question or "").strip()
    if not q:
        return ""
    if "中产" in q or "阶层" in q:
        return "China social stratification report interpretation middle class income wealth"
    return f"{q} report interpretation"


def _topic_decompose_queries(question: str, seed_queries: list[str], limit: int = 6) -> list[str]:
    q = (question or "").strip()
    seeds = dedupe_keep_order(seed_queries or [], limit=4)
    if not q:
        return seeds

    is_zh = bool(re.search(r"[\u4e00-\u9fff]", q))
    topic = q
    if is_zh:
        if "中产" in q and "阶层" in q:
            topic = "中国社会阶层与中产阶层"
        elif "中产" in q:
            topic = "中国中产阶级"
        elif "阶层" in q:
            topic = "中国社会阶层"
        templates = [
            f"{topic} 官方定义 统计口径 国家统计局",
            f"{topic} 规模 人数 占比 最新数据",
            f"{topic} 收入 区间 中位数 分位数",
            f"{topic} 资产 负债 杠杆 房贷 财务状况",
            f"{topic} CHFS CFPS CGSS 调查 报告",
            f"{topic} 社科院 蓝皮书 学术论文 PDF",
        ]
        if _decompose_interpretation_enabled():
            templates.extend(
                [
                    f"{topic} 研究报告 解读 综述 摘要 核心观点",
                    f"{topic} 原报告 找不到 替代来源 二手引用 数据口径",
                ]
            )
    else:
        templates = [
            f"{q} official definition statistical methodology",
            f"{q} population size estimate latest data",
            f"{q} income distribution median percentile",
            f"{q} assets debt leverage financial condition",
            f"{q} survey data CHFS CFPS CGSS",
            f"{q} academic report PDF",
        ]

    combined = dedupe_keep_order(seeds + templates, limit=limit)
    if is_zh and _en_query_fallback_enabled():
        en_q = _one_en_fallback_query(q)
        if en_q:
            combined = [x for x in combined if x != en_q]
            if len(combined) >= limit:
                combined = combined[: max(0, limit - 1)]
            combined.append(en_q)
            combined = dedupe_keep_order(combined, limit=limit)
    return combined


def _heuristic_extract_page_evidence(question: str, page_text: str, reason: str = "") -> dict:
    text = (page_text or "").strip()
    if not text:
        return {
            "is_relevant": False,
            "evidence_count": 0,
            "key_facts": [],
            "summary": "",
            "reason": reason or "empty_page_text",
        }

    keywords = _extract_keywords(question)
    lowered = text.lower()
    hit_keywords = [k for k in keywords if k and k in lowered]
    hit_count = len(hit_keywords)

    # Prefer sentences containing numbers/ratios/time and topic keywords.
    sentences = re.split(r"(?<=[。！？!?；;\n])", text)
    candidates: list[str] = []
    for sent in sentences:
        s = sent.strip()
        if len(s) < 16:
            continue
        has_number = bool(re.search(r"\d|%|％|万|亿|元|年", s))
        has_kw = any(k in s.lower() for k in keywords[:10]) if keywords else False
        if has_number and has_kw:
            candidates.append(s)
        elif has_kw and len(candidates) < 2:
            candidates.append(s)
        if len(candidates) >= 3:
            break

    if not candidates:
        for sent in sentences:
            s = sent.strip()
            if len(s) >= 24:
                candidates.append(s)
            if len(candidates) >= 2:
                break

    key_facts = [c[:220] for c in candidates[:3]]
    summary = " ".join(candidates[:2]).strip()[:420]
    is_relevant = hit_count >= 2 or (hit_count >= 1 and bool(key_facts))
    evidence_count = len(key_facts) if is_relevant else 0

    return {
        "is_relevant": is_relevant,
        "evidence_count": evidence_count,
        "key_facts": key_facts,
        "summary": summary,
        "reason": reason or "heuristic_extractor_fallback",
    }


def _is_low_value_note(note: str) -> bool:
    text = (note or "").strip()
    if not text:
        return True
    lowered = text.lower()
    markers = [
        "无有效信息",
        "没有有效信息",
        "no useful information",
        "failed to read",
        "404",
        "not found",
        "页面不存在",
        "no unread url",
        "no unread url available to read",
    ]
    return any(marker in lowered or marker in text for marker in markers)


def _maybe_research_with_title(
    state: ResearchState,
    settings: Settings,
    source_meta: dict,
    failed_url: str,
) -> tuple[list[str], int]:
    title = (source_meta.get("title") or "").strip()
    if not title:
        return [], 0

    domain = urlsplit(failed_url).netloc.strip()
    candidates = [f"\"{title}\""]
    if domain:
        candidates.append(f"\"{title}\" {domain}")

    queries: list[str] = []
    new_total = 0
    for query in candidates:
        if query in state.backup_queries:
            continue
        state.backup_queries.add(query)
        queries.append(query)
        try:
            results = search_web(
                query,
                max_results=max(3, settings.max_search_results),
                source_policy=settings.source_policy,
            )
            before = len(state.sources)
            state.sources = merge_sources(state.sources, results)
            added_urls = [item.get("url", "").strip() for item in state.sources[before:]]
            _enqueue_pending_urls(state, added_urls)
            new_total += max(0, len(state.sources) - before)
        except Exception as exc:
            state.notes.append(f"backup search failed: {query}; error: {exc}")
    return queries, new_total


def _enqueue_pending_urls(state: ResearchState, urls: list[str]) -> None:
    existing = set(state.pending_read_urls)
    for raw in urls:
        url = (raw or "").strip()
        if not url or url in state.tried_urls or url in existing:
            continue
        state.pending_read_urls.append(url)
        existing.add(url)


def _dequeue_next_url(state: ResearchState, preferred_url: str) -> str:
    pref = (preferred_url or "").strip()
    if pref and pref not in state.tried_urls:
        state.pending_read_urls = [u for u in state.pending_read_urls if u != pref]
        return pref

    while state.pending_read_urls:
        url = state.pending_read_urls.pop(0).strip()
        if url and url not in state.tried_urls:
            return url

    return pick_unvisited_url(state.sources, state.tried_urls, source_policy="balanced")


def _read_batch_size() -> int:
    raw = (os.getenv("BATCH_READ_SIZE", "3") or "3").strip()
    try:
        size = int(raw)
    except Exception:
        size = 3
    return max(1, min(5, size))


def _read_batch_workers(batch_size: int) -> int:
    raw = (os.getenv("BATCH_READ_MAX_WORKERS", "3") or "3").strip()
    try:
        workers = int(raw)
    except Exception:
        workers = 3
    workers = max(1, min(5, workers))
    return min(workers, max(1, batch_size))


def _read_all_from_search_enabled() -> bool:
    raw = (os.getenv("READ_ALL_SEARCH_RESULTS", "0") or "0").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def _dequeue_next_urls(state: ResearchState, preferred_url: str, batch_size: int) -> list[str]:
    picked: list[str] = []
    first = _dequeue_next_url(state, preferred_url)
    if first:
        picked.append(first)
    while len(picked) < batch_size:
        nxt = _dequeue_next_url(state, "")
        if not nxt:
            break
        if nxt in picked:
            continue
        picked.append(nxt)
    return picked


def _dequeue_all_urls(state: ResearchState, preferred_url: str) -> list[str]:
    picked: list[str] = []
    seen: set[str] = set()

    def _push(raw: str) -> None:
        url = (raw or "").strip()
        if not url or url in seen or url in state.tried_urls:
            return
        picked.append(url)
        seen.add(url)

    pref = (preferred_url or "").strip()
    if pref:
        state.pending_read_urls = [u for u in state.pending_read_urls if (u or "").strip() != pref]
        _push(pref)

    for url in state.pending_read_urls:
        _push(url)
    state.pending_read_urls = []

    for item in state.sources:
        _push((item.get("url") or "").strip())

    return picked


def _fetch_many_pages(
    urls: list[str], max_chars: int, max_workers: int
) -> tuple[dict[str, dict], dict[str, str]]:
    page_bundle_by_url: dict[str, dict] = {}
    fetch_errors: dict[str, str] = {}
    if not urls:
        return page_bundle_by_url, fetch_errors

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_url = {
            executor.submit(fetch_page_bundle, url, max_chars): url for url in urls
        }
        for future in as_completed(future_to_url):
            url = future_to_url[future]
            try:
                page_bundle_by_url[url] = future.result()
            except Exception as exc:
                fetch_errors[url] = f"Failed to read {url}: {exc}"
    return page_bundle_by_url, fetch_errors


def _synthesize_answer(llm: LLMClient, state: ResearchState) -> str:
    import json
    citation_catalog = build_citation_catalog(
        state.evidence,
        state.read_sources,
        state.sources,
        limit=20,
    )
    citation_lines = "\n".join(
        f"[{item['id']}] {item['title']} - {item['url']}" for item in citation_catalog
    )

    user_prompt = (
        f"Question: {state.question}\n\n"
        "Writing requirements:\n"
        "1) answer the question directly first;\n"
        "2) support claims with evidence;\n"
        "3) when evidence is limited or conflicting, use cautious wording and avoid absolute statements;\n"
        "4) explicitly state uncertainty and what evidence is still missing;\n"
        "5) output format:\n"
        "<think>brief reasoning</think>\n"
        "<answer>final answer</answer>\n"
        "6) Citation requirements:\n"
        "- Use numeric inline citations like [1], [2].\n"
        "- Every key conclusion sentence must include at least one [n] citation.\n"
        "- Do not use markdown links in body.\n"
        "- Include at least 6 references.\n"
        "- If answer body is Chinese, use section title '参考文献：'.\n"
        "- If answer body is English, use section title 'References:'.\n"
        "- Append numbered URL entries under that section.\n"
        "- Use only URLs from Evidence, Read Sources, or Sources.\n\n"
        "Available citation catalog (use these numbers only):\n"
        f"{citation_lines}\n\n"
        f"Notes:\n{json.dumps(state.notes, ensure_ascii=False, indent=2)}\n\n"
        f"Evidence:\n{json.dumps(state.evidence, ensure_ascii=False, indent=2)}\n\n"
        f"Read Sources:\n{json.dumps(state.read_sources, ensure_ascii=False, indent=2)}\n\n"
        f"Sources:\n{json.dumps(state.sources, ensure_ascii=False, indent=2)}"
    )
    return llm.chat(SYNTHESIZE_SYSTEM_PROMPT, user_prompt)


def run_research(question: str, settings: Settings, verbose: bool = True) -> dict:
    llm = LLMClient(
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
        model=settings.openai_model,
    )
    state = ResearchState(question=question)

    for step_id in range(1, settings.max_steps + 1):
        planner_raw = llm.chat(PLANNER_SYSTEM_PROMPT, planner_user_prompt(state))
        plan = extract_json_block(planner_raw)

        action = (plan.get("action") or "").strip().lower()
        forced_action = False
        force_reason_code = ""

        if step_id <= 5:
            has_read_in_first_five = any(
                s.get("step", 0) <= 5 and s.get("action") == "read" for s in state.steps
            )
            if not has_read_in_first_five and action != "read":
                has_candidate_url = bool(
                    pick_unvisited_url(state.sources, state.tried_urls, settings.source_policy)
                )
                if has_candidate_url or step_id == 5:
                    action = "read"
                    forced_action = True
                    force_reason_code = "force_read_before_step5"

        if state.steps:
            prev_step = state.steps[-1]
            prev_was_search = prev_step.get("action") == "search"
            prev_has_new_results = int(prev_step.get("new_results") or 0) > 0
            if prev_was_search and prev_has_new_results and action != "read":
                if state.pending_read_urls:
                    action = "read"
                    forced_action = True
                    force_reason_code = "force_read_pending_sources"

        # With short budgets (e.g., max_steps=5), ensure at least two read rounds before finalization.
        if settings.max_steps <= 5 and step_id == max(1, settings.max_steps - 1) and action != "read":
            read_steps_done = sum(1 for s in state.steps if s.get("action") == "read")
            has_candidate_url = bool(
                state.pending_read_urls
                or pick_unvisited_url(state.sources, state.tried_urls, settings.source_policy)
            )
            if read_steps_done < 2 and has_candidate_url:
                action = "read"
                forced_action = True
                force_reason_code = "force_second_read_before_last"

        # Never waste the last step on a pure search.
        if step_id == settings.max_steps and action in {"search", "reflect"}:
            has_candidate_url = bool(
                state.pending_read_urls
                or pick_unvisited_url(state.sources, state.tried_urls, settings.source_policy)
            )
            if has_candidate_url:
                action = "read"
                forced_action = True
                force_reason_code = "force_read_on_last_step"
            else:
                action = "synthesize"
                forced_action = True
                force_reason_code = "force_synthesize_on_last_step"

        why = (plan.get("why") or "").strip()
        sub_goal = (plan.get("sub_goal") or "").strip()
        plan_gaps = dedupe_keep_order(plan.get("knowledge_gaps") or state.knowledge_gaps, limit=8)
        if plan_gaps:
            state.knowledge_gaps = plan_gaps
        if sub_goal:
            state.todo_queue = dedupe_keep_order([sub_goal] + state.todo_queue, limit=8)

        step_log = {
            "step": step_id,
            "action": action,
            "why": why,
            "sub_goal": sub_goal,
            "knowledge_gaps": list(state.knowledge_gaps),
            "time": datetime.now().isoformat(timespec="seconds"),
            "forced_action": forced_action,
            "reason_code": force_reason_code,
        }

        if verbose:
            print(f"\n[Step {step_id}] action={action} why={why}")
            if sub_goal:
                print(f"  sub_goal: {sub_goal}")

        observation = ""

        if action == "search":
            raw_queries = plan.get("search_queries") or []
            if isinstance(raw_queries, str):
                raw_queries = [raw_queries]
            queries = dedupe_keep_order(raw_queries, limit=2) or [state.question]
            if _query_decompose_enabled():
                queries = _topic_decompose_queries(
                    question=state.question,
                    seed_queries=queries,
                    limit=_query_decompose_limit(),
                )

            planner_mode = (plan.get("search_mode") or "").strip().lower()
            if planner_mode in {"web", "scholar", "hybrid"}:
                search_mode = planner_mode
            else:
                search_mode = settings.search_mode

            if search_mode == "hybrid" and not looks_academic_question(state.question):
                use_web = True
                use_scholar = False
            else:
                use_web = search_mode in {"web", "hybrid"}
                use_scholar = search_mode in {"scholar", "hybrid"}

            all_results: list[dict] = []
            search_errors: list[str] = []
            for query in queries:
                if use_web:
                    try:
                        web_results = search_web(
                            query,
                            max_results=settings.max_search_results,
                            source_policy=settings.source_policy,
                        )
                        all_results.extend(web_results)
                    except Exception as exc:
                        search_errors.append(f"web query failed: {query}; error: {exc}")

                if use_scholar:
                    try:
                        scholar_results = search_scholar(
                            query,
                            max_results=settings.max_scholar_results,
                            source_policy=settings.source_policy,
                        )
                        all_results.extend(scholar_results)
                    except Exception as exc:
                        search_errors.append(f"scholar query failed: {query}; error: {exc}")

            before = len(state.sources)
            state.sources = merge_sources(state.sources, all_results)
            added_urls = [item.get("url", "").strip() for item in state.sources[before:]]
            _enqueue_pending_urls(state, added_urls)

            step_log["queries"] = queries
            step_log["search_mode"] = search_mode
            step_log["new_results"] = len(all_results)
            step_log["pending_read_count"] = len(state.pending_read_urls)
            if search_errors:
                step_log["search_errors"] = search_errors
                state.notes.extend(search_errors)
            observation = f"searched {len(queries)} queries; collected {len(all_results)} raw results"
            if verbose:
                print(f"  search queries: {queries}")
                print(f"  raw results: {len(all_results)}")
                print(f"  pending read urls: {len(state.pending_read_urls)}")
                if search_errors:
                    print(f"  search errors: {len(search_errors)}")

        elif action == "read":
            preferred_url = (plan.get("url") or "").strip()
            read_all_mode = _read_all_from_search_enabled()
            if read_all_mode:
                urls = _dequeue_all_urls(state, preferred_url)
                batch_size = len(urls)
            else:
                batch_size = _read_batch_size()
                urls = _dequeue_next_urls(state, preferred_url, batch_size=batch_size)
            workers = _read_batch_workers(len(urls))

            read_ok = False
            fetch_ok = False
            evidence_ok = False

            if not urls:
                note = "No unread URL available to read."
                state.notes.append(note)
                step_log["url"] = ""
                step_log["urls"] = []
                step_log["read_all_mode"] = read_all_mode
                step_log["note"] = note
                step_log["fetch_ok"] = False
                step_log["evidence_ok"] = False
                step_log["read_ok"] = False
                step_log["pending_read_count"] = len(state.pending_read_urls)
                observation = note
            else:
                for url in urls:
                    state.tried_urls.add(url)

                page_bundle_map, fetch_errors = _fetch_many_pages(
                    urls=urls,
                    max_chars=settings.max_page_chars,
                    max_workers=workers,
                )

                per_url_results: list[dict] = []
                backup_queries_all: list[str] = []
                backup_new_total = 0
                note_blocks: list[str] = []
                fetch_ok_count = 0
                evidence_ok_count = 0

                for url in urls:
                    source_meta = _find_source_meta(state.sources, url)
                    current_fetch_ok = False
                    current_evidence_ok = False
                    current_read_ok = False
                    chosen_title = ""

                    page_bundle = page_bundle_map.get(url) or {}
                    page_text = str(page_bundle.get("text") or "").strip()
                    page_title = str(page_bundle.get("title") or "").strip()
                    if page_text:
                        current_fetch_ok = len(page_text) >= 300

                    if current_fetch_ok:
                        fetch_ok_count += 1
                        extracted = _extract_page_evidence(llm, state.question, url, page_text)
                        summary = extracted.get("summary", "")
                        reason = extracted.get("reason", "")
                        key_facts = extracted.get("key_facts", [])
                        evidence_count = int(extracted.get("evidence_count", 0) or 0)
                        is_relevant = bool(extracted.get("is_relevant", False))

                        note_lines = []
                        if summary:
                            note_lines.append(summary)
                        if key_facts:
                            note_lines.append("Key facts:")
                            note_lines.extend([f"- {fact}" for fact in key_facts])
                        if reason:
                            note_lines.append(f"Reason: {reason}")
                        current_note = "\n".join(note_lines).strip() or _summarize_page(
                            llm, state.question, url, page_text
                        )

                        current_evidence_ok = (
                            (is_relevant or bool(key_facts))
                            and evidence_count > 0
                            and not _is_low_value_note(current_note)
                        )
                        if current_evidence_ok:
                            evidence_ok_count += 1
                        current_read_ok = current_fetch_ok and current_evidence_ok
                        chosen_title = _best_source_title(
                            url=url,
                            page_title=page_title,
                            source_meta=source_meta,
                            summary=current_note,
                        )

                        # Relaxed citation pool gate: fetch_ok=True is enough to enter read_sources.
                        if not any((item.get("url") or "") == url for item in state.read_sources):
                            state.read_sources.append(
                                {
                                    "url": url,
                                    "title": chosen_title,
                                    "snippet": (source_meta.get("snippet") or "").strip(),
                                    "summary": current_note,
                                    "fetch_ok": True,
                                    "evidence_ok": current_evidence_ok,
                                }
                            )

                        if current_read_ok:
                            state.visited_urls.add(url)
                            if not any((item.get("url") or "") == url for item in state.evidence):
                                state.evidence.append(
                                    {
                                        "url": url,
                                        "title": chosen_title,
                                        "snippet": (source_meta.get("snippet") or "").strip(),
                                        "summary": current_note,
                                    }
                                )
                        else:
                            state.failed_urls.add(url)
                    else:
                        current_note = fetch_errors.get(url) or f"Failed to read {url}: empty page text"
                        state.failed_urls.add(url)
                        # Try backup re-search only when fetch failed.
                        backup_queries, backup_new = _maybe_research_with_title(
                            state=state,
                            settings=settings,
                            source_meta=source_meta,
                            failed_url=url,
                        )
                        if backup_queries:
                            backup_queries_all.extend(backup_queries)
                            backup_new_total += backup_new

                    read_ok = read_ok or current_read_ok
                    fetch_ok = fetch_ok or current_fetch_ok
                    evidence_ok = evidence_ok or current_evidence_ok
                    note_blocks.append(f"{url}\n{current_note}")
                    per_url_results.append(
                        {
                            "url": url,
                            "fetch_ok": current_fetch_ok,
                            "evidence_ok": current_evidence_ok,
                            "read_ok": current_read_ok,
                            "note": current_note,
                        }
                    )

                note = "\n\n---\n\n".join(note_blocks)
                state.notes.append(note)

                step_log["url"] = urls[0]
                step_log["urls"] = urls
                step_log["read_all_mode"] = read_all_mode
                step_log["batch_workers"] = workers
                step_log["note"] = note
                step_log["fetch_ok"] = fetch_ok
                step_log["evidence_ok"] = evidence_ok
                step_log["read_ok"] = read_ok
                step_log["fetch_ok_count"] = fetch_ok_count
                step_log["evidence_ok_count"] = evidence_ok_count
                step_log["read_count"] = len(urls)
                step_log["read_results"] = per_url_results
                step_log["pending_read_count"] = len(state.pending_read_urls)
                if backup_queries_all:
                    step_log["backup_queries"] = dedupe_keep_order(backup_queries_all, limit=8)
                    step_log["backup_new_results"] = backup_new_total
                    step_log["pending_read_count"] = len(state.pending_read_urls)
                observation = note
            if verbose:
                print(f"  read urls: {urls}")
                print(f"  batch workers: {workers}")
                print(f"  pending read urls: {len(state.pending_read_urls)}")

        elif action == "reflect":
            observation = "manual reflection requested by planner"
            step_log["note"] = observation
            if verbose:
                print("  reflect-only step.")

        elif action == "synthesize":
            draft = _synthesize_answer(llm, state)
            state.draft_answer = ensure_answer_tagged(draft)
            step_log["draft"] = state.draft_answer
            observation = "draft answer updated"
            if verbose:
                print("  synthesized draft answer.")

        elif action == "finish":
            if not state.draft_answer:
                state.draft_answer = ensure_answer_tagged(_synthesize_answer(llm, state))
            step_log["note"] = "planner decided to finish"
            state.steps.append(step_log)
            return build_result_payload(state)

        else:
            fallback_note = f"Unknown action from planner: {action}"
            state.notes.append(fallback_note)
            step_log["note"] = fallback_note
            observation = fallback_note

        try:
            reflection = reflect_step(llm, state, step_id, plan, observation)
            state.reflections.append(reflection)
            state.knowledge_gaps = reflection["updated_gaps"]
            state.confidence = reflection["confidence"]
            if reflection.get("next_hint"):
                state.todo_queue = dedupe_keep_order([reflection["next_hint"]] + state.todo_queue, limit=8)
            step_log["reflection"] = reflection
            if verbose:
                print(
                    "  reflection: "
                    f"sufficient={reflection['is_sufficient']} "
                    f"confidence={reflection['confidence']:.2f}"
                )
        except Exception as exc:
            reflection_error = f"Reflection parse failed: {exc}"
            state.notes.append(reflection_error)
            step_log["reflection_error"] = reflection_error

        if bool(plan.get("finish_if_done")) and state.confidence >= 0.8:
            if not state.draft_answer:
                state.draft_answer = ensure_answer_tagged(_synthesize_answer(llm, state))
            state.steps.append(step_log)
            return build_result_payload(state)

        state.steps.append(step_log)

    if not state.draft_answer:
        state.draft_answer = ensure_answer_tagged(_synthesize_answer(llm, state))

    return build_result_payload(state)
