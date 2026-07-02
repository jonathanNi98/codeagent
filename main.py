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
        print("clear conversation history")
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
                result = pipeline.run(line)
            render_result(result)
        except Exception as e:
            panel(f"{type(e).__name__}: {e}", title="❌ pipeline error", color="red")


if __name__ == "__main__":
    main()
