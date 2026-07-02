"""
pipeline.py — orchestrate Planner → Coder → Runner.

main.py calls ``pipeline.run(user_msg)`` once per user input.
This module drives the three stages and returns a structured PipelineResult
that the UI layer can render stage by stage.

What you fill in:
  - run(user_msg)  — wire up the three stages + per-stage exception handling
"""
from __future__ import annotations

from dataclasses import dataclass, field

import planner
import coder
import runner
from ui import banner, panel


@dataclass
class StageResult:
    """Result of a single pipeline stage."""
    name: str                                # "planner" | "coder" | "runner"
    ok: bool
    artifact: str = ""                       # plan text / summary / test output
    error: str | None = None                 # None on success


@dataclass
class PipelineResult:
    """Aggregate result across all stages."""
    stages: list[StageResult] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """True iff every stage succeeded."""
        return all(s.ok for s in self.stages)


def run(user_msg: str) -> PipelineResult:
    """Drive Planner → Coder → Runner on a single user request.
    Planner->Coder->Runner is a linear pipeline, so if any stage fails, the rest are skipped.
    Returns a PipelineResult with per-stage ok/error status and artifacts.
    """
    
    result = PipelineResult()
    
    banner("planner")
    try:
        plan_text = planner.run(user_msg)
        result.stages.append(StageResult(name="planner", ok=True, artifact=plan_text))
        panel(plan_text, title="📋 Plan")    
    except Exception as e:
        result.stages.append(StageResult(name="planner", ok=False, error=str(e)))
        return result
    
    banner("coder")
    try:
        code_text = coder.run(plan_text)
        result.stages.append(StageResult(name="coder", ok=True, artifact=code_text))
        panel(code_text, title="Code")
    except Exception as e:
        result.stages.append(StageResult(name="coder", ok=False, error=str(e)))
        return result
    
    banner("runner")
    try:
        test = runner.run_tests()
        result.stages.append(StageResult(name="runner", ok=test.passed, artifact=test.output,
                                         error=None if test.passed else "Tests failed"))
        panel(test.output,title="Test Output", color="green" if test.passed else "red")
    except Exception as e:
        result.stages.append(StageResult(name="runner", ok=False, error=str(e)))
        return result
    
    return result
