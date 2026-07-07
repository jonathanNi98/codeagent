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

from core.config import Config, get_config, make_client
from tools import dispatch_tool, tools_for
from core.utils import call_llm, AgentTurnError

# ----------------------------------------------------------------------------
# System prompt
# ----------------------------------------------------------------------------
PLANNER_SYSTEM_PROMPT = """\
You are the Planner agent. You investigae a codebase using ONLY the read-only tools provided.
The provided tools are: list_file, read_file, search_file, run_command (read-only commands), git_diff.
You MUST NOT modify any file.

When done, output exactly ONE JSON object and NOTHING else (no prose, no code fences):
{
  "needs_code_change": <bool>,
  "summary": "<1-2 sentences>",
  "steps": ["..."],
  "files_to_modify": ["..."]
}
- Questions/explanations -> needs_code_change=false, put the answer in summary.
- Coding requests -> needs_code_change=true, list every file to edit in files_to_modify.

You can cap your investigation at ~8 tool calls — be efficient, don't re-read what you already read.
"""


# ----------------------------------------------------------------------------
# Agent loop
# ----------------------------------------------------------------------------

def run(user_msg: str, session_context: str = "") -> str:
    """Run the Planner on ``user_msg`` and return its final plan text.

    Args:
        user_msg: the user's natural-language request.
        session_context: optional prior session context.

    Returns:
        The Planner's final assistant text — the plan that the Coder will implement.

    """

    cfg = get_config()
    client = make_client(cfg)
    messages: list[dict[str, Any]] = []
    if session_context:
        content = f"{session_context}\n{user_msg}"
    else:
        content = user_msg
    messages.append({"role": "user", "content": content})
    
    for _ in range(cfg.max_tool_iterations):
        # ----------------------------------------------------------------------
        # resp shape — verified by a real MiniMax-M3 call:
        #
        #   type(resp)        -> anthropic.types.Message
        #   resp.stop_reason  -> "end_turn" | "tool_use" | "max_tokens"
        #   resp.content      -> list[ContentBlock]   (ALWAYS a list, even if 1)
        #
        #   Real repr example (text-only response, no tools):
        #     Message(
        #       id='msg_...',  type='message',  role='assistant',
        #       model='MiniMax-M3',
        #       stop_reason='end_turn',
        #       content=[
        #         TextBlock(citations=None,
        #                   text="I'm MiniMax-M3, an AI assistant made by MiniMax.",
        #                   type='text'),
        #       ],
        #       usage=Usage(input_tokens=14, output_tokens=18, ...),
        #     )
        #
        #   When tools are passed, content may also contain ToolUseBlocks:
        #     ToolUseBlock(type='tool_use', id='toolu_01ABC',
        #                  name='list_file', input={'path': '.'})
        # ----------------------------------------------------------------------
        resp = call_llm(
            client,
            model=cfg.model_name,
            system=PLANNER_SYSTEM_PROMPT,
            messages=messages,
            tools=tools_for("planner"),
            max_tokens=4096,
        )
        
        print(f"[debug] stop_reason  = {resp.stop_reason!r}")
        print(f"[debug] content_len  = {len(resp.content)}")
        try:
            print(json.dumps(resp.model_dump(), indent=2, ensure_ascii=False))
        except Exception as e:
            print(f"[debug] model_dump failed: {e!r}")
            print(repr(resp))
        print("[debug] " + "-" * 50)

        # resp.stop_reason ∈ {"end_turn", "tool_use", "max_tokens"}
        if resp.stop_reason == "end_turn":
            # No tool use -> final answer.
            return "".join(
                b.text for b in resp.content
                if getattr(b, "type", None) == "text"
            )
        if resp.stop_reason != "tool_use":
            raise AgentTurnError(f"unexpected stop_reason: {resp.stop_reason!r}")

        messages.append({"role": "assistant", "content": resp.content})

        tool_results = []
        for block in resp.content:
            if (getattr(block, "type", None) == "tool_use"):
                result = dispatch_tool(block.name, block.input)
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
