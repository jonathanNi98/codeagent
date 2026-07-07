# codeagent

> 一个最小可跑的**多 agent CLI 代码助手** —— 用户在终端用自然语言下指令，agent 自动调研代码库、改文件、跑测试。
>
> A minimal multi-agent CLI code assistant — user issues plain-language directives in the terminal; the agents investigate the codebase, edit files, and run tests automatically.

```
user ──► REPL ──► Planner (LLM) ──► Coder (LLM) ──► Runner (shell)
                   只读 / read-only        全工具 / full          测试 / tests
```

---

## 快速开始 / Quick Start

```bash
# 安装 / Install
cd /Users/jonathan/mcp/codeagent
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 配置 / Configure
cp .env.example .env
# 编辑 .env,填入 MINIMAX_API_KEY + MINIMAX_BASE_URL(必填)/ required
# MINIMAX_MODEL_NAME    (可选 / optional,默认 "MiniMax-M3")
# AGENT_WORKDIR         (可选 / optional,默认 "./test_target")
# TEST_CMD              (可选 / optional,默认 "pytest -q")
# MAX_TOOL_ITERATIONS   (可选 / optional,默认 12)

# 启动 / Run
python main.py
```

进入 REPL 看到 `❯` 提示符就可以下指令 / At the `❯` prompt, type your task:

```
❯ Fix the bug in calculator.py where subtract returns the wrong value
```

---

## 架构 / Architecture

### 三阶段流水线 / Three-stage pipeline

```
┌───────────┐    ┌─────────┐    ┌─────────┐    ┌─────────┐
│   User    │──►│ Planner │──►│  Coder  │──►│  Runner │──► result
│ (REPL)    │    │  (LLM)  │    │  (LLM)  │    │  (subprocess)
└───────────┘    └─────────┘    └─────────┘    └─────────┘
                    │              │
                    ▼              ▼
                只读工具        全工具 + 白名单
              read-only         full + allowlist
```

| Agent   | 角色 / Role                                | 允许的工具 / Allowed tools                                |
|---------|--------------------------------------------|---------------------------------------------------------|
| Planner | 读代码、出方案 / Read code, propose plan    | `list_file` `read_file` `search_file` `run_command` `git_diff` |
| Coder   | 按方案改文件 / Implement plan              | 上表 5 项 + `write_file` (+ 强制白名单 / with allowlist) |
| Runner  | 跑测试 / Run test command                  | `subprocess` (无 LLM / no LLM)                          |

### Plan JSON Schema(v0.1.0 起 / since v0.1.0)

Planner 输出一个 **JSON 对象**(不再是自然语言),供 Pipeline 校验、给 Coder 看。

```json
{
  "needs_code_change": true,
  "summary": "Fix off-by-one error in subtract()",
  "steps": ["Read file", "Identify bug", "Patch"],
  "files_to_modify": ["calculator.py"]
}
```

字段 / Fields:
- `needs_code_change: bool` —— 门控开关 / gate switch (`false` ⇒ 走 Answer,跳过 Coder / skip Coder)
- `summary: str` —— 给 Coder + UI 看 / for Coder + UI
- `steps: list[str]` —— 步骤描述 / step descriptions
- `files_to_modify: list[str]` —— Coder 可写的文件 / files Coder may write (allowlist 源头 / allowlist source)

校验逻辑 / Validation: `core/planner_schema.py::parse_plan()`,失败抛 `PlanParseError`。

---

## 版本历史 / Version History

> 按 `git tag` 排序,描述"那个 tag 点上系统长什么样 + 关键改动"。
> Listed by `git tag`, describing what the system looked like at that tag + key changes.

### `v0.2.0` (current) — Plan schema + History + 3-layer retry

**Tag 位置 / tag points to**: `0758413` — `feat(code_agent): add 3-layer auto-retry with bound agent loops`

**这一版做了什么 / What this release does**:

#### 1. Plan JSON schema + Pipeline 门控 / Plan JSON schema + Pipeline gating
- `core/planner_schema.py` 新建:`Plan` frozen dataclass + `parse_plan()` 解析 + 校验 / new module with `Plan` frozen dataclass, `parse_plan()` parses + validates
- `core/pipeline.py` 用 `parse_plan()` 解析 Planner 输出 / parses Planner output
- 门控逻辑: `needs_code_change=false` ⇒ 直接展示 `summary` 为 Answer,跳过 Coder + Runner / direct show `summary` as Answer, skip Coder + Runner

