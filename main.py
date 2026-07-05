"""
main.py — REPL entry point.

Reads user input line by line, runs each through ``pipeline.run(...)``,
prints the result, and loops.

Built-in slash commands (handled in ``handle_command``):
  /help    show command list
  /quit    exit (also: /exit, /q)
  /reset   clear conversation history (placeholder in MVP)
  /diff    show the most recent git diff (placeholder in MVP)

Any line not starting with ``/`` is treated as a task message.

What you fill in:
  - If you want the welcome banner to be fancier (panel with version, etc.)
  - If you want /diff to actually surface pipeline's last artifact
  - If you want to per-stage print ok/err lines and render each stage's panel
"""
from __future__ import annotations

import sys

from core import pipeline
from ui import banner, panel, prompt, spinner
from core.history import SessionTurn, compact_history, format_session_context

session_history: list[SessionTurn] = []

HELP_TEXT = """\
Available commands:
  /help   show this help
  /quit   exit the REPL (also /exit, /q)
  /reset  clear conversation history (placeholder in MVP)
  /diff   show the most recent git diff (placeholder in MVP)

Otherwise just type a task in natural language. Press Ctrl+D to exit.
"""

def handle_command(line: str) -> bool:
    """return a slash command handler result: True if the Repl should exit, False otherwise."""
    part = line.strip().split()
    cmd = part[0]
    args = part[1:]
    print(f"[debug] cmd={cmd!r}  args={args!r}")

    if cmd in ("/quit", "/exit", "/q"):
        return True
    elif cmd == "/help":
        print(HELP_TEXT)
    elif cmd == "/reset":
        session_history.clear()
    elif cmd == "/diff":
        print("show the most recent git diff")
    else:
        print(f"unknown command: {line}")
    return False

def render_result(result: pipeline.PipelineResult) -> None:
    """Pretty-print the pipeline outcome as ok/err markers + an overall verdict.

    Note: pipeline.run already calls ui.panel() inline for each stage's
    artifact as it runs, so we only need to print markers + summary here.
    """
    if not result.stages:
        print("(no stages ran)")
        return

    for stage in result.stages:
        marker = "✅" if stage.ok else "❌"
        line = f"{marker} {stage.name}"
        if stage.error:
            line += f": {stage.error}"
        print(line)

    print()
    overall = "✅ all stages passed" if result.ok else "❌ some stages failed"
    print(f"[{overall}]")

def _extract_turn(user_msg: str, result: pipeline.PipelineResult) -> SessionTurn:
    by_name = {s.name: s for s in result.stages}
    
    plan_stage = by_name.get("planner")
    if plan_stage and plan_stage.ok:
        try:
            from core.planner_schema import parse_plan
            plan_summary = parse_plan(plan_stage.artifact).summary
        except Exception:
            art = plan_stage.artifact or ""
            plan_summary = art[:200] + ("..." if len(art) > 200 else "")
    else:
        err = plan_stage.error if plan_stage else "no stage"
        plan_summary = f"[planner failed: {err}]"
        
    coder_stage = by_name.get("coder")
    if coder_stage is None:
        code_summary = "[skipped: needs_code_change=false]"
    elif coder_stage.ok:
        code_summary = coder_stage.artifact or "(empty)"
    else:
        code_summary = f"[coder failed: {coder_stage.error}]"
        
    runner_stage = by_name.get("runner")
    if runner_stage is None:
        test_outcome = "[skipped]"
    elif runner_stage.ok:
        test_outcome = "✅ passed"
    else:
        test_outcome = f"❌ failed: {runner_stage.error or 'see output'}"

    return SessionTurn(
        user_msg=user_msg,
        plan_summary=plan_summary,
        code_summary=code_summary,
        test_outcome=test_outcome,
    )

def main() -> None:
    """REPL loop. Catches per-pipeline exceptions so the user can keep going."""
    banner("codeagent")

    while True:
        try:
            line = prompt()
        except (EOFError, KeyboardInterrupt):
            print("\nbye.")
            return

        line = line.strip()
        if not line:
            continue

        if line.startswith("/"):
            if handle_command(line):
                return
            continue

        try:
            with spinner("thinking…"):
                ctx = format_session_context(compact_history(session_history))
                result = pipeline.run(line, session_context=ctx)
                session_history.append(_extract_turn(line, result))

            render_result(result)
        except Exception as e:
            panel(f"{type(e).__name__}: {e}", title="❌ pipeline error", color="red")


if __name__ == "__main__":
    main()
