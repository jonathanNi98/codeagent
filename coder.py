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

from config import Config, get_config, make_client
from tools import dispatch_tool, tools_for


# ----------------------------------------------------------------------------
# System prompt — TODO
# ----------------------------------------------------------------------------
CODER_SYSTEM_PROMPT = """\
    You are the Coder agent. You receive a numbered plan and must implement
    it by editing files in the working directory.
    Available tools: list_file, read_file, search_file, write_file,
    run_command, git_diff.
    Workflow: 1) read_file the target file. 2) write_file with the new full
    contents. 3) git_diff to verify. Repeat per file.
    Keep edits minimal and surgical — only change what the plan calls for.
    Don't refactor unrelated code.
    After your last write_file, call git_diff once more, then output a
    brief summary in plain text and STOP calling tools.
"""


# ----------------------------------------------------------------------------
# Agent loop — TODO
# ----------------------------------------------------------------------------

def run(plan_text: str, history: list[dict[str, Any]] | None = None) -> str:
    """Run the Coder on ``plan_text`` and return its final summary text.

    Args:
        plan_text: the plan from the Planner.
        history:   optional prior messages.

    Returns:
        The Coder's final assistant text — a brief summary of what it changed.

    Implementation note: this is structurally identical to planner.run —
    copy that skeleton and swap tools_for("planner") for tools_for("coder").
    The only real difference is the system prompt and the initial user
    message ("implement this plan:\n\n{plan_text}").
    """
    cfg: Config = get_config()
    client = make_client(cfg)
    
    messages: list[dict[str, Any]] = list(history or [])
    messages.append({"role": "user",
                     "content": f"Here is a plan to implement:\n\n{plan_text}\n\n"
                                f"Implement it by editing files. Use write_file to apply "
                                f"each change, then git_diff to verify. After the last "
                                f"write_file, call git_diff once more and stop calling tools, "
                                f"then output a brief summary."})    
    
    while True:
        resp = client.messages.create(
            model=cfg.model_name,
            system=CODER_SYSTEM_PROMPT,
            messages=messages,
            tools=tools_for("coder"),
            max_tokens=4096,
        )
        
        if resp.stop_reason == "end_turn":
            return "".join(b.text for b in resp.content if getattr(b, "type", None) == "text")
        messages.append({"role": "assistant", "content": resp.content})
        
        tool_results = []
        for block in resp.content:
            if getattr(block, "type", None) == "tool_use":
                result = dispatch_tool(block.name, block.input)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result,
                })
        messages.append({"role": "user", "content": tool_results})
            