"""task_store.py — codeagent 任务状态存储抽象 + 单进程内存实现(v0.3.0 新增)。

本文件目前以注释形式给出 v0.3.0 第一阶段的参考实现,等评审通过后再
把代码从注释里"解开"。先建文件占位,让后续 pipeline 接入能找到模块。

模块职责:
  TaskStore        Protocol —— 所有实现的统一接口(后续可加 JSON / SQLite)。
  MemoryTaskStore  单进程内存实现,只供本进程使用,不跨进程安全。

执行期状态变更都在这里:
  - claim_task(task_id, owner)    认领
  - update_status(task_id, status) 修改状态(带状态机校验)
"""
from __future__ import annotations

from typing import Protocol

from core.task_state import (
    Plan,
    TaskNode,
    TaskStatus,
)

__all__ = [
    "TaskStore",
    "MemoryTaskStore",
    "TaskNotFoundError",
    "TaskClaimError",
    "InvalidTaskTransitionError",
]

class TaskNotFoundError(KeyError):
  """操作的 task_id 不在当前 Plan 中。继承 KeyError,方便调用方用 'in' 检查。"""
  
  def __init__(self, task_id: str) -> None:
    super().__init__(task_id)
    self.task_id = task_id
    
  def __str__(self) -> str:
    return f"task {self.task_id!r} not found in plan"
  
class TaskClaimError(RuntimeError):
  """claim_task 失败时抛出,错误信息已说明具体原因。"""
  
class InvalidTaskTransitionError(RuntimeError):
  """update_status 给出的状态转移不被状态机允许。"""
  
class TaskStore(Protocol):
  """任务状态存储的统一接口(本轮只实现 MemoryTaskStore)。
  
  所有方法均为同步。线程 / 进程安全由具体实现负责。
  """
  
  def get_plan(self) -> Plan: ...
  
  def list_tasks(self) -> list[TaskNode]: ...
  
  def list_ready(self) -> list[TaskNode]: ...
  
  def get_task(self, task_id: str) -> TaskNode: ...
  
  def claim_task(self, task_id: str, owner: str) -> TaskNode: ...
  
  def update_status(self, task_id: str, status: TaskStatus) -> TaskNode: ...
  
_ALLOWED_TRANSITIONS: dict[TaskStatus, frozenset[TaskStatus]] = {
  TaskStatus.PENDING:    frozenset({TaskStatus.IN_PROGRESS,
                                    TaskStatus.BLOCKED,
                                    TaskStatus.FAILED}),
  TaskStatus.IN_PROGRESS:frozenset({TaskStatus.COMPLETED,
                                    TaskStatus.FAILED,  
                                    TaskStatus.BLOCKED}),
  TaskStatus.COMPLETED:  frozenset(),
  TaskStatus.FAILED:     frozenset({TaskStatus.PENDING}),
  TaskStatus.BLOCKED:    frozenset({TaskStatus.PENDING}),                            
}

# 在这个状态下把owner清空,让任务重新可被认领。其他状态保留 owner 便于事后追溯。
_CLEAR_OWNER_ON: frozenset[TaskStatus] = frozenset({
  TaskStatus.BLOCKED,
  TaskStatus.PENDING,
})

# 内存实现
class MemoryTaskStore:
  """单进程内存版 TaskStore
  
  初始化时立即对 plan 做 validate(),所以构造失败 = 静态不合法。
  
  Concurrency:
      仅适用于单进程。``list_ready() + claim_task()`` 在未来多进程环境下
      并不是原子操作;跨进程 TaskStore 必须通过事务或锁实现原子 claim。
  """
  
  def __init__(self, plan: Plan) -> None:
    self._plan = plan
    self._plan.validate()  # 构造即校验,失败快速抛
    
  def list_tasks(self) -> list[TaskNode]:
    """按 Plan.tasks 的插入顺序返回所有任务。"""
    return list(self._plan.tasks.values())

  def get_plan(self) -> Plan:
    """返回构造时传入的 Plan 对象。返回的是同一份引用,调用方请勿改动。"""
    return self._plan
  
  def list_ready(self) -> list[TaskNode]:
    return self._plan.ready()

  def get_task(self, task_id: str) -> TaskNode:
    try:
      return self._plan.tasks[task_id]
    except KeyError:
      raise TaskNotFoundError(task_id) from None
    
  def claim_task(self, task_id: str, owner: str) -> TaskNode:
    """
    认领一个 ready 任务。
    
    失败时抛 TaskClaimError,错误信息已说明具体原因(任务不存在时
    抛 TaskNotFoundError,保持与"找不到任务"语义清晰区分)。

    Concurrency:
        MemoryTaskStore 仅适用于单进程。
        未来跨进程 TaskStore 必须通过事务或锁实现原子 claim。
    """
    node = self.get_task(task_id)
    rt = node.runtime
    
    if not isinstance(owner, str) or owner.strip() == "":
        raise TaskClaimError(
            f"cannot claim task {task_id!r}: owner must be a non-empty string"
        )
    if rt.status != TaskStatus.PENDING:
        raise TaskClaimError(
            f"cannot claim task {task_id!r}: status is {rt.status.value!r}, "
            f"expected 'pending'"
        )
      
    if rt.owner is not None:
        raise TaskClaimError(
            f"cannot claim task {task_id!r}: already claimed by owner "
            f"{rt.owner!r}"
        )
    
    unfinished = [ d for d in node.spec.depends_on if self._plan.tasks[d].runtime.status != TaskStatus.COMPLETED ]
    if unfinished:
        raise TaskClaimError(
            f"cannot claim task {task_id!r}: dependencies not completed: "
            f"{unfinished!r}"
        )
        
    rt.owner = owner
    rt.status = TaskStatus.IN_PROGRESS
    return node
  
  def update_status(self, task_id: str, status: TaskStatus) -> TaskNode:
    """
    修改任务的状态
    
    允许的转移关系由模块级 _ALLOWED_TRANSITIONS 决定。
    切换到 BLOCKED / PENDING 时会自动清空 owner(任务重新可被认领);
    切换到 COMPLETED / FAILED 时保留 owner(便于事后追溯)。
    IN_PROGRESS 必然已经由 claim 设置,这里只增不改 owner。
    """
    
    node = self.get_task(task_id)
    rt = node.runtime
    current = rt.status
    
    allowed = _ALLOWED_TRANSITIONS.get(current, frozenset())
    if status not in allowed:
      raise InvalidTaskTransitionError(
          f"invalid status transition for task {task_id!r}: "
          f"{current.value!r} -> {status.value!r}; "
          f"allowed from {current.value!r}: "
          f"{sorted(s.value for s in allowed) or '<none>'}"
      )
      
    rt.status = status
    if status in _CLEAR_OWNER_ON:
      rt.owner = None
      
    return node