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

import pipeline
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
    cmd = line.strip().lower()
    if cmd in ("/quit", "/exit", "/q"):
        return True
    elif cmd == "/help":
        print(HELP_TEXT)
    elif cmd == "reset":
        print("clear conversation history")
    elif cmd == "/diff":
        print("show the most recent git diff")

def render_result(result: pipeline.PipelineResult) -> None:
    """Pretty-print the pipeline outcome.

    Suggested:
        for stage in result.stages:
            marker = '✅' if stage.ok else '❌'
            print(f"{marker} {stage.name}: {stage.error or 'ok'}")
            if stage.artifact:
                panel(stage.artifact, title=f"📦 {stage.name} output")
    """
    # TODO: implement stage-by-stage rendering.
    # You can keep it minimal (just print markers) or full (panels per stage).
    raise NotImplementedError(
        "TODO: iterate result.stages, print ok/err marker, panel each artifact."
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
                result = pipeline.run(line)
            render_result(result)
        except Exception as e:
            panel(f"{type(e).__name__}: {e}", title="❌ pipeline error", color="red")


if __name__ == "__main__":
    main()
