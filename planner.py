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
import config
from tools import dispatch_tool, tools_for


# ----------------------------------------------------------------------------
# System prompt
# ----------------------------------------------------------------------------
PLANNER_SYSTEM_PROMPT = """\
You are the Planner agent. You investigae a codebase using ONLY the read-only tools provided.
The provided tools are: list_file, read_file, search_file, run_command (read-only commands), git_diff.
You MUST NOT modify any file.
After enough investigation, output a numbered plan, one step per line, then a final section 'fields to be modify:'
listing the paths you expect to change, after that section, stop calling tools.
You can cap your investigation at ~8 tool calls — be efficient, don't re-read what you already read.
"""


# ----------------------------------------------------------------------------
# Agent loop
# ----------------------------------------------------------------------------

def run(user_msg: str, history: list[dict[str, Any]] | None = None) -> str:
    """Run the Planner on ``user_msg`` and return its final plan text.

    Args:
        user_msg: the user's natural-language request.
        history:  optional prior messages (each a dict in OpenAI chat format
                  with 'role' and 'content'). Use [] for a fresh session.

    Returns:
        The Planner's final assistant text — the plan that the Coder will implement.
    
    

    """
    cfg = config.get_config()
    client = make_client(cfg)
    messages: list[dict[str, Any]] = list(history or [])
    messages.append({"role": "user", "content": user_msg})
    
    while True:
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
        resp = client.messages.create(
            model=cfg.model_name,
            system=PLANNER_SYSTEM_PROMPT,
            messages=messages,
            tools=tools_for("planner"),
            max_tokens=4096,
        )
        
        # DEBUG: 临时调试——看 resp 里面是什么,跑通后删掉
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
