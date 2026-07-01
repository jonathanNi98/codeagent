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

    Returns a PipelineResult. Each stage's exception is captured into that
    stage's ``error`` field (rather than propagating) so that downstream
    stages can still see what earlier stages produced. If the Planner fails,
    return immediately — there's no plan to code from.

    TODO (you implement): the structure is fixed, the body is yours.

        result = PipelineResult()

        # --- Planner ---
        banner("planner")
        try:
            plan_text = planner.run(user_msg)
            result.stages.append(StageResult("planner", True, artifact=plan_text))
            panel(plan_text, title="Plan")
        except Exception as e:
            result.stages.append(StageResult("planner", False, error=str(e)))
            return result

        # --- Coder ---
        banner("coder")
        try:
            summary = coder.run(plan_text)
            result.stages.append(StageResult("coder", True, artifact=summary))
            panel(summary, title="Coder summary")
        except Exception as e:
            result.stages.append(StageResult("coder", False, error=str(e)))
            return result

        # --- Runner ---
        banner("runner")
        try:
            test = runner.run_tests()
            result.stages.append(StageResult(
                "runner",
                ok=test.passed,
                artifact=test.output,
                error=None if test.passed else f"tests failed (exit {test.returncode})",
            ))
        except Exception as e:
            result.stages.append(StageResult("runner", False, error=str(e)))

        return result
    """
    raise NotImplementedError(
        "TODO: orchestrate planner.run -> coder.run -> runner.run_tests "
        "with per-stage exception capture. See docstring pseudocode."
    )
