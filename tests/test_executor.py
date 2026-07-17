"""tests/test_executor.py — 覆盖 Executor 的 8 个核心场景(对应规范编号同 doc §9.1)。

对应规范编号:
  1. NoopExecutor.run(any) → ok=True(多 action subTest)
  2. NoopExecutor.name == "NoopExecutor"
  3. FailingExecutor 含 'boom' → ok=False,error 非空且含 'boom'
  4. FailingExecutor 不含 'boom' → ok=True
  5. FailingExecutor 大写 'BOM' → 不触发(大小写敏感)
  6. FailingExecutor.name == "FailingExecutor"
  7. TaskResult(ok=True, error=...) → 抛 ValueError
  8. TaskResult(ok=False, error=None) → 抛 ValueError

跑测:
  python -m unittest tests.test_executor -v
"""
from __future__ import annotations

import unittest

from core.executor import (
    Executor,
    FailingExecutor,
    NoopExecutor,
    TaskResult,
)
from core.task_state import (
    TaskNode,
    TaskSpec,
)


def _node(action: str = "noop") -> TaskNode:
    """一个最小化的 TaskNode,只关心 spec.action(本模块其他字段用不到)。"""
    return TaskNode(TaskSpec(id="t", action=action))


class TestNoopExecutor(unittest.TestCase):
    """1~2: NoopExecutor 对任何 task 都 ok=True + name 字面量。"""

    def test_noop_returns_ok_for_any_action(self):
        # 1. 任意 action 都返回 ok=True
        exe = NoopExecutor()
        for action in ("", "do:something", "read:foo.py", "boom", "💥", "x" * 4096):
            with self.subTest(action=action):
                result = exe.run(_node(action))
                self.assertTrue(result.ok)
                self.assertIsNone(result.error)

    def test_noop_name_is_literal(self):
        # 2. NoopExecutor.name 字面量
        self.assertEqual(NoopExecutor().name, "NoopExecutor")


class TestFailingExecutor(unittest.TestCase):
    """3~6: FailingExecutor 的"boom"触发规则 + name 字面量。"""

    def test_boom_in_action_fails(self):
        # 3. 包含 'boom' → ok=False,error 非空且含 'boom'
        result = FailingExecutor().run(_node("make a boom: detonate"))
        self.assertFalse(result.ok)
        err = result.error
        assert err is not None, "TaskResult(ok=False) must have non-empty error"
        self.assertIn("boom", err)

    def test_no_boom_succeeds(self):
        # 4. 不含 'boom' → ok=True
        result = FailingExecutor().run(_node("safe action"))
        self.assertTrue(result.ok)
        self.assertIsNone(result.error)

    def test_uppercase_is_not_a_trigger(self):
        # 5. 大写 'BOM' 不触发(大小写敏感,设计上只用一个 literal 字符串)
        for action in ("BOM", "Boom", "BoomBoom", "bOoM"):
            with self.subTest(action=action):
                result = FailingExecutor().run(_node(action))
                self.assertTrue(result.ok)

    def test_failing_name_is_literal(self):
        # 6. FailingExecutor.name 字面量
        self.assertEqual(FailingExecutor().name, "FailingExecutor")


class TestTaskResultInvariant(unittest.TestCase):
    """7~8: TaskResult 的 __post_init__ 不变量。"""

    def test_ok_true_with_error_raises(self):
        # 7. ok=True + 非 None error → 抛 ValueError
        with self.assertRaises(ValueError) as ctx:
            TaskResult(ok=True, error="should not be set")
        self.assertIn("ok=True", str(ctx.exception))

    def test_ok_false_without_error_raises(self):
        # 8. ok=False + None/empty error → 抛 ValueError
        for bad_error in (None, ""):
            with self.subTest(error=bad_error):
                with self.assertRaises(ValueError):
                    TaskResult(ok=False, error=bad_error)


class TestExecutorBaseNotImplemented(unittest.TestCase):
    """非编号要求:基类 Executor.run 直接调用应抛 NotImplementedError。

    这是 Protocol 风格基类的契约 —— 子类必须实现 run(),否则就是用错了。
    """

    def test_base_executor_run_raises(self):
        # 通过子类(因为 Executor 不是 abstract,本身可以实例化)再调 run,
        # 这样验证"默认实现"语义,符合设计 §5.1。
        class _Bare(Executor):
            name = "Bare"
        with self.assertRaises(NotImplementedError):
            _Bare().run(_node())


if __name__ == "__main__":
    unittest.main()
