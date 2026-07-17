"""task_state.py — codeagent 任务静态定义 + Plan 静态校验(v0.3.0 新增)。

本文件目前以注释形式给出 v0.3.0 第一阶段的参考实现,等评审通过后再
把代码从注释里"解开"。先建文件占位,让 core.task_store 能 import 到。

模块职责:
  TaskSpec   不可变。任务定义(id / action / depends_on),创建后通常不变。
  TaskRuntime 可变。运行时状态(status / owner),执行过程中不断变。
  TaskNode   组合上面两者 = 一个完整任务实例。
  Plan       一组 TaskNode + 静态校验 + "当前可执行任务" 查询。

执行期状态变更(claim / update_status)放在 core.task_store,本模块不做。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable

import core

__all__ = [
    "TaskStatus",
    "TaskSpec",
    "TaskRuntime",
    "TaskNode",
    "Plan",
    "InvalidPlanError",
]

class InvalidPlanError(ValueError):
    """Plan 静态结构不合法时抛出(键名不一致、缺依赖、自依赖、循环依赖 等)。"""

class TaskStatus(str, Enum):
    """任务运行时状态。

    PENDING     等待被认领
    IN_PROGRESS 已被某 owner 认领,正在执行
    COMPLETED   执行成功(终态,但可在 history 中保留 owner)
    FAILED      执行失败(可在 update_status 中回到 PENDING 重试)
    BLOCKED     被阻塞(可在 update_status 中回到 PENDING 重新调度)
    """
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"

@dataclass(frozen=True)
class TaskSpec:
    """任务静态定义。
    
    Fields:
        id:          任务唯一 id,Plan 字典的 key 必须与此一致。
        action:      任务要做什么的描述(由上层语义解析,如 "read:foo.py")。
        depends_on:  本任务的前置任务 id 集合(注意:必须是 tuple)。
    """
    
    id: str
    action: str
    depends_on: tuple[str, ...] = ()
    
    def __post_init__(self) -> None:
        if not isinstance(self.depends_on, tuple):
            object.__setattr__(self, "depends_on", tuple(self.depends_on))

@dataclass
class TaskRuntime:
    """任务运行时状态"""
    status: TaskStatus = TaskStatus.PENDING
    owner: str | None = None
    
@dataclass
class TaskNode:
    """完整任务实例 = 静态定义 + 运行时状态。"""
    spec: TaskSpec
    runtime: TaskRuntime = field(default_factory=TaskRuntime)
    
@dataclass
class Plan:
    """一组TaskNode + 静态校验入口。
    
    Fields:
        summary:          Plan 描述(给上层 UI / log 用,不参与调度)。
        needs_code_change: 与现有 core.planner_schema.Plan 语义对齐,本轮只作为元信息保留,调度本身不依赖它。
        tasks:           任务字典,key == spec.id。
    """
    
    summary: str
    needs_code_change: bool
    tasks: dict[str, TaskNode] = field(default_factory=dict)
    
    def validate(self) -> None:
        """静态校验 tasks 的结构合法性。

        检查项(顺序):
          1. 字典 key 必须 == TaskSpec.id
          2. 禁止自依赖
          3. 所有 depends_on 必须存在于 tasks
          4. 无循环依赖(DFS,WHITE/GRAY/BLACK 着色)
        """
        
        for key, node in self.tasks.items():
            if key != node.spec.id:
                raise InvalidPlanError(
                    f"task dict key {key!r} does not match TaskSpec.id "
                    f"{node.spec.id!r}"
                )
        
        for tid, node in self.tasks.items():
            if tid in node.spec.depends_on:
                raise InvalidPlanError(
                    f"task {tid!r} depends on itself"
                )
        
        for tid, node in self.tasks.items():
            missing = [d for d in node.spec.depends_on if d not in self.tasks]
            if missing:
                raise InvalidPlanError(
                    f"task {tid!r} has missing dependencies: {missing!r}"
                )
                
        cycle = _detect_cycle(self.tasks)
        if cycle:
            raise InvalidPlanError(
                f"cyclic dependency detected: {' -> '.join(cycle)}"
            )
            
    def ready(self) -> list[TaskNode]:
        """返回当前可执行的任务列表。

        可执行条件(全部满足):
          - status == PENDING
          - owner is None
          - 所有 depends_on 对应任务 status == COMPLETED
          
        返回顺序 == tasks 字典插入顺序(稳定)。
        """
        
        out: list[TaskNode] = []
        for node in self.tasks.values():  # dict 保持插入顺序
            rt = node.runtime
            if rt.status != TaskStatus.PENDING:
                continue
            if rt.owner is not None:
                continue
            all_completed = True
            for d in node.spec.depends_on:
                dep_node = self.tasks[d]
                if dep_node.runtime.status != TaskStatus.COMPLETED:
                    all_completed = False
                    break
            if not all_completed:
                continue
            out.append(node)
        return out
            
def _detect_cycle(tasks:dict[str, TaskNode]) -> list[str] | None:
    """DFS 检测循环依赖。命中时返回构成环的节点序列(含回到起点),否则 None。"""
    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[str, int] = {tid: WHITE for tid in tasks}
    path: list[str] = []
    
    def visit(tid: str) -> list[str] | None:
        color[tid] = GRAY
        path.append(tid)
        for dep in tasks[tid].spec.depends_on:
            c = color[dep]
            if c == GRAY:
                # 在 path 里第一次出现 dep 的位置 + dep 本身 = 一个环
                idx = path.index(dep)
                return path[idx:] + [dep]
            if c == WHITE:
                found = visit(dep)
                if found is not None:
                    return found
        path.pop()
        color[tid] = BLACK
        return None
    
    for tid in tasks:
        if color[tid] == WHITE:
            cycle = visit(tid)
            if cycle is not None:
                return cycle
            
    return None
