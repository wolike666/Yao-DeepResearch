from __future__ import annotations

import json

from .state import ResearchState


def format_state_for_planner(state: ResearchState) -> str:
    latest_notes = state.notes[-5:]
    latest_sources = state.sources[-5:]
    return json.dumps(
        {
            "question": state.question,
            "step_count": len(state.steps),
            "todo_queue": state.todo_queue[:6],
            "knowledge_gaps": state.knowledge_gaps[:6],
            "visited_url_count": len(state.visited_urls),
            "latest_notes": latest_notes,
            "latest_sources": latest_sources,
            "current_draft": state.draft_answer,
            "confidence": state.confidence,
        },
        ensure_ascii=False,
        indent=2,
    )


def planner_user_prompt(state: ResearchState) -> str:
    return (
        "请根据当前研究状态，输出下一步计划。\n"
        "规划要求：\n"
        "1) 子目标必须和原问题直接相关；\n"
        "2) 优先补齐关键事实缺口；\n"
        "3) 查询语句要具体、可执行；\n"
        "4) 若证据不足，不得选择 finish；\n"
        "5) 前 5 步内至少执行 1 次 read。\n"
        "请严格遵循以下 JSON schema（字段名必须保持英文）:\n"
        "{\n"
        '  "sub_goal": "本轮要证明/查明的子目标",\n'
        '  "knowledge_gaps": ["信息缺口1", "信息缺口2"],\n'
        '  "action": "search|read|reflect|synthesize|finish",\n'
        '  "why": "简短原因",\n'
        '  "search_queries": ["查询1", "查询2"],\n'
        '  "search_mode": "web|scholar|hybrid",\n'
        '  "url": "当 action=read 时优先读取的链接",\n'
        '  "finish_if_done": false\n'
        "}\n\n"
        f"研究状态:\n{format_state_for_planner(state)}"
    )
