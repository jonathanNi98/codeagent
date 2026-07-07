"""
coder.py — Coder agent.

Role: receive a plan from the Planner and edit files to implement it.
Has all 6 tools available, including write_file.

What you fill in:
  - CODER_SYSTEM_PROMPT — instructions for the LLM
  - run(plan_text, history) — same agent-loop shape as planner.run, but with
    tools_for("coder") instead of tools_for("planner").
"""
from __future__ import annotations

import json
from typing import Any

from core.config import Config, get_config, make_client
from tools import dispatch_tool, tools_for
from core.utils import call_llm
from core.errors import AgentTurnError


# ----------------------------------------------------------------------------
# System prompt
# ----------------------------------------------------------------------------
CODER_SYSTEM_PROMPT = """\
    You are the Coder agent. You receive a numbered plan and must implement
    it by editing files in the working directory.

    REFUSAL RULE: If the input does Not look like a numbered plan with a "files to modify" section listing path,
    do Not call any tools. Reply with one sentence: "Not a plan, skipping coder." and stop. Do not invent
    work based on role description or any other context. Only implement what is in the plan.

    Available tools: list_file, read_file, search_file, write_file,
    run_command, git_diff.
    
    Allowlist rule: you may call write_file only on paths listed in the "files to modify" section of the plan. Writes to
    any other path will be rejected by the tool with [ERROR]. When rejected, do Not retry the same path, stop calling
    tools and report.
    
    Workflow when input IS a plan:
    1) read_file the target file.
    2) write_file with the new full contents.
    3) git_diff to verify. Repeat per file.

    Keep edits minimal and surgical — only change what the plan calls for.
    Don't refactor unrelated code.
    After your last write_file, call git_diff once more, then output a
    brief summary in plain text and STOP calling tools.
"""

# ----------------------------------------------------------------------------
# Agent loop
# ----------------------------------------------------------------------------

def run(plan_text: str, allowed_files: frozenset[str] | None = None, session_context: str = "", test_feedback: str = "") -> str:
    """Run the Coder on ``plan_text`` and return its final summary text.

    Args:
        plan_text: the plan from the Planner.
        allowed_files: optional set of files the Coder is allowed to modify.
        session_context: optional prior session context.
        test_feedback: optional prior test failure output (for retry loop).

    Returns:
        The Coder's final assistant text — a brief summary of what it changed.

    Implementation note: this is structurally identical to planner.run —
    copy that skeleton and swap tools_for("planner") for tools_for("coder").
    The only real difference is the system prompt and the initial user
    message ("implement this plan:\n\n{plan_text}").
    """

    feedback_block = (
        f"\n\n=== Previous test failure (please fix) ===\n{test_feedback}\n"
        f"=== END ===\n\n"
        if test_feedback else ""
    )
    cfg: Config = get_config()
    client = make_client(cfg)

    messages: list[dict[str, Any]] = []
    prefix = f"{session_context}\n" if session_context else ""
    messages.append({"role": "user",
                     "content": f"{prefix}"
                                f"{feedback_block}"
                                f"Here is a plan to implement:\n\n{plan_text}\n\n"
                                f"Allowed files you may write to:\n"
                                f"  {sorted(allowed_files) if allowed_files else '[]'}\n\n"
                                f"Implement it by editing files. Use write_file to apply "
                                f"each change, then git_diff to verify. After the last "
                                f"write_file, call git_diff once more and stop calling tools, "
                                f"IMPORTANT: write_file will REJECT any path not in the allowed list. "
                                f"If you see [ERROR] on a write_file, do NOT retry the same path — stop "
                                f"then output a brief summary."})
    
    for _ in range(cfg.max_tool_iterations):
        resp = call_llm(
            client,
            model=cfg.model_name,
            system=CODER_SYSTEM_PROMPT,
            messages=messages,
            tools=tools_for("coder"),
            max_tokens=4096,
        )

        if resp.stop_reason == "end_turn":
            return "".join(b.text for b in resp.content if getattr(b, "type", None) == "text")
        if resp.stop_reason != "tool_use":
            raise AgentTurnError(f"unexpected stop_reason: {resp.stop_reason!r}")

        messages.append({"role": "assistant", "content": resp.content})
        
        tool_results = []
        for block in resp.content:
            if getattr(block, "type", None) == "tool_use":
                result = dispatch_tool(block.name, block.input, allowed_files=allowed_files)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result,
                })
        messages.append({"role": "user", "content": tool_results})

    raise AgentTurnError(
        f"exhausted {cfg.max_tool_iterations} tool-call iterations without end_turn; "
        f"model may be stuck in a tool loop"
    )