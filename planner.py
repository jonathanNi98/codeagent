"""
planner.py — Planner agent.

Role: investigate the codebase (read-only), produce a textual plan that the
Coder agent will then implement.

Available tools (no write access):
  list_file, read_file, search_file, run_command, git_diff

What you fill in:
  - PLANNER_SYSTEM_PROMPT  — instructions for the LLM
  - run(user_msg, history) — the agent loop (LLM ↔ tools until end-of-turn)
"""
from __future__ import annotations

import json
from typing import Any

from config import Config, get_config, make_client
from tools import dispatch_tool, tools_for


# ----------------------------------------------------------------------------
# System prompt — TODO
# ----------------------------------------------------------------------------
#
# Suggested content (write it your own way):
#
#   - "You are the Planner agent. You investigate a codebase using ONLY the
#      read-only tools provided (list_file, read_file, search_file,
#      run_command with read-only commands, git_diff). You MUST NOT modify any
#      file."
#   - "After enough investigation, output a numbered plan, one step per line,
#      then a final section 'Files to modify:' listing the paths you expect to
#      change. After that section, stop calling tools."
#   - "Cap your investigation at ~8 tool calls — be efficient, don't re-read
#      what you already read."
#
PLANNER_SYSTEM_PROMPT = """\
TODO: write the Planner system prompt here. See docstring/comment above for guidance.
"""


# ----------------------------------------------------------------------------
# Agent loop — TODO
# ----------------------------------------------------------------------------

def run(user_msg: str, history: list[dict[str, Any]] | None = None) -> str:
    """Run the Planner on ``user_msg`` and return its final plan text.

    Args:
        user_msg: the user's natural-language request.
        history:  optional prior messages (each a dict in OpenAI chat format
                  with 'role' and 'content'). Use [] for a fresh session.

    Returns:
        The Planner's final assistant text — the plan that the Coder will implement.

    Pseudocode for the OpenAI-compatible SDK (default expectation):

        cfg: Config = get_config()
        client = make_client(cfg)

        messages: list[dict] = list(history or [])
        messages.append({"role": "user", "content": user_msg})

        while True:
            resp = client.chat.completions.create(
                model=cfg.model_name,
                messages=[
                    {"role": "system", "content": PLANNER_SYSTEM_PROMPT},
                    *messages,
                ],
                tools=tools_for("planner"),
            )
            choice = resp.choices[0]
            assistant_msg = choice.message    # has .content and .tool_calls
            messages.append(assistant_msg)    # OpenAI requires echoing back

            if not assistant_msg.tool_calls:           # final answer
                return assistant_msg.content or ""

            for tc in assistant_msg.tool_calls:
                args = json.loads(tc.function.arguments or "{}")
                # Optional: forward tool_call_id / name to dispatch_tool
                result = dispatch_tool(tc.function.name, args)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result,
                })
    """
    raise NotImplementedError(
        "TODO: implement the Planner agent loop. See docstring pseudocode."
    )
