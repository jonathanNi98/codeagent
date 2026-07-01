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
#
# Suggested content:
#
#   - "You are the Coder agent. You receive a numbered plan and must implement
#      it by editing files in the working directory."
#   - "Available tools: list_file, read_file, search_file, write_file,
#      run_command, git_diff."
#   - "Workflow: 1) read_file the target file. 2) write_file with the new full
#      contents. 3) git_diff to verify. Repeat per file."
#   - "Keep edits minimal and surgical — only change what the plan calls for.
#      Don't refactor unrelated code."
#   - "After your last write_file, call git_diff once more, then output a
#      brief summary in plain text and STOP calling tools."
#
CODER_SYSTEM_PROMPT = """\
TODO: write the Coder system prompt here. See docstring/comment above for guidance.
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
    raise NotImplementedError(
        "TODO: implement the Coder agent loop. Mirror Planner.run; "
        "swap tools_for('planner') -> tools_for('coder')."
    )
