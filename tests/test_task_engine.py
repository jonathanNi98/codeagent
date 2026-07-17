"""tests/test_task_engine.py — 覆盖 TaskEngine.step() 的 7 个核心场景(对应规范编号同 doc §9.2)。

对应规范编号:
  1. 无 ready → step() 返回 None
  2. 单 ready,成功 → COMPLETED,owner=executor.name
  3. 单 ready,失败 → FAILED,owner 保留
  4. 2 个 ready,step 只 take 第一个(下一次 step 才到第二个)
  5. 依赖链 a→b:第一次 step 跑 a → b 自动解锁 → 第二次 step 处理 b
  6. 任务原 status=IN_PROGRESS 不被 step 抢
  7. claim 失败 → 抛 EngineError,store 中 task 仍 PENDING + owner=None

跑测:
  python -m unittest tests.test_task_engine -v
"""
from __future__ import annotations

import unittest

from core.executor import FailingExecutor, NoopExecutor
from core.task_engine import (
    EngineError,
    StepOutcome,
    TaskEngine,
)
from core.task_state import (
    Plan,
    TaskNode,
    TaskRuntime,
    TaskSpec,
    TaskStatus,
)
from core.task_store import MemoryTaskStore


def _spec(tid: str, action: str = "noop", depends_on=()) -> TaskSpec:
    return TaskSpec(id=tid, action=action, depends_on=depends_on)


def _build_store(*nodes: TaskNode) -> MemoryTaskStore:
    plan = Plan(
        summary="engine test",
        needs_code_change=False,
        tasks={n.spec.id: n for n in nodes},
    )
    return MemoryTaskStore(plan)


class TestNoReady(unittest.TestCase):
    """1: store 中无 ready task → step() 返回 None。"""

    def test_empty_plan_returns_none(self):
        store = _build_store()
        engine = TaskEngine(store, NoopExecutor())
        self.assertIsNone(engine.step())

    def test_all_done_returns_none(self):
        # 都已 COMPLETED,自然不在 ready 中
        store = _build_store(
            TaskNode(_spec("a"), TaskRuntime(status=TaskStatus.COMPLETED, owner="x")),
        )
        engine = TaskEngine(store, NoopExecutor())
        self.assertIsNone(engine.step())

    def test_all_in_progress_returns_none(self):
        # 都被别的 worker 抢了,IN_PROGRESS 也不在 ready 中(§6.3:status != PENDING)
        store = _build_store(
            TaskNode(_spec("a"), TaskRuntime(status=TaskStatus.IN_PROGRESS, owner="other")),
        )
        engine = TaskEngine(store, NoopExecutor())
        self.assertIsNone(engine.step())


class TestSuccessPath(unittest.TestCase):
    """2: 单 ready,成功 → COMPLETED,owner=executor.name。"""

    def test_single_ready_runs_to_completion(self):
        store = _build_store(TaskNode(_spec("a")))
        exe = NoopExecutor()
        engine = TaskEngine(store, exe)

        outcome = engine.step()
        assert outcome is not None, "step() returned None while a task was ready"

        self.assertIsInstance(outcome, StepOutcome)
        self.assertEqual(outcome.task_id, "a")
        self.assertEqual(outcome.final_status, TaskStatus.COMPLETED)
        self.assertTrue(outcome.result.ok)
        self.assertIsNone(outcome.error)

        # store 里的 task 也确实变成了 COMPLETED + owner=NoopExecutor
        node = store.get_task("a")
        self.assertEqual(node.runtime.status, TaskStatus.COMPLETED)
        self.assertEqual(node.runtime.owner, exe.name)


class TestFailurePath(unittest.TestCase):
    """3: 单 ready,失败 → FAILED,owner 保留(便于追溯,见 §6.3.3 不变量 4)。"""

    def test_failing_action_runs_to_failed(self):
        # 用 FailingExecutor,只有 action 含 'boom' 才失败 —— 故意选 "run a boom"
        store = _build_store(TaskNode(_spec("a", action="run a boom")))
        exe = FailingExecutor()
        engine = TaskEngine(store, exe)

        outcome = engine.step()
        assert outcome is not None, "step() returned None while a task was ready"

        self.assertEqual(outcome.task_id, "a")
        self.assertEqual(outcome.final_status, TaskStatus.FAILED)
        self.assertFalse(outcome.result.ok)
        self.assertIsNotNone(outcome.error)

        # owner 保留(失败语义下仍知道是哪个 worker 尝试跑过)
        node = store.get_task("a")
        self.assertEqual(node.runtime.status, TaskStatus.FAILED)
        self.assertEqual(node.runtime.owner, exe.name)


class TestStepTakesOne(unittest.TestCase):
    """4: 2 个 ready,step 只跑 ready[0];下次 step 才到第二个。

    不变量 §6.3.3 #1:一次 step 最多改 1 个 task。
    """

    def test_two_ready_step_processes_first_only(self):
        # 字典插入顺序:z 先 → a 后,Plan.ready() 同顺序(z, a)
        store = _build_store(
            TaskNode(_spec("z")),
            TaskNode(_spec("a")),
        )
        engine = TaskEngine(store, NoopExecutor())

        first = engine.step()
        assert first is not None, "step() returned None while a task was ready"
        self.assertEqual(first.task_id, "z")

        # 第一次 step 后 'z' 已是 COMPLETED,只剩 'a' 在 ready
        ready = store.list_ready()
        self.assertEqual([n.spec.id for n in ready], ["a"])

        # 第二次 step 才轮到 'a'
        second = engine.step()
        assert second is not None, "step() returned None while a task was ready"
        self.assertEqual(second.task_id, "a")
        self.assertEqual(second.final_status, TaskStatus.COMPLETED)

        # 三次 step 后 store 内已无 ready task
        self.assertIsNone(engine.step())


