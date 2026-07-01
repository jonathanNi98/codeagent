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

    Suggested implementation:

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
            output = (proc.stdout or "") + (proc.stderr or "")
            return TestResult(
                passed=proc.returncode == 0,
                returncode=proc.returncode,
                output=output,
                timed_out=False,
            )
        except subprocess.TimeoutExpired as e:
            return TestResult(
                passed=False,
                returncode=-1,
                output=(e.stdout or "") + (e.stderr or "") if isinstance(e.stdout, str) else "",
                timed_out=True,
            )

    Map returncode 0 -> passed=True. Anything else -> passed=False.
    """
    raise NotImplementedError(
        "TODO: subprocess.run(cmd, shell=True, capture_output=True, text=True, "
        "timeout=300). Map returncode into .passed; catch TimeoutExpired into "
        ".timed_out."
    )
