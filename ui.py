"""
ui.py — rich-based terminal rendering.

All public functions here are stubs you fill in. Call sites in pipeline.py
and main.py are already wired to these names, so once you implement the
bodies the whole UI lights up.

Style guidance
--------------
- planner -> blue
- coder   -> green
- runner  -> yellow
- errors  -> red
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from rich.console import Console
from rich.panel import Panel

# ----------------------------------------------------------------------------
# Phase banner
# ----------------------------------------------------------------------------

_PHASE_COLOR = {
    "planner": "blue",
    "coder":   "green",
    "runner":  "yellow",
}


def banner(phase: str) -> None:
    """Print a phase banner. ``phase`` ∈ {"planner", "coder", "runner", anything else}.

    Suggested implementation:

        from rich.console import Console
        color = _PHASE_COLOR.get(phase, "white")
        Console().print(f"[bold {color}]── {phase.upper()} ──────────────[/]")

    """
    color = _PHASE_COLOR.get(phase, "white")
    Console().print(f"\n[bold {color}]── {phase.upper()} ──────────────[/]")


# ----------------------------------------------------------------------------
# Tool call row
# ----------------------------------------------------------------------------

def tool_call_row(name: str, args: dict) -> None:
    """Render one line for a tool invocation, e.g. ``🔧 read_file src/foo.py (lines 1-50)``.

    Called from inside agent loops for every tool dispatch (optional but nice).

    Suggested:

        Console().print(f"🔧 [cyan]{name}[/] {summarise_args(name, args)}",
                        highlight=False)
    """
    raise NotImplementedError(
        "TODO: Console().print(f'🔧 [cyan]{name}[/] {args}')"
    )


# ----------------------------------------------------------------------------
# Panel
# ----------------------------------------------------------------------------

def panel(text: str, title: str = "", color: str | None = None) -> None:
    """Wrap ``text`` in a rich Panel and print it.
    """
    Console().print(Panel(text, title=title, border_style=color or "white"))

# ----------------------------------------------------------------------------
# Spinner context manager
# ----------------------------------------------------------------------------

@contextmanager
def spinner(text: str) -> Iterator[None]:
    """Context manager that shows a spinner with ``text`` while the body runs.

    Usage:

        with spinner("Planner thinking…"):
            result = planner.run(msg)

    Easiest impl:

        from rich.status import Status
        from rich.console import Console
        with Status(text, spinner="dots", console=Console()):
            yield
    """
    print(text, end="", flush=True)
    try:
        yield
    finally:
        print(" done. ")


# ----------------------------------------------------------------------------
# Prompt
# ----------------------------------------------------------------------------

def prompt() -> str:
    """Print the input prompt ``❯ `` and return the user's line.
    """
    try:
        return input("❯ ")
    except EOFError:
        raise SystemExit(0)