#### 2. Session-level history with 3-tier compaction
- 新增 `core/history.py`: `SessionTurn` + `CompactedHistory` + `compact_history()` + `format_session_context()` / new module
- `main.py` 模块级维护 `session_history`,每轮 append 一条 `SessionTurn` / module-level `session_history` maintained, each turn appends a `SessionTurn`
- 3-tier: `head` (第 1 轮作为任务锚点 / first turn as task anchor) + `middle` (每轮 1 行 heuristic 压缩 / per-turn 1-line heuristic compression) + `recent` (最近 3 轮完整保留 / last 3 turns kept in full)
- 上下文通过 `=== SESSION CONTEXT === / === END === / === CURRENT REQUEST ===` 边界标记注入到 Planner / Coder 的 user message / context injected via boundary markers into Planner / Coder user message
- `agents/planner.py` 和 `agents/coder.py` 都加了 `session_context: str = ""` 参数 / both agents got a `session_context: str = ""` parameter
- `agents.coder.run` 的死参数 `history` 被删除 / removed dead `history` parameter

#### 3. 3-layer auto-retry / 3-layer auto-retry
- **Layer A (API)**:`core/config.py::make_client` 加 `max_retries=3` —— Anthropic SDK 自带 per-call exp backoff + jitter / Anthropic SDK provides per-call exp backoff + jitter
- **Layer B (parse_plan)**:`core/planner_schema.py::plan_with_retries()` 循环 3 次,失败时把 `PlanParseError` 信息注回 user_msg 尾部让 LLM 自纠 / loops 3 times, injects `PlanParseError` info into user_msg tail for LLM self-correction
- **Layer C (test → coder)**:`core/pipeline.py` 把 coder + runner 包成 `for attempt in range(3):` 循环 / wraps coder + runner in `for attempt in range(3):` loop
  - Test fail 时,截断 `last_test_output` 为 `头 100 + 尾 500` 字符,作为 `test_feedback` 喂回 Coder / On test failure, truncate `last_test_output` to head 100 + tail 500 chars, feed back to Coder as `test_feedback`
  - Coder user message 加 `=== Previous test failure (please fix) === / === END ===` 块 / adds `=== Previous test failure (please fix) === / === END ===` block

#### 4. Bound agent loops + 类型安全 / Bound agent loops + type safety
- `agents/{planner,coder}.py` 把 `while True:` 换成 `for _ in range(cfg.max_tool_iterations):` —— 防止 `max_tokens` 死循环 / prevent `max_tokens` infinite loop
- 加上 `if resp.stop_reason != "tool_use": raise AgentTurnError(...)` —— `max_tokens` / 未知 stop_reason 不再悄悄落入 tool 分支 / no longer silently falls into tool branch
- 循环耗尽时显式 `raise AgentTurnError(...)` —— `-> str` 类型合约成立 / `-> str` type contract holds

#### 5. 配置项 / Configuration
- `Config` 加字段 `max_tool_iterations: int = 12` / new field `max_tool_iterations: int = 12`
- `.env` 里可配 `MAX_TOOL_ITERATIONS=N` 覆盖 / overridable via `MAX_TOOL_ITERATIONS=N` in `.env`

#### 6. 模块重构 / Module restructure
- `core/retry.py` 拆成 `core/utils.py` (call_llm + 异常重导出) + `core/errors.py` (异常类)/ split into `core/utils.py` (call_llm + error re-exports) + `core/errors.py` (exception classes)
- `plan_with_retries` 跟 `Plan` 同住 `core/planner_schema.py` —— 破循环 import / move to break circular import via late local import
- 删掉 `core/retry.py` / `core/retry.py` deleted

**已知限制 / Known limitations**:
- parse_plan 校验在 `needs_code_change=false` 时**只强制 `files_to_modify` 为空**,步骤可非空(LLM 想列推理就让它列) / parse_plan only enforces `files_to_modify` is empty; steps may be non-empty
- Test feedback 截断策略比较暴力(头 100 + 尾 500),不智能摘要 / Test feedback truncation is simple (head 100 + tail 500), not smart summarization
- Retry 不感知"同一个错误反复出"——只有 3 次硬性上界 / Retry has no thrash detection
- `/diff` 还是占位 / `/diff` is still placeholder

**Issue tracker(本版相关)**:
- `agents/parse_plan_relaxation.md` —— parse_plan 校验详细 bug 报告(已修复 / fixed)

---

### `v0.1.0` — Coder 自动改文件防护 / Coder auto-edit protection

**Tag 位置 / tag points to**: `2104b81` — `fix(code_agent): prevent Coder from auto-editing on non-plan inputs`

**这一版做了什么 / What this release does**:
- Coder prompt 加 REFUSAL RULE: 输入不像 plan 就拒绝改文件 / Coder prompt gains REFUSAL RULE
- `Plan.summary` 当 Answer 显示 / `Plan.summary` shown as Answer
- 跨文件修改按 `files_to_modify` 列表约束(只 Coder 写时强制,本版本只是 prompt-level) / cross-file edits constrained per `files_to_modify` list (only Coder time, this is prompt-level)

