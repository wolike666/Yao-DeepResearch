from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ResearchState:
    question: str
    steps: list[dict] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    sources: list[dict] = field(default_factory=list)
    evidence: list[dict] = field(default_factory=list)
    read_sources: list[dict] = field(default_factory=list)
    reflections: list[dict] = field(default_factory=list)
    todo_queue: list[str] = field(default_factory=list)
    knowledge_gaps: list[str] = field(default_factory=list)
    visited_urls: set[str] = field(default_factory=set)
    tried_urls: set[str] = field(default_factory=set)
    failed_urls: set[str] = field(default_factory=set)
    backup_queries: set[str] = field(default_factory=set)
    pending_read_urls: list[str] = field(default_factory=list)
    confidence: float = 0.0
    draft_answer: str = ""
