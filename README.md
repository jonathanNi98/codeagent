# codeagent

一个最小可跑的**多 agent CLI 代码助手** —— 用户在终端用自然语言下指令，agent 自动调研代码库、改文件、跑测试。

```
user ──► REPL ──► Planner (LLM) ──► Coder (LLM) ──► Runner (shell)
                   只读工具            全工具          跑测试
```

| Agent | 角色 | 允许的工具 |
| --- | --- | --- |
| **Planner** | 读代码、定位问题、出方案 | `list_file` `read_file` `search_file` `run_command` `git_diff` |
| **Coder**   | 按方案改文件 | 上面 + `write_file` |
| **Runner**  | 跑测试命令 | `subprocess` (无 LLM) |

Planner / Coder 都用 MiniMax-M3。

---

## 准备

```bash
cd /Users/jonathan/mcp/codeagent
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# 编辑 .env，填入 MINIMAX_API_KEY 和 MINIMAX_BASE_URL
```

## 跑起来

```bash
python main.py
```

进入 REPL，看到 `❯` 提示符就可以下指令了：

```
❯ Fix the bug in calculator.py where subtract returns the wrong value
```

## 内置命令

| 命令 | 作用 |
| --- | --- |
| `/help`  | 显示命令清单 |
| `/quit`  | 退出（也支持 `/exit`） |
| `/reset` | 清空会话历史（MVP 占位） |
| `/diff`  | 显示最近一次 git diff |

---

## 文件分工

| 文件 | 干什么的 |
| --- | --- |
| `config.py`   | 读 `.env`、暴露 `Config`、构造 LLM client |
| `tools.py`    | 6 个工具：纯函数实现 + JSON Schema + dispatcher |
| `planner.py`  | Planner agent（system prompt + agent loop） |
| `coder.py`    | Coder agent（system prompt + agent loop） |
| `runner.py`   | 跑 `TEST_CMD` 并报告结果 |
| `pipeline.py` | 串起 Plan → Code → Test |
| `ui.py`       | `rich` 渲染（banner / 工具调用行 / panel / spinner） |
| `main.py`     | REPL 入口 |

---

## 接口已铺好，实现你来填

骨架里每个文件都定义好了**接口签名、参数类型、返回值形状、JSON Schema、调用关系**。
所有需要写业务逻辑的函数体我都标了 `raise NotImplementedError("TODO: ...")`，并配了一段说明告诉你该怎么填。

找待办：

```bash
grep -rn "NotImplementedError" --include='*.py' .
```

待填的位置：

- `config.py::make_client` —— 选 OpenAI / Anthropic SDK，构造 client
- `tools.py::_impl_*` —— 6 个工具的真实实现（读文件、grep、shell 等）
- `tools.py::dispatch_tool` —— 调 impl 并格式化结果
- `planner.py` / `coder.py` 里的 `*_SYSTEM_PROMPT` 和 `run()` —— agent 的 system prompt + agent loop
- `runner.py::run_tests` —— subprocess 调用
- `pipeline.py::run` —— 串起三段并按阶段捕获异常
- `ui.py` 里的所有函数 —— rich 渲染细节

填好之后 `python main.py` 就能用了。
# codeagent
