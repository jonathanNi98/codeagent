"""
tools.py — the 6 tools the LLM can call.

Structure
---------
  _impl_<name>      pure-function implementations. Each returns
                    (content: str, error: Optional[str]).
                    Bodies are stubs — fill them in.

  DISPATCH          name -> impl-function mapping.

  dispatch_tool     (name, args) -> formatted string suitable to feed
                    back to the LLM as a ``tool`` message.

  TOOL_SCHEMAS      list of JSON-Schema tool definitions in
                    OpenAI-compatible ``tools=[...]`` format.
                    Each one feeds into the LLM so it knows what it can call.

  tools_for(agent)  returns the subset of schemas an agent is allowed to use
                    (Planner = read-only, Coder = everything).

Output contract for every _impl
-------------------------------
    (content, error) where:
      success -> ("some text",   None)
      failure -> ("",             "reason")
The dispatcher formats either case for the LLM.
"""
from __future__ import annotations

import subprocess  # noqa: F401  (used by impls you write)
from pathlib import Path
from typing import Any


# ============================================================================
#                                Tool implementations
# ============================================================================
#
# Each _impl returns (content, error). Bodies are stubs — you write them.
# Keep the signature stable; the LLM schema depends on the keyword names.


def _impl_list_file(path: str = ".") -> tuple[str, str | None]:
    """List files & directories under ``path``.

    Default ``path="."`` means the agent's working directory.

    Return:
      (formatted_listing, None) on success
      ("",               "error message") on failure (e.g. path missing)
    """
    raise NotImplementedError(
        "TODO: Path(path).iterdir() or os.listdir(); format as a tree or "
        "indented list. Hide dotfiles unless explicitly requested."
    )


def _impl_read_file(
    path: str,
    start_line: int | None = None,
    end_line: int | None = None,
) -> tuple[str, str | None]:
    """Read ``path``. If start_line/end_line given, return just that 1-indexed inclusive slice.

    Format every output line as ``"  <n>: <text>"`` (note the 2-space indent)
    so the LLM can cite line numbers back.
    """
    raise NotImplementedError(
        "TODO: Path(path).read_text(); splitlines(); slice(start-1, end); "
        "prefix each line with its 1-indexed number; join with '\\n'."
    )


def _impl_search_file(
    pattern: str,
    path: str = ".",
    regex: bool = False,
) -> tuple[str, str | None]:
    """Search ``pattern`` under ``path``.

    When ``regex=False`` treat ``pattern`` as a literal substring.
    When ``regex=True`` compile it with ``re.compile``.

    Format each match as ``"<relpath>:<lineno>:<line>"``.
    """
    raise NotImplementedError(
        "TODO: subprocess.run(['grep', '-rn', ...]) or walk the tree with "
        "pathlib.rglob and filter lines. Return at most N matches if the "
        "result could be huge."
    )


def _impl_write_file(path: str, content: str) -> tuple[str, str | None]:
    """Overwrite (or create) ``path`` with ``content`` (full file contents)."""
    raise NotImplementedError(
        "TODO: Path(path).parent.mkdir(parents=True, exist_ok=True); "
        "Path(path).write_text(content, encoding='utf-8'). Return "
        "('wrote <N> bytes', None)."
    )


def _impl_run_command(
    cmd: str,
    cwd: str | None = None,
    timeout: int = 30,
) -> tuple[str, str | None]:
    """Run a shell command. Returns combined stdout+stderr.

    Suggested:
        proc = subprocess.run(
            cmd, shell=True, cwd=cwd,
            capture_output=True, text=True, timeout=timeout,
        )
    If exit 0 -> (stdout, None).  Else -> (stdout+stderr, "exit <code>").
    On TimeoutExpired -> return ("", "timed out after <N>s").
    """
    raise NotImplementedError(
        "TODO: subprocess.run(..., shell=True, capture_output=True, text=True, "
        "timeout=timeout). Map returncode into the (content, error) tuple."
    )


def _impl_git_diff(cwd: str = ".") -> tuple[str, str | None]:
    """Return ``git diff`` of working tree against HEAD. '' if no changes."""
    raise NotImplementedError(
        "TODO: subprocess.run(['git', 'diff'], cwd=cwd, capture_output=True, "
        "text=True). On non-zero exit (e.g. not a git repo) return "
        "('', error)."
    )


# ============================================================================
#                                Dispatch table
# ============================================================================

