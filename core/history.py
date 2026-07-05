"""
History module for session-level history compression and rendering.

设计要点(摘自 Claude Code / hermes-agent 对照):
  - head anchor 永远保留第 1 轮(用户原始任务)
  - middle 用 per-turn 1-line heuristic 压缩(本轮,不调 LLM)
  - recent 保留最近 3 轮完整
  - LLM 摘要 / token 预算 / 防 thrash / 持久化 留作下一轮
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

@dataclass(frozen=True)
class SessionTurn:
    user_msg: str
    plan_summary: str
    code_summary: str
    test_outcome: str
    
@dataclass(frozen=True)
class CompactedHistory:
    head: SessionTurn | None
    middle_summaries: list[str]
    recent: list[SessionTurn]
    
def _truncate(s: str, n: int) -> str:
    s = (s or "").replace("\n", " ")
    return s if len(s) <= n else s[:n] + "..."
    
def summarize_turn_one_line(t: SessionTurn) -> str:
    user = _truncate(t.user_msg, 60)
    plan = _truncate(t.plan_summary, 60)
    if t.code_summary.startswith("[skipped"):
        coder = "[no code]"
    else:
        coder = _truncate(t.code_summary, 60)
    return f"User={user!r} | Plan={plan!r} | Coder={coder!r} | Tests={t.test_outcome}"

def compact_history(history: List[SessionTurn], *, protect_last_n: int = 3) -> CompactedHistory:
    if not history:
        return CompactedHistory(head=None, middle_summaries=[], recent=[])

    head = history[0]
    if len(history) <= 1 + protect_last_n:
        return CompactedHistory(head=head, middle_summaries=[], recent=history[1:])

    recent = history[-protect_last_n:]
    middle = history[1:-protect_last_n]
    middle_summaries = [summarize_turn_one_line(t) for t in middle]
    return CompactedHistory(head=head, middle_summaries=middle_summaries, recent=recent)
    
def _render_turn_block(t: SessionTurn) -> str:
    return (
        f"User: {t.user_msg}\n"
        f"Plan: {t.plan_summary}\n"
        f"Coder: {t.code_summary}\n"
        f"Tests: {t.test_outcome}"
    )
    
def format_session_context(compacted: CompactedHistory) ->str:
    if compacted.head is None and not compacted.recent and not compacted.middle_summaries:
        return ""
    
    lines = ["=== SESSION CONTEXT (prior turns; current request follows below) ==="]
    
    if compacted.head is not None:
        lines.append("")
        lines.append("[First turn — original task anchor]")
        lines.append(_render_turn_block(compacted.head))
        
    if compacted.middle_summaries:
        lines.append("")
        lines.append(f"[Earlier turns — {len(compacted.middle_summaries)} compressed to 1 line each]")
        for s in compacted.middle_summaries:
            lines.append(f"  {s}")
            
    if compacted.recent:
        lines.append("")
        lines.append(f"[Recent turns — last {len(compacted.recent)} in full]")
        for i, t in enumerate(compacted.recent, 1):
            lines.append(f"-- Turn {i}/{len(compacted.recent)} --")
            lines.append(_render_turn_block(t))
            
    lines.append("")
    lines.append("=== END SESSION CONTEXT ===")
    lines.append("")
    lines.append("=== CURRENT REQUEST ===")
    return "\n".join(lines)