class TestDependencyChain(unittest.TestCase):
    """5: 依赖链 a→b —— 第一次 step 后 b 自动解锁,第二次 step 跑 b。"""

    def test_chain_a_then_b(self):
        store = _build_store(
            TaskNode(_spec("a")),
            TaskNode(_spec("b", depends_on=("a",))),
        )
        engine = TaskEngine(store, NoopExecutor())

        # 第一轮:只有 a ready
        first = engine.step()
        assert first is not None, "step() returned None while a task was ready"
        self.assertEqual(first.task_id, "a")
        self.assertEqual(first.final_status, TaskStatus.COMPLETED)

        # a COMPLETED 后 b 自动解锁
        ready = store.list_ready()
        self.assertEqual([n.spec.id for n in ready], ["b"])

        # 第二轮:跑 b
        second = engine.step()
        assert second is not None, "step() returned None while a task was ready"
        self.assertEqual(second.task_id, "b")
        self.assertEqual(second.final_status, TaskStatus.COMPLETED)

        # 第三轮:全清,无 ready
        self.assertIsNone(engine.step())


class TestInProgressNotStolen(unittest.TestCase):
    """6: 任务原 status=IN_PROGRESS 不被 step 抢(被别的 worker 锁住了)。

    不变量 §6.3.3 #5:不动非 ready 的任务。
    """

    def test_in_progress_not_picked(self):
        # 'a' 已经被别的 worker 抢(不是我们 engine),'b' 才是 ready
        store = _build_store(
            TaskNode(_spec("a"), TaskRuntime(status=TaskStatus.IN_PROGRESS, owner="other")),
            TaskNode(_spec("b")),
        )
        engine = TaskEngine(store, NoopExecutor())

        outcome = engine.step()
        assert outcome is not None, "step() returned None while a task was ready"
        # step 只看到 ready 中的 'b',不会尝试去 claim 'a'
        self.assertEqual(outcome.task_id, "b")

        # 'a' 状态 / owner 完全不变(被别 worker 持有,owner 也不应是我们的 executor)
        node = store.get_task("a")
        self.assertEqual(node.runtime.status, TaskStatus.IN_PROGRESS)
        self.assertEqual(node.runtime.owner, "other")


class TestClaimFailure(unittest.TestCase):
    """7: list_ready 与 claim_task 之间 store 被外部改动 → EngineError,且 store 不被污染。

    设计 §6.3.2 描述:外部 worker 在两步之间把 task 抢走 / 改了状态。
    这里用一个 MemoryTaskStore + 手工修改 rt 来模拟。
    """

    def test_external_change_between_list_and_claim_raises_engine_error(self):
        # 用一个 hook store:list_ready 之后立刻把 a 的状态改成非 PENDING,
        # 模拟"被外部 worker 在两步之间抢走"。
        from core.task_store import TaskStore, TaskClaimError

        class _RaceStore:
            """模拟"list_ready 之后立刻改 store",触发 claim 失败。

            严格实现 TaskStore Protocol —— step() 实际只用到 list_ready /
            claim_task / update_status;其它方法(Protocol shape 完整性需要)
            委托给 inner。
            """

            def __init__(self, inner: MemoryTaskStore) -> None:
                self._inner = inner

            def list_ready(self):
                # 第一次 list_ready 看到 'a' ready,顺手把它的 status 改成 IN_PROGRESS(owner=external)
                ready = self._inner.list_ready()
                if ready and self._inner.get_task("a").runtime.status == TaskStatus.PENDING:
                    node = self._inner.get_task("a")
                    node.runtime.status = TaskStatus.IN_PROGRESS
                    node.runtime.owner = "external-worker"
                return ready

            def claim_task(self, task_id, owner):
                # 现在 task 已经被 external-worker 设到 IN_PROGRESS,
                # MemoryTaskStore.claim_task 会抛 TaskClaimError(stale)。
                return self._inner.claim_task(task_id, owner)

            def update_status(self, task_id, status):
                return self._inner.update_status(task_id, status)

            # step() 不会调到这些,但 TaskEngine.__init__ 要求 store 满足 Protocol ——
            # 这里委托给 inner,语义上等价"对外暴露 inner 的视图,只在 list_ready
            # 处做 race 拦截"。
            def get_plan(self) -> Plan:
                return self._inner.get_plan()

            def list_tasks(self) -> list[TaskNode]:
                return self._inner.list_tasks()

            def get_task(self, task_id: str) -> TaskNode:
                return self._inner.get_task(task_id)

        inner = _build_store(TaskNode(_spec("a")))
        store = _RaceStore(inner)
        engine = TaskEngine(store, NoopExecutor())

        # list_ready 看到 ready,在 engine.step() 内:pick=a → claim_task 失败
        with self.assertRaises(EngineError) as ctx:
            engine.step()

        # 错误链里能找到底层 TaskClaimError(cause 属性 + __cause__)
        self.assertIsInstance(ctx.exception.cause, TaskClaimError)
        self.assertIs(ctx.exception.__cause__, ctx.exception.cause)

        # store 中 'a' 不应被我们 engine 污染:是 external-worker 的 IN_PROGRESS,
        # 不是 NoopExecutor 的。
        final = inner.get_task("a")
        self.assertEqual(final.runtime.status, TaskStatus.IN_PROGRESS)
        self.assertEqual(final.runtime.owner, "external-worker")


if __name__ == "__main__":
    unittest.main()
