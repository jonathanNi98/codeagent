"""errors.py — codeagent 自定义异常。

集中放:
- LLMCallError:LLM API 调用最终失败(SDK 已用尽 max_retries)
- AgentTurnError:Agent loop 出现不该继续的状态(max_tokens、未知 stop_reason、循环上界耗尽 等)

被 core.utils 和 agents.{planner,coder} 引用。
"""
from __future__ import annotations

__all__ = [
    "LLMCallError",
    "AgentTurnError",
]


class LLMCallError(Exception):
    """LLM API 调用最终失败(SDK 已用尽 max_retries)。"""
    def __init__(self, original: Exception):
        super().__init__(str(original))
        self.original = original


class AgentTurnError(Exception):
    """Agent loop 出现不该继续的状态:max_tokens、未知 stop_reason、循环上界耗尽 等。"""
    pass
