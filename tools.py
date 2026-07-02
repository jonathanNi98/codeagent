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
import re 
import subprocess  # noqa: F401  (used by impls you write)
from pathlib import Path
from typing import Any

from core.config import get_config


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
    p = Path(path)
    if not p.exists():
        return "", f"path does not exist: {path}"
    if not p.is_dir():
        return "", f"path is not a directory: {path}"
    
    entries: list[str] = []
    for entry in sorted(p.iterdir(), key=lambda p: p.name):
        if entry.name.startswith("."):
            continue
        marker = "/" if entry.is_dir() else ""
        entries.append(f"{entry.name}{marker}")
        
    if not entries:
        return "(empty)", None
    return ("\n".join(entries), None)

def _impl_read_file(
    path: str,
    start_line: int | None = None,
    end_line: int | None = None,
) -> tuple[str, str | None]:
    """Read ``path``. If start_line/end_line given, return just that 1-indexed inclusive slice.

    Format every output line as ``"  <n>: <text>"`` (note the 2-space indent)
    so the LLM can cite line numbers back.
    """
    p = Path(path)
    if not p.exists():
        return "", f"path does not exist: {path}"
    if not p.is_file():
        return "", f"path is not a file: {path}"
    try:
        text = p.read_text(encoding="utf-8")
    except OSError as e:
        return "", f"OS error reading file: {e}"
    except Exception as e:
        return "", f"failed to read file: {e}"
    
    lines = text.splitlines()
    total = len(lines)
    
    start_index = max(0, start_line - 1) if start_line is not None else 0
    end_index = min(total, end_line) if end_line is not None else total
    sliced = lines[start_index:end_index]
    
    base = start_line if start_line is not None else 1
    numbered = [f"  {i}: {line}" for i, line in enumerate(sliced, start=base)]
    
    return ("\n".join(numbered), None)

SKIP_DIRS = {".git", "__pycache__", ".venv", "venv", "node_modules", ".pytest_cache"}
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
    root = Path(path)
    if not root.exists():
        return "", f"path does not exist: {path}"
    
    try:
        needle = re.compile(pattern) if regex else None
    except re.error as e:
        return ("", f"invalid regex: {e}")
    
    if root.is_file():
        files = [root]
    else:
        files = [p for p in root.rglob("*") if p.is_file() and p.name not in SKIP_DIRS]
    
    hits: list[str] = []
    max_hits = 100
    for file in files:
        try:
            text = file.read_text(encoding="utf-8")
        except Exception as e:
            continue
        for i, line in enumerate(text.splitlines(), start=1):
            matched = (
                (needle is not None and needle.search(line))
                or (needle is None and pattern in line)
            )
            if matched:
                realpath = file.relative_to(root) if root.is_dir() else file
                hits.append(f"{realpath}:{i}:{line}")
                if len(hits) >= max_hits:
                    hits.append(f"... (truncated, >{max_hits} matches)")
                    return ("\n".join(hits), None)
        
        if not hits:
            return ("(no matches)", None)
        
    return ("\n".join(hits), None)


def _impl_write_file(path: str, content: str) -> tuple[str, str | None]:
    """Overwrite (or create) ``path`` with ``content`` (full file contents)."""
    # Caculate the allowed working directory to prevent writing outside of it
    cfg = get_config()
    allowed_workdir = Path(cfg.workdir).resolve()
    p = Path(path).resolve()
    
    try:
        p.relative_to(allowed_workdir)
    except ValueError:
        return ("", f"write error is outside of the allowed working directory")
    
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return (f"wrote {len(content)} bytes to {path}", None)
    except OSError as e:
        return ("", f"write error: {e}")


