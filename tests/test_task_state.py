"""tests/test_task_state.py — 覆盖 task_state 的 10 个核心场景(编号对应规范)。

本文件目前以注释形式给出 v0.3.0 第一阶段的参考测试,等评审通过后
把代码从 # 号注释里"解开"即可用 unittest 跑。

对应规范编号:
  1.  无依赖任务是 ready
  2.  依赖未完成时不可 ready
  3.  依赖完成后任务 ready
  4.  已被 owner 认领的任务不可 ready
  5.  非 PENDING 状态不可 ready(IN_PROGRESS / COMPLETED / FAILED / BLOCKED)
  6.  依赖不存在 -> InvalidPlanError
  7.  自依赖 -> InvalidPlanError
  8.  两节点循环依赖 -> InvalidPlanError
  9.  三节点循环依赖 -> InvalidPlanError
  10. 字典 Key 和 TaskSpec.id 不一致 -> InvalidPlanError

跑测:
  python -m unittest tests.test_task_state -v
"""
from __future__ import annotations


# ---------------------------------------------------------------------------
# 参考实现 —— 已解开,跑 python -m unittest tests.test_task_state -v
# ---------------------------------------------------------------------------

import unittest

from core.task_state import (
    InvalidPlanError,
    Plan,
    TaskNode,
    TaskRuntime,
    TaskSpec,
    TaskStatus,
)


def _spec(tid: str, action: str = "do:something", depends_on=()) -> TaskSpec:
    return TaskSpec(id=tid, action=action, depends_on=depends_on)


def _plan_with(*nodes: TaskNode, needs_code_change: bool = True) -> Plan:
    return Plan(
        summary="test plan",
        needs_code_change=needs_code_change,
        tasks={n.spec.id: n for n in nodes},
    )


class TestPlanReady(unittest.TestCase):
    """1~5: ready() 的状态筛选规则。"""

    def test_no_deps_is_ready(self):
        # 1. 无依赖 + PENDING => 在 ready()
        p = _plan_with(TaskNode(_spec("a")))
        self.assertEqual([n.spec.id for n in p.ready()], ["a"])

    def test_dep_not_complete_not_ready(self):
        # 2. 依赖未完成时不可 ready
        p = _plan_with(
            TaskNode(_spec("a")),
            TaskNode(_spec("b", depends_on=("a",))),
        )
        ready_ids = {n.spec.id for n in p.ready()}
        self.assertIn("a", ready_ids)
        self.assertNotIn("b", ready_ids)

    def test_dep_complete_makes_ready(self):
        # 3. 依赖完成后任务 ready
        p = _plan_with(
            TaskNode(_spec("a"), TaskRuntime(status=TaskStatus.COMPLETED, owner="m")),
            TaskNode(_spec("b", depends_on=("a",))),
        )
        self.assertEqual([n.spec.id for n in p.ready()], ["b"])

    def test_owner_blocks_ready(self):
        # 4. 已被 owner 认领的任务不可 ready
        p = _plan_with(
            TaskNode(_spec("a"), TaskRuntime(status=TaskStatus.PENDING, owner="worker-a")),
        )
        self.assertEqual(p.ready(), [])

    def test_non_pending_not_ready(self):
        # 5. 非 PENDING 状态均不出现在 ready()
        for st in (TaskStatus.IN_PROGRESS, TaskStatus.COMPLETED,
                   TaskStatus.FAILED, TaskStatus.BLOCKED):
            with self.subTest(status=st):
                p = _plan_with(
                    TaskNode(_spec("a"), TaskRuntime(status=st, owner=None)),
                )
                self.assertEqual(p.ready(), [])


class TestPlanValidate(unittest.TestCase):
    """6~10: validate() 的 4 类错误。"""

    def test_missing_dep_raises(self):
        # 6. 依赖不存在
        p = _plan_with(TaskNode(_spec("b", depends_on=("missing_task",))))
        with self.assertRaises(InvalidPlanError) as ctx:
            p.validate()
        self.assertIn("b", str(ctx.exception))
        self.assertIn("missing_task", str(ctx.exception))

    def test_self_dep_raises(self):
        # 7. 自依赖
        p = _plan_with(TaskNode(_spec("a", depends_on=("a",))))
        with self.assertRaises(InvalidPlanError) as ctx:
            p.validate()
        self.assertIn("a", str(ctx.exception))

    def test_two_node_cycle_raises(self):
        # 8. a -> b -> a
        p = _plan_with(
            TaskNode(_spec("a", depends_on=("b",))),
            TaskNode(_spec("b", depends_on=("a",))),
        )
        with self.assertRaises(InvalidPlanError) as ctx:
            p.validate()
        # 错误信息中应包含 cycle / cyclic 字样,且涉及两个节点
        msg = str(ctx.exception).lower()
        self.assertTrue("cyclic" in msg or "cycle" in msg)
        self.assertIn("a", str(ctx.exception))
        self.assertIn("b", str(ctx.exception))

    def test_three_node_cycle_raises(self):
        # 9. a -> b -> c -> a
        p = _plan_with(
            TaskNode(_spec("a", depends_on=("b",))),
            TaskNode(_spec("b", depends_on=("c",))),
            TaskNode(_spec("c", depends_on=("a",))),
        )
        with self.assertRaises(InvalidPlanError):
            p.validate()

    def test_key_id_mismatch_raises(self):
        # 10. 字典 key 和 TaskSpec.id 不一致
        node = TaskNode(_spec("task_b"))  # spec.id == "task_b"
        p = Plan(summary="x", needs_code_change=True, tasks={"task_a": node})
        with self.assertRaises(InvalidPlanError) as ctx:
            p.validate()
        msg = str(ctx.exception)
        self.assertIn("task_a", msg)
        self.assertIn("task_b", msg)


class TestReadyStableOrder(unittest.TestCase):
    """ready() 必须按 tasks 字典插入顺序返回。"""

    def test_ready_returns_in_insertion_order(self):
        p = _plan_with(
            TaskNode(_spec("z")),
            TaskNode(_spec("a")),
            TaskNode(_spec("m")),
        )
        self.assertEqual([n.spec.id for n in p.ready()], ["z", "a", "m"])


if __name__ == "__main__":
    unittest.main()