DISPATCH: dict[str, Any] = {
    "list_file":   _impl_list_file,
    "read_file":   _impl_read_file,
    "search_file": _impl_search_file,
    "write_file":  _impl_write_file,
    "run_command": _impl_run_command,
    "git_diff":    _impl_git_diff,
}


def dispatch_tool(name: str, args: dict[str, Any]) -> str:
    """Run the impl for ``name`` with ``args`` and return a single string for the LLM.

    Suggested formatting:
      success         -> content as-is
      error           -> "[ERROR] <error>"
      unknown tool    -> "[ERROR] unknown tool: <name>"

    You should also try/except around the impl call so a NotImplementedError
    (still-stub) surfaces cleanly to the LLM instead of crashing the loop.
    """
    impl = DISPATCH.get(name)
    if impl is None:
        return f"[ERROR] unknown tool: {name!r}"

    # TODO: try: content, error = impl(**args)  except Exception as e: ...
    raise NotImplementedError(
        "TODO: call impl(**args), format (content, error) into one string. "
        "Catch exceptions so the agent loop keeps running."
    )


# ============================================================================
#                       JSON-Schema tool definitions
# ============================================================================
#
# These are the descriptions the LLM sees. Keep the descriptions crisp —
# the LLM uses them to decide WHEN to call each tool.

TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "list_file",
            "description": (
                "List files and directories under a path. Use to discover what "
                "is in a folder before reading specific files."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Directory path, relative to the working directory or absolute. Defaults to '.'.",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": (
                "Read the contents of a file. Output is prefixed with line "
                "numbers (e.g. '  12: foo()') so you can cite lines back. "
                "Use start_line/end_line for large files."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "File path, relative or absolute.",
                    },
                    "start_line": {
                        "type": "integer",
                        "description": "Optional 1-indexed inclusive start line.",
                    },
                    "end_line": {
                        "type": "integer",
                        "description": "Optional 1-indexed inclusive end line.",
                    },
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_file",
            "description": (
                "Search for a substring or regex across files under a path. "
                "Each match is returned as '<file>:<line>:<content>'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "Substring (when regex=false) or regular expression (when regex=true).",
                    },
                    "path": {
                        "type": "string",
                        "description": "Directory to search. Defaults to '.'.",
                    },
                    "regex": {
                        "type": "boolean",
                        "description": "Treat pattern as a regular expression. Defaults to false.",
                    },
                },
                "required": ["pattern"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": (
                "Overwrite (or create) a file with the given content. "
                "The whole file is replaced — include everything you want kept."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "File path, relative or absolute.",
                    },
                    "content": {
                        "type": "string",
                        "description": "Full new contents of the file.",
                    },
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_command",
            "description": (
                "Run a shell command in the agent's working directory. "
                "Use only read-only or project-intended commands (ls, cat, "
                "grep, git log, pytest, etc.). Returns combined stdout+stderr "
                "and the exit code."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "cmd": {
                        "type": "string",
                        "description": "Shell command to execute.",
                    },
                    "cwd": {
                        "type": "string",
                        "description": "Optional working directory. Defaults to the agent's working directory.",
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "Optional timeout in seconds. Defaults to 30.",
                    },
                },
                "required": ["cmd"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "git_diff",
            "description": (
                "Show the unified diff of the working tree against HEAD. "
                "Empty string means no working-tree changes."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "cwd": {
                        "type": "string",
                        "description": "Optional working directory. Defaults to the agent's working directory.",
                    },
                },
            },
        },
    },
]


# ============================================================================
#                  Per-agent tool subsets (used by planner/coder)
# ============================================================================

PLANNER_TOOL_NAMES = {"list_file", "read_file", "search_file", "run_command", "git_diff"}
CODER_TOOL_NAMES = set(DISPATCH.keys())  # all 6


def tools_for(agent: str) -> list[dict[str, Any]]:
    """Return only the schemas allowed for the named agent.

    agent ∈ {"planner", "coder"}.
    Planner: read-only investigation (no write_file).
    Coder:   everything.
    """
    if agent == "planner":
        names = PLANNER_TOOL_NAMES
    elif agent == "coder":
        names = CODER_TOOL_NAMES
    else:
        raise ValueError(f"unknown agent: {agent!r}")
    return [t for t in TOOL_SCHEMAS if t["function"]["name"] in names]
