"""tests/test_task_store.py — 覆盖 MemoryTaskStore 的 8 个核心场景。

本文件目前以注释形式给出 v0.3.0 第一阶段的参考测试,等评审通过后
把代码从 # 号注释里"解开"即可用 unittest 跑。

对应规范编号:
  11. 成功认领 ready task(PENDING+owner=None -> IN_PROGRESS+owner="main")
  12. 不能认领不存在的 Task             -> TaskNotFoundError
  13. 不能认领已经被认领的 Task         -> TaskClaimError
  14. 不能认领依赖未完成的 Task         -> TaskClaimError
  15. owner 不能为空("" / "   " 都失败)
  16. COMPLETED 不能重新改为 IN_PROGRESS
  17. FAILED 可以重置为 PENDING(owner 清空)
  18. BLOCKED 可以重置为 PENDING(owner 清空)

跑测:
  python -m unittest tests.test_task_store -v
"""
from __future__ import annotations


# ---------------------------------------------------------------------------
# 参考实现 —— 已解开,跑 python -m unittest tests.test_task_store -v
# ---------------------------------------------------------------------------

import unittest

from core.task_state import (
    Plan,
    TaskNode,
    TaskRuntime,
    TaskSpec,
    TaskStatus,
)
from core.task_store import (
    InvalidTaskTransitionError,
    MemoryTaskStore,
    TaskClaimError,
    TaskNotFoundError,
)


def _build_store(*nodes: TaskNode, needs_code_change: bool = True) -> MemoryTaskStore:
    plan = Plan(
        summary="store test",
        needs_code_change=needs_code_change,
        tasks={n.spec.id: n for n in nodes},
    )
    return MemoryTaskStore(plan)  # 构造时即 validate()


def _completed(tid: str) -> TaskNode:
    """一个已完成、可被其他任务依赖的任务。"""
    return TaskNode(
        TaskSpec(id=tid, action="noop"),
        TaskRuntime(status=TaskStatus.COMPLETED, owner="setup"),
    )


class TestClaim(unittest.TestCase):
    """11~15: claim_task。"""

    def test_claim_ready_task(self):
        # 11. 成功认领
        store = _build_store(TaskNode(TaskSpec(id="a", action="x")))
        node = store.claim_task("a", "main")
        self.assertEqual(node.runtime.status, TaskStatus.IN_PROGRESS)
        self.assertEqual(node.runtime.owner, "main")

    def test_claim_nonexistent_raises(self):
        # 12. 认领不存在的任务 -> TaskNotFoundError
        store = _build_store(TaskNode(TaskSpec(id="a", action="x")))
        with self.assertRaises(TaskNotFoundError):
            store.claim_task("ghost", "main")

    def test_claim_already_claimed_raises(self):
        # 13. 已被认领 -> TaskClaimError
        store = _build_store(TaskNode(TaskSpec(id="a", action="x")))
        store.claim_task("a", "worker-1")
        with self.assertRaises(TaskClaimError):
            store.claim_task("a", "worker-2")

    def test_claim_dep_not_done_raises(self):
        # 14. 依赖未完成 -> TaskClaimError
        store = _build_store(
            TaskNode(TaskSpec(id="a", action="x")),
            TaskNode(TaskSpec(id="b", action="y", depends_on=("a",))),
        )
        with self.assertRaises(TaskClaimError) as ctx:
            store.claim_task("b", "main")
        self.assertIn("a", str(ctx.exception))

    def test_claim_empty_owner_raises(self):
        # 15. owner 为空 / 全空白 -> 失败
        store = _build_store(TaskNode(TaskSpec(id="a", action="x")))
        for bad in ("", "   "):
            with self.subTest(owner=bad):
                with self.assertRaises(TaskClaimError):
                    store.claim_task("a", bad)
        # 确认任务没被污染
        self.assertEqual(store.get_task("a").runtime.status, TaskStatus.PENDING)
        self.assertIsNone(store.get_task("a").runtime.owner)


