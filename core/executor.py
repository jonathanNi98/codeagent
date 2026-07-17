"""executor.py — codeagent 任务执行抽象(v0.3.1 新增)。

模块职责:
  TaskResult      一次执行的结果,engine.step() 据此决定 update_status 切到哪。
  Executor        一个 task「怎么跑」的抽象(Protocol 风格的基类)。
  NoopExecutor    占位实现,所有 task 都返回 ok=True —— 用于演示 / 拓扑演练。
  FailingExecutor 测试用实现,按 task.action 关键词决定 ok / !ok。

本模块不调 LLM / 不调 subprocess —— 真正的 LLMAgentExecutor /
SubprocessExecutor 留给 v0.3.5+。当前阶段只保证:engine.step() 有一条
可被独立测的执行路径。
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    # 仅供类型检查 —— 运行时不需要 import,避免和 core.task_store 循环依赖。
    from core.task_state import TaskNode

__all__ = [
    "TaskResult",
    "Executor",
    "NoopExecutor",
    "FailingExecutor",
]

@dataclass(frozen=True)
class TaskResult:
    ok: bool
    error: str | None = None
    
    def __post_init__(self) -> None:
        if self.ok and self.error is not None:
            raise ValueError(
                f"TaskResult(ok=True, error=...) is invalid: "
                f"error must be None when ok=True, got {self.error!r}"
            )
        if not self.ok and not self.error:
            raise ValueError(
                "TaskResult(ok=False, error=None/empty) is invalid: "
                "error must be a non-empty string when ok=False"
            )

class Executor:
    """
    一个 task 应该怎么跑
    """
    
    name: str = "Executor"
    
    def run(self, task: "TaskNode") -> TaskResult:
        raise NotImplementedError(f"{type(self).__name__}.run() must be implemented")
    
class NoopExecutor(Executor):
    """
    所有 task 都返回 ok=True
    """
    
    name: str = "NoopExecutor"
    
    def run(self, task: "TaskNode") -> TaskResult:
        return TaskResult(ok=True)

class FailingExecutor(Executor):
    """
    根据 task.action 决定 ok / !ok
    """
    name: str = "FailingExecutor"
    _FAILURE_TOKEN: str = "boom"
    
    def run(self, task: "TaskNode") -> TaskResult:
        if self._FAILURE_TOKEN in task.spec.action:
            return TaskResult(ok=False, error=f"simulated failure: {task.spec.action!r}")
        return TaskResult(ok=True)
