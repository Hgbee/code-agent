# Code Assistant Agent — 代码助手 Agent

一个基于 LLM 原生 API 的命令行代码助手，专注**代码审查、代码解释与代码生成**。实现了完整的 Agent 循环（输入 → 推理 → 工具调用 → 输出）、5 个沙箱工具、上下文记忆与错误重试。

## 功能特性

- **Agent 核心循环**：LLM 自主决定何时调用工具、调用哪个工具，工具结果回传后继续推理，直到产出最终回答
- **5 个工具**（全部限制在工作区沙箱内，防路径穿越）：
  | 工具 | 功能 |
  |------|------|
  | `read_file` | 读取代码文件 |
  | `write_file` | 将生成的代码写入文件 |
  | `list_files` | 浏览项目目录树 |
  | `search_code` | 正则检索代码内容 |
  | `run_python` | 执行 Python 代码验证逻辑（带超时保护） |
- **上下文记忆**：多轮对话历史完整保留，支持 `/reset` 开新会话
- **错误处理与重试**：LLM 调用失败指数退避重试；工具异常不中断循环，错误信息回传给 LLM 自行修正
- **循环保护**：最大推理步数限制，防止死循环

## 环境要求

- Python 3.10+
- 任一 OpenAI 兼容 LLM 服务（OpenAI / DeepSeek / 通义千问 / 本地 Ollama 均可）

## 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置 LLM（以 DeepSeek 为例，也可换任意 OpenAI 兼容服务）
#    Windows PowerShell:
$env:LLM_API_KEY="sk-你的key"
$env:LLM_BASE_URL="https://api.deepseek.com"
$env:LLM_MODEL="deepseek-chat"
#    Linux/macOS:
export LLM_API_KEY=sk-你的key
export LLM_BASE_URL=https://api.deepseek.com
export LLM_MODEL=deepseek-chat

# 3. （建议）把 Agent 工作区指向你要分析的代码目录
$env:AGENT_WORKSPACE="c:/path/to/your/project"

# 4. 启动
python main.py

# 或不联网先体验离线演示模式（脚本驱动的 Mock LLM）
python main.py --mock
```

## 使用示例

```
你> 帮我审查当前目录下的代码有什么问题
  [调用工具] list_files({})
  [工具结果] a.py ...
  [调用工具] read_file({"path": "a.py"})
  ...
Agent> **a.py 存在除零风险**（第 3 行）……

你> 解释一下 utils.py 里的 parse 函数
Agent> 该函数的作用是……

你> 写一个重试装饰器到 retry.py，并测试它
  [调用工具] write_file({"path": "retry.py", ...})
  [调用工具] run_python({"code": "import retry; ..."})
Agent> 已生成 `retry.py` 并运行测试通过……

命令: /help 帮助 | /tools 查看工具 | /reset 清空记忆 | /exit 退出
```

## 运行测试

```bash
python tests/test_agent.py          # 无需 pytest
# 或
python -m pytest tests/ -v
```

测试覆盖：工具沙箱安全（路径穿越拦截、超时保护）、Agent 完整循环、上下文记忆、工具错误回传。

## 项目结构

```
code-agent/
├── main.py                  # 入口
├── requirements.txt
├── README.md
├── Design.md                # 设计文档
├── code_agent/
│   ├── config.py            # 配置 + 系统 Prompt
│   ├── agent.py             # Agent 循环 + LLM 客户端(重试)
│   ├── tools.py             # 工具注册中心 + 5 个沙箱工具
│   ├── mock.py              # 离线 Mock LLM（演示/测试用）
│   └── cli.py               # 命令行交互
└── tests/test_agent.py      # 离线测试(Mock LLM)
```

## 配置项（环境变量）

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `LLM_API_KEY` | 无 | API 密钥（必填，mock 模式除外） |
| `LLM_BASE_URL` | `https://api.deepseek.com` | OpenAI 兼容服务地址 |
| `LLM_MODEL` | `deepseek-chat` | 模型名 |
| `AGENT_WORKSPACE` | 当前目录 | 工具沙箱根目录 |
| `AGENT_MAX_STEPS` | `12` | 单次任务最大推理步数 |
| `AGENT_TOOL_TIMEOUT` | `15` | 工具执行超时（秒） |
| `AGENT_API_RETRIES` | `3` | LLM 调用重试次数 |
