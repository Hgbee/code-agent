# Design.md — 设计文档

## 1. 项目定位

**代码审查 / 解释 / 生成 Agent**。用户用自然语言提出代码相关需求，Agent 自主读取、检索、执行、编写代码，最终给出有依据的结论——而不是让 LLM 凭空猜测。

技术选型：**Python + LLM 原生 API（OpenAI 兼容协议）**，不依赖重型框架。理由：
1. 作业考察的是 Agent 基础能力（LLM 调用、Prompt 设计、工具集成），手写循环比调框架更能体现对 Agent 设计模式的理解；
2. OpenAI 兼容协议可无缝切换 OpenAI / DeepSeek / 通义千问 / 本地 Ollama，供应商无关；
3. 依赖极少（仅 `openai` SDK），评审者 `pip install` 一条命令即可复现。

## 2. 总体架构

```
┌──────────┐   用户输入    ┌───────────────────────────────┐
│   CLI    │ ───────────→ │           Agent               │
│ (cli.py) │              │  (agent.py)                   │
└──────────┘ ←─────────── │  messages[] ← 上下文记忆       │
   最终回答                └──────┬────────────────▲───────┘
                                 │ 推理: 该调工具吗? │ 工具结果回传
                                 ▼                │
                        ┌─────────────────┐ ┌─────┴────────┐
                        │ LLM Client      │ │ ToolRegistry │
                        │ (重试/退避)      │ │ (tools.py)   │
                        └─────────────────┘ └──────────────┘
                          read_file / write_file / list_files
                          search_code / run_python （沙箱内）
```

### Agent 循环（核心设计模式：ReAct）

```
for step in 1..max_steps:
    message = LLM(messages, tools)        # ① 推理
    if message 无 tool_calls:             # ② 无需工具 → 产出最终回答, break
        return message.content
    for tc in message.tool_calls:         # ③ 执行全部工具调用
        result = ToolRegistry.execute(tc.name, tc.args)
        messages.append(tool: result)     # ④ 结果回传, 进入下一轮推理
else: 强制停止（防死循环）
```

关键点：
- **LLM 拥有决策权**：是否调用工具、调用哪个、传什么参数、何时停止，全由模型基于 function-calling 自主决定，这正是 Agent 区别于"固定流水线"的本质。
- **观察-行动循环**：工具结果（Observation）追加进对话历史，模型据此修正下一步行动（Action），即 ReAct 模式。

## 3. 模块设计

| 模块 | 职责 | 关键设计 |
|------|------|----------|
| `config.py` | 配置加载、系统 Prompt | dataclass + 环境变量，全部有默认值；Prompt 定义角色、工具用法与 4 条工作准则（先读代码再回答等） |
| `agent.py` | Agent 循环、LLM 客户端 | `LLMClient` 为 `Protocol`，测试用 `MockLLM` 注入，无需联网即可端到端测试；LLM 调用失败**指数退避重试** |
| `tools.py` | 工具注册中心 | 工具 = Python 函数 + JSON Schema，`_add()` 一处注册两份数据，新增工具只加一个函数 |
| `cli.py` | 交互 | REPL + `/help /tools /reset /exit` 命令 |

## 4. 关键设计决策

### 4.1 沙箱安全
所有文件工具经 `_resolve()` 统一解析路径：先 `resolve()` 再校验 `is_relative_to(workspace)`，**从根上拦截 `../` 路径穿越**；读取限制文本后缀白名单，防止误读二进制；`run_python` 用子进程 + `cwd=沙箱` + 超时强杀。

### 4.2 错误处理策略（错误也是信息）
- **工具错误不抛异常**：`ToolRegistry.execute` 捕获一切异常，把 `"工具执行出错: ..."` 作为结果回传 LLM，让模型看到错误后自行调整（换路径、改参数、改方案）——这是 Agent 鲁棒性的关键；
- **LLM 调用错误重试**：网络/限流类错误指数退避（2s/4s/8s），重试耗尽才向上抛；
- **防死循环**：`max_steps` 上限。

### 4.3 上下文记忆
`messages` 列表自会话开始完整保留（system + 全部 user/assistant/tool 消息），天然支持多轮追问与跨轮工具结果引用；`/reset` 重建。

### 4.4 可测试性
`MockLLM` 按"脚本"依次返回预设的 tool_calls / content，在**零网络依赖**下验证：完整循环、记忆保留、错误回传三条路径。

## 5. 边界情况覆盖

| 边界情况 | 处理 |
|----------|------|
| 路径穿越 `../` | 沙箱校验拒绝 |
| 文件不存在 / 二进制文件 | 返回错误文本给 LLM |
| 工具参数 JSON 非法 | 捕获解析错误，按空参数处理 |
| 代码死循环 | 子进程超时强杀 |
| LLM 限流/断网 | 指数退避重试 3 次 |
| Agent 无限调工具 | max_steps 强制停止 |
| 输出过长 | read/run/search 各自截断上限 |

## 6. 未来扩展

- 流式输出（SSE）；Web UI（FastAPI + WebSocket）
- 更多工具：git diff、AST 静态分析、网页检索
- 记忆压缩（长对话摘要）、子 Agent 协作（审查员+修复员）