class TestUpdateStatus(unittest.TestCase):
    """16~18: update_status 状态机 + owner 处理。"""

    def _claimed(self) -> MemoryTaskStore:
        store = _build_store(TaskNode(TaskSpec(id="a", action="x")))
        store.claim_task("a", "main")
        return store

    def test_completed_cannot_revert_to_in_progress(self):
        # 16. COMPLETED -> IN_PROGRESS 非法
        store = self._claimed()
        store.update_status("a", TaskStatus.COMPLETED)
        with self.assertRaises(InvalidTaskTransitionError):
            store.update_status("a", TaskStatus.IN_PROGRESS)
        # 顺带测一下 COMPLETED -> PENDING 同样非法
        with self.assertRaises(InvalidTaskTransitionError):
            store.update_status("a", TaskStatus.PENDING)

    def test_failed_can_reset_to_pending_clears_owner(self):
        # 17. FAILED -> PENDING 允许,且 owner 清空
        store = self._claimed()
        store.update_status("a", TaskStatus.FAILED)
        node = store.update_status("a", TaskStatus.PENDING)
        self.assertEqual(node.runtime.status, TaskStatus.PENDING)
        self.assertIsNone(node.runtime.owner)

    def test_blocked_can_reset_to_pending_clears_owner(self):
        # 18. BLOCKED -> PENDING 允许,且 owner 清空
        store = self._claimed()
        store.update_status("a", TaskStatus.BLOCKED)
        node = store.update_status("a", TaskStatus.PENDING)
        self.assertEqual(node.runtime.status, TaskStatus.PENDING)
        self.assertIsNone(node.runtime.owner)


class TestUpdateStatusOwnerRetention(unittest.TestCase):
    """非编号要求:owner 保留 / 清空规则(sanity check)。"""

    def _claimed(self) -> MemoryTaskStore:
        store = _build_store(TaskNode(TaskSpec(id="a", action="x")))
        store.claim_task("a", "main")
        return store

    def test_completed_keeps_owner(self):
        store = self._claimed()
        store.update_status("a", TaskStatus.COMPLETED)
        self.assertEqual(store.get_task("a").runtime.owner, "main")

    def test_failed_keeps_owner(self):
        store = self._claimed()
        store.update_status("a", TaskStatus.FAILED)
        self.assertEqual(store.get_task("a").runtime.owner, "main")


class TestStoreBasics(unittest.TestCase):
    """非编号要求:get_plan / list_tasks / list_ready / get_task 基础接口。"""

    def test_get_plan_returns_same_plan(self):
        store = _build_store(TaskNode(TaskSpec(id="a", action="x")))
        self.assertEqual(store.get_plan().summary, "store test")

    def test_list_tasks_in_insertion_order(self):
        store = _build_store(
            TaskNode(TaskSpec(id="z", action="x")),
            TaskNode(TaskSpec(id="a", action="y")),
        )
        self.assertEqual([n.spec.id for n in store.list_tasks()], ["z", "a"])

    def test_list_ready_matches_plan_ready(self):
        store = _build_store(
            _completed("a"),
            TaskNode(TaskSpec(id="b", action="y", depends_on=("a",))),
            TaskNode(TaskSpec(id="c", action="z")),
        )
        self.assertEqual([n.spec.id for n in store.list_ready()], ["b", "c"])

    def test_get_task_missing_raises(self):
        store = _build_store(TaskNode(TaskSpec(id="a", action="x")))
        with self.assertRaises(TaskNotFoundError):
            store.get_task("ghost")


class TestInvalidPlanRejectedAtConstruction(unittest.TestCase):
    """非编号要求:构造时即校验,坏 Plan 拿不到 store。"""

    def test_cyclic_plan_rejected(self):
        bad_plan = Plan(
            summary="bad",
            needs_code_change=True,
            tasks={
                "a": TaskNode(TaskSpec(id="a", action="x", depends_on=("b",))),
                "b": TaskNode(TaskSpec(id="b", action="y", depends_on=("a",))),
            },
        )
        with self.assertRaises(Exception):  # InvalidPlanError
            MemoryTaskStore(bad_plan)


if __name__ == "__main__":
    unittest.main()