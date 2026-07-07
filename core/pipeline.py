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

from agents import planner, coder, runner
from ui import banner, panel
from core.planner_schema import PlanParseError, plan_with_retries

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


def run(user_msg: str, session_context: str = "") -> PipelineResult:
    """Drive Planner → Coder → Runner on a single user request.
    Planner->Coder->Runner is a linear pipeline, so if any stage fails, the rest are skipped.
    Returns a PipelineResult with per-stage ok/error status and artifacts.
    """

    result = PipelineResult()
    
    banner("planner")
    try:
        plan_text, plan = plan_with_retries(user_msg, session_context=session_context)
        result.stages.append(StageResult(name="planner", ok=True, artifact=plan_text))
        panel(plan_text, title="📋 Plan")
    except Exception as e:
        result.stages.append(StageResult(name="planner", ok=False, error=str(e)))
        return result
    
    needs_code_change = plan.needs_code_change
    if not needs_code_change:
        panel(plan.summary, title="Answer")
        return result
    
    test_feedback: str = ""
    last_test_output: str = ""
    test_passed: bool = False
    for attempt in range(3):
        banner("coder" if attempt == 0 else f"coder retry {attempt}")
        try:
            code_text = coder.run(
                plan_text,
                allowed_files=plan.allowed_files(),
                session_context=session_context,
                test_feedback=test_feedback,
            )
            if attempt == 0:
                result.stages.append(StageResult(name="coder", ok=True, artifact=code_text))
                panel(code_text, title="Code")
        except Exception as e:
            result.stages.append(StageResult(name="coder", ok=False, error=str(e)))
            return result
        
        banner("runner")
        try:
            test = runner.run_tests()
            last_test_output = test.output
            test_passed = test.passed
            result.stages.append(StageResult(
                name="runner",
                ok=test.passed,
                artifact=test.output,
                error=None if test.passed else f"Tests failed (attempt {attempt + 1}/3)",
            ))
            panel(test.output, title="Test Output", color="green" if test.passed else "red")
        except Exception as e:
            result.stages.append(StageResult(name="runner", ok=False, error=str(e)))
            return result
        
        if test.passed:
            break
        head = last_test_output[:100]
        tail = last_test_output[-500:] if len(last_test_output) > 500 else last_test_output
        test_feedback = f"{head}\n\n[... truncated {len(last_test_output) - 600} chars ...]\n\n{tail}"
        
    return result
