"""
runner.py — execute the project's test command and report pass/fail.

This is NOT an LLM agent. It's a thin shell-out that runs whatever
TEST_CMD points at (default: ``pytest -q``) inside AGENT_WORKDIR.

What you fill in:
  - run_tests() — the actual subprocess.run call + returncode handling.
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from config import get_config


@dataclass
class TestResult:
    """Outcome of a single test invocation."""
    passed: bool
    returncode: int
    output: str         # combined stdout + stderr
    timed_out: bool


def run_tests(
    workdir: Path | None = None,
    cmd: str | None = None,
) -> TestResult:
    """Execute the test command and return a TestResult.

    Args:
        workdir: directory to run in. Defaults to cfg.workdir.
        cmd:     shell command to run. Defaults to cfg.test_cmd.
    """
    def _decode(x: Any) -> str:
        """TimeoutExpired.stdout/stderr may be bytes / str / None.
        Coerce all three to str so TestResult.output stays well-typed.
        """
        if x is None:
            return ""
        if isinstance(x, bytes):
            return x.decode("utf-8", errors="replace")
        # 已经排除 None 和 bytes,剩下就是 str;用 str() 兜底
        # Pylance 看到 bytearray / memoryview 跟 bytes 一样满足 isinstance 检查,
        # 所以这里靠 str() 兜住
        return str(x)

    cfg = get_config()
    cwd = workdir or cfg.workdir

    try:
        proc = subprocess.run(
            cmd or cfg.test_cmd,
            shell=True,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=300,
        )
    except subprocess.TimeoutExpired as e:
        return TestResult(
            passed=False,
            returncode=-1,
            output=_decode(e.stdout) + _decode(e.stderr),
            timed_out=True,
        )
    except OSError as e:
        return TestResult(
            passed=False,
            returncode=-1,
            output=f"shell exec error: {e}",
            timed_out=False,
        )

    output = _decode(proc.stdout) + _decode(proc.stderr)
    return TestResult(
        passed=proc.returncode == 0,
        returncode=proc.returncode,
        output=output,
        timed_out=False,
    )