**基础 MVP / Base MVP**: `c8c1371` — `feat(code_agent): mvp for code_agent`
- 6 工具 + dispatcher / 6 tools + dispatcher
- 三阶段流水线 / three-stage pipeline
- rich 渲染 / rich rendering
- REPL 入口 / REPL entry point

---

## 命令 / Commands (REPL 内 / Inside REPL)

| 命令 / Command | 作用 / Effect                                                          |
|---------------|-----------------------------------------------------------------------|
| `/help`       | 显示命令清单 / show command list                                      |
| `/quit`       | 退出 (`/exit`, `/q`) / exit                                          |
| `/reset`      | 清空 session 上下文(从 v0.2.0 起真清空)/ clear session context (v0.2.0+ actually clears)|
| `/diff`       | 显示最近一次 git diff(还是占位 / placeholder)                            |

---

## 配置 / Configuration

`.env` 变量说明 / `.env` variables:

| 变量 / Variable | 必填 / Required | 默认 / Default | 说明 / Description                                                                                  |
|--------------|--------|--------------|--------------------------------------------------------------------------------------------------|
| `MINIMAX_API_KEY`   | ✅ | —            | LLM provider key                                                                                  |
| `MINIMAX_BASE_URL`  | ✅ | —            | e.g. `https://api.example.com/v1`                                                                |
| `MINIMAX_MODEL_NAME`| ❌ | `MiniMax-M3` | 调用的模型 / model name                                                                          |
| `AGENT_WORKDIR`     | ❌ | `./test_target` | Planner / Coder / Runner 工作目录(写文件沙盒约束) / working directory (write file sandbox) |
| `TEST_CMD`          | ❌ | `pytest -q`  | Runner 跑的命令 / command run by Runner                                                        |
| `MAX_TOOL_ITERATIONS`| ❌ | `12`         | 每个 agent tool-call 上界 / per-agent tool-call ceiling                                          |

---

## 文件结构 / File Structure

```
.
├── main.py              # REPL 入口 / REPL entry
├── tools.py             # 6 tools + dispatch_tool
├── ui.py                # rich 渲染(banner / panel / spinner / prompt)/ rich rendering
├── agents/
│   ├── planner.py       # Planner agent loop (with session_context + call_llm + max_tokens guard)
│   ├── coder.py         # Coder agent loop(with test_feedback + write_file allowlist)
│   └── runner.py        # subprocess 跑测试 / subprocess test runner
└── core/
    ├── config.py        # 读 .env, Config 冻结 dataclass, make_client
    ├── errors.py        # LLMCallError + AgentTurnError
    ├── history.py       # SessionTurn + 3-tier compaction + format_session_context
    ├── pipeline.py      # Planner -> Coder (test 循环) -> Runner 编排
    ├── planner_schema.py # Plan dataclass + parse_plan + plan_with_retries
    └── utils.py         # call_llm (Layer A 包装) + error re-exports
```

**依赖 / Dependencies**:
- `anthropic>=0.30.0` —— 主 LLM SDK(用的是 Anthropic 兼容端点 / uses Anthropic-compatible endpoint)
- `python-dotenv>=1.0.0` —— `.env` 读取 / `.env` loader
- `rich>=13.0.0` —— 终端渲染 / terminal rendering

不引入 tenacity / hand-roll retry 这些,Anthropic SDK 自带 per-call 重试 / no `tenacity`, `tenacity` not used; Anthropic SDK has built-in per-call retry.

---

## 下一轮预告 / Next Round

1. **Thrash 检测** —— `plan_with_retries` 在错误 fingerprint 重复出现 N 次时自动停止,避免哑火死转 / auto-stop when error fingerprint repeats, avoid dummied-out thrashing
2. **LLM-based middle summarization** —— 取代 per-turn 1-line heuristic,用 LLM 真正摘要中间轮次 / replace 1-line heuristic with real LLM summary of middle turns
3. **Token budget + auto-compact** —— `call_llm` 后查 usage,触发了自动压 session_history / check usage after `call_llm`, trigger auto-compress of `session_history`
4. **手动 `/compress [focus]` 命令** —— 两家参考都有的 / present in both Claude Code and hermes-agent
5. **`/diff` 真落地** —— 展示最近一次 pipeline 的 artifact / implement to actually surface last pipeline's artifact

---

## 复现 / Reproducibility

- 模型: `MiniMax-M3` (在 `.env::MINIMAX_MODEL_NAME` 可覆盖)
- 所有 `git tag` 的源码都对应一个明确的状态:`git checkout v0.1.0` / `git checkout v0.2.0` / etc.
- Issue: `agents/parse_plan_relaxation.md`(v0.2.0 的 parse_plan 校验相关)

---

_Last updated: 2026-07 · v0.2.0_