def _impl_run_command(
    cmd: str,
    cwd: str | None = None,
    timeout: int = 30,
) -> tuple[str, str | None]:
    """Run a shell command. Returns combined stdout+stderr."""
    try:
        proc = subprocess.run(
            cmd,
            shell=True,             # 把 cmd 当字符串给 /bin/sh -c "cmd"
            cwd=cwd,                # 在哪跑(默认 None = 当前进程 cwd)
            capture_output=True,    # 捕获 stdout 和 stderr(否则会漏)
            text=True,              # stdout/stderr 是 str 而不是 bytes
            timeout=timeout,        # 30s 兜底,长任务 LLM 可以传更长
        )
    except subprocess.TimeoutExpired:
        return ("", f"timed out after {timeout}s")
    except OSError as e:
        # 极端情况:shell 不存在(macOS 上偶尔有),cmd 写错等
        return ("", f"shell exec error: {e}")

    # 把 stdout + stderr 拼一起(LLM 看到完整输出)
    output = (proc.stdout or "") + (proc.stderr or "")
    if proc.returncode == 0:
        return (output, None)
    # 非零退出是"测试失败"那种,不是 LLM 工具调用本身的错误 → 走 error 字段
    return (output, f"exit {proc.returncode}")


def _impl_git_diff(cwd: str = ".") -> tuple[str, str | None]:
    """Return ``git diff`` of working tree against HEAD. '' if no changes."""
    try:
        proc = subprocess.run(
            ["git", "diff"],       # list 传法,不经过 shell,避免注入风险
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except subprocess.TimeoutExpired:
        return ("", "git diff timed out")
    except FileNotFoundError:
        return ("", "git not installed")
    except OSError as e:
        return ("", f"git exec error: {e}")

    # git diff 在非 git 仓库里返回非零退出,这是预期情况
    if proc.returncode != 0:
        err = (proc.stderr or "").strip() or f"git exit {proc.returncode}"
        return ("", err)

    diff = proc.stdout or ""
    if not diff.strip():
        return ("(no working-tree changes)", None)
    return (diff, None)


# ============================================================================
#                                Dispatch table
# ============================================================================
DISPATCH: dict[str, Any] = {
    "list_file":    _impl_list_file,
    "read_file":    _impl_read_file,
    "search_file":  _impl_search_file,
    "write_file":   _impl_write_file,
    "run_command":  _impl_run_command,
    "git_diff":     _impl_git_diff,
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
        return f"[ERROR] unknown tool: {name}"
    try:
        content, error = impl(**args)
        if error is not None:
            return f"[ERROR] {error}"
        return content
    except Exception as e:
        return f"[ERROR] {type(e).__name__}: {e}"


# ============================================================================
#                       JSON-Schema tool definitions
# ============================================================================
#
# These are the descriptions the LLM sees. Keep the descriptions crisp —
# the LLM uses them to decide WHEN to call each tool.

TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "name": "list_file",
        "description": (
            "List files and directories under a path. Use to discover what "
            "is in a folder before reading specific files."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Directory path, relative to the working directory or absolute. Defaults to '.'.",
                },
            },
            "required": [],
        },
    },
    {
        "name": "read_file",
        "description": (
            "Read the contents of a file. Output is prefixed with line "
            "numbers (e.g. '  12: foo()') so you can cite lines back. "
            "Use start_line/end_line for large files."
        ),
        "input_schema": {
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
    {
        "name": "search_file",
        "description": (
            "Search for a substring or regex across files under a path. "
            "Each match is returned as '<file>:<line>:<content>'."
        ),
        "input_schema": {
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
    {
        "name": "write_file",
        "description": (
            "Overwrite (or create) a file with the given content. "
            "The whole file is replaced — include everything you want kept."
        ),
        "input_schema": {
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
    {
        "name": "run_command",
        "description": (
            "Run a shell command in the agent's working directory. "
            "Use only read-only or project-intended commands (ls, cat, "
            "grep, git log, pytest, etc.). Returns combined stdout+stderr "
            "and the exit code."
        ),
        "input_schema": {
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
    {
        "name": "git_diff",
        "description": (
            "Show the unified diff of the working tree against HEAD. "
            "Empty string means no working-tree changes."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "cwd": {
                    "type": "string",
                    "description": "Optional working directory. Defaults to the agent's working directory.",
                },
            },
            "required": [],
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
    return [t for t in TOOL_SCHEMAS if t["name"] in names]
