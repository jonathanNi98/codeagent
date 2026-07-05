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
from core.planner_schema import parse_plan, PlanParseError

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
        plan = parse_plan(plan_text)
        result.stages.append(StageResult(name="planner", ok=True, artifact=plan_text))
        panel(plan_text, title="📋 Plan")    
    except Exception as e:
        result.stages.append(StageResult(name="planner", ok=False, error=str(e)))
        return result
    
    needs_code_change = plan.needs_code_change
    if not needs_code_change:
        panel(plan.summary, title="Answer")
        return result
    
    banner("coder")
    try:
        code_text = coder.run(plan_text)
        """
        ===================== 改动 6 / 你自己写 =====================
        这段三引号是指引，不会执行。请把上面那行：
            code_text = coder.run(plan_text)
        替换成：
            code_text = coder.run(plan_text, allowed_files=plan.allowed_files())
        （plan 是 3(b) 那一段解析出来的 Plan 对象；
          plan.allowed_files() 返回 frozenset[str]，白名单；allowlist=None 时
          _impl_write_file 内部会短路、保持旧行为，但 Coder 阶段我们总会传。）

        这是把 Plan.files_to_modify 接上 Coder 工具链的关键一行，
        改完白名单强制就全链路贯通了：
            Plan.files_to_modify
              -> plan.allowed_files()  (frozen)
              -> coder.run(allowed_files=...)
              -> dispatch_tool(allowed_files=...)
              -> _impl_write_file(allowed_files=...)  (落盘前拦截)
        ============================================================
        """
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
