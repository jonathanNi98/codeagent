"""utils.py — 跨 agent / pipeline 的小工具集。

本模块是跨多个 agent / pipeline 共享的"基础工具":
- call_llm:包一层 SDK 异常 -> LLMCallError(Layer A 翻译)
- 重导出 LLMCallError / AgentTurnError(实际定义在 core.errors),方便一处 import

不依赖任何 agent(避免循环),被 core.pipeline / agents.planner / agents.coder 引用。
"""
from __future__ import annotations

import anthropic

from core.errors import LLMCallError, AgentTurnError  # 重导出,方便 `from core.utils import AgentTurnError`

__all__ = [
    "LLMCallError",
    "AgentTurnError",
    "call_llm",
]


# ---------------------------------------------------------------------------
# call_llm —— 翻译 SDK 异常(实际 per-call retry 由 SDK 内部 max_retries 处理)
# ---------------------------------------------------------------------------
def call_llm(client, **kwargs):
    """包一层 messages.create;SDK 异常 -> LLMCallError(给 pipeline 捕)。

    SDK 内部已经做了 3 次 max_retries(见 config.make_client 的 max_retries=3)。
    这里只把最后一次 SDK 异常翻译成本模块的 LLMCallError,让上层统一捕获。
    """
    try:
        return client.messages.create(**kwargs)
    except (
        anthropic.APIConnectionError,
        anthropic.APITimeoutError,
        anthropic.RateLimitError,
        anthropic.APIStatusError,
    ) as e:
        raise LLMCallError(e) from e
