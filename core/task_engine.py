"""task_engine.py — codeagent 任务调度循环(v0.3.1 新增)。

模块职责:
  StepOutcome   engine.step() 一次的结果(triple)。
  EngineError   engine 内部步骤出错时抛(目前专用于包 TaskClaimError)。
  TaskEngine    单步驱动的执行循环 —— 调用方主动推进,不是「一次性跑完」。

不调 LLM / 不调 subprocess,执行委托给 core.executor.Executor。
本模块只负责:
  1.  从 store 拉一个 ready task
  2.  claim 它(把 owner 设为 executor.name)
  3.  调 executor.run() 拿一个 TaskResult
  4.  按 result.ok 把 task 推到 COMPLETED 或 FAILED
  5.  return StepOutcome

为什么是 step 而不是 run_until_complete:
  - 每次 step 后调用方可以查验 store 状态(测试粒度需要)
  - 调用方控制节奏(上限 / 用户中断 / dry-run)
  - v0.3.3 的 failure_classifier 还没写,一次性跑完遇到 FAILED 不知道该不该重试
"""

from __future__ import annotations

from dataclasses import dataclass
from core.executor import Executor, TaskResult
from core.task_state import TaskStatus
from core.task_store import TaskClaimError, TaskStore

__all__ = [
    "TaskEngine",
    "StepOutcome",
    "EngineError",
]

@dataclass(frozen=True)
class StepOutcome:
    """
    engine.step() 一次的结果
    """
    
    task_id: str
    final_status: TaskStatus
    result: TaskResult
    
    @property
    def error(self) -> str | None:
        """result.ok=False 时的 error,None 表示成功(等价 result.error)。"""
        return self.result.error
    
class EngineError(RuntimeError):
    """
    Engine 内部出错
    """
    
    def __init__(self, message: str, *, cause: BaseException | None = None) -> None:
        super().__init__(message)
        self.cause = cause
        
class TaskEngine:
    """
    单步驱动的执行循环
    """
    
    def __init__(self, store: TaskStore, executor: Executor) -> None:
        self.store = store
        self.executor = executor
        
    def step(self) -> StepOutcome | None:
        """
        跑一个 task:list_ready → claim → run → update_status。
        """
        ready = self.store.list_ready()
        if not ready:
            return None
        
        pick = ready[0]
        task_id = pick.spec.id
        
        try:
            claimed = self.store.claim_task(task_id, owner=self.executor.name)
        except TaskClaimError as e:
            raise EngineError(
                f"claim failed mid-step for task {task_id!r}: {e}",
                cause=e,
            ) from e
        
        result = self.executor.run(claimed)
        
        if result.ok:
            final = self.store.update_status(task_id, TaskStatus.COMPLETED)
        else:
            final = self.store.update_status(task_id, TaskStatus.FAILED)
        
        return StepOutcome(
            task_id=task_id,
            final_status=final.runtime.status,
            result=result,
        )
