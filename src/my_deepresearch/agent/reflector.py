from __future__ import annotations

import json

from ..llm_client import LLMClient
from ..prompts import REFLECT_SYSTEM_PROMPT
from .state import ResearchState
from .utils import clamp_confidence, dedupe_keep_order, extract_json_block, record_llm_usage


def reflect_step(
    llm: LLMClient,
    state: ResearchState,
    step_id: int,
    plan: dict,
    observation: str,
) -> dict:
    user_prompt = (
        "请评估最新一步是否让研究达到可收敛状态。\n"
        "评估标准：相关性、可信度、完整性、时效性。\n"
        "请返回严格 JSON（字段名必须保持英文）：\n"
        "{\n"
        '  "step": 0,\n'
        '  "is_sufficient": false,\n'
        '  "updated_gaps": ["信息缺口"],\n'
        '  "next_hint": "下一步建议",\n'
        '  "confidence": 0.0\n'
        "}\n\n"
        f"Step: {step_id}\n"
        f"Question: {state.question}\n"
        f"Plan: {json.dumps(plan, ensure_ascii=False)}\n"
        f"Observation: {observation}\n"
        f"Recent notes: {json.dumps(state.notes[-5:], ensure_ascii=False)}\n"
        f"Recent sources: {json.dumps(state.sources[-5:], ensure_ascii=False)}"
    )
    response = llm.chat(
        REFLECT_SYSTEM_PROMPT,
        user_prompt,
        usage_context={"purpose": "reflector", "step": step_id},
    )
    record_llm_usage(state, response["usage"])
    raw = response["content"]
    reflection = extract_json_block(raw)
    reflection["step"] = int(reflection.get("step") or step_id)
    reflection["is_sufficient"] = bool(reflection.get("is_sufficient", False))
    reflection["updated_gaps"] = dedupe_keep_order(
        reflection.get("updated_gaps") or state.knowledge_gaps,
        limit=8,
    )
    reflection["next_hint"] = (reflection.get("next_hint") or "").strip()
    reflection["confidence"] = clamp_confidence(reflection.get("confidence", state.confidence))
    return reflection
