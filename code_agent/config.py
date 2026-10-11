"""配置模块：通过环境变量加载，所有选项均有合理默认值。"""
from __future__ import annotations

import os
from dataclasses import dataclass, field


def _env(key: str, default: str) -> str:
    return os.environ.get(key, default).strip()


@dataclass
class Config:
    # LLM 服务配置（OpenAI 兼容协议，可接 OpenAI / DeepSeek / 通义千问 / 本地 Ollama 等）
    api_key: str = field(default_factory=lambda: _env("LLM_API_KEY", ""))
    base_url: str = field(default_factory=lambda: _env("LLM_BASE_URL", "https://api.deepseek.com"))
    model: str = field(default_factory=lambda: _env("LLM_MODEL", "deepseek-chat"))

    # Agent 配置
    max_steps: int = field(default_factory=lambda: int(_env("AGENT_MAX_STEPS", "12")))  # 防止死循环
    tool_timeout: int = field(default_factory=lambda: int(_env("AGENT_TOOL_TIMEOUT", "15")))  # 工具执行超时(秒)
    api_retries: int = field(default_factory=lambda: int(_env("AGENT_API_RETRIES", "3")))  # LLM 调用重试次数

    # 工作区（沙箱根目录，工具只能访问该目录内的文件）
    workspace: str = field(default_factory=lambda: os.path.abspath(_env("AGENT_WORKSPACE", os.getcwd())))

    # 离线演示模式（不联网，用本地脚本驱动的 Mock LLM）
    mock: bool = False


SYSTEM_PROMPT = """你是一个专业的代码助手 Agent，擅长代码审查、代码解释与代码生成。

你可以调用工具来完成任务：
- read_file / list_files / search_code：读取、浏览、检索用户项目中的代码
- write_file：将生成的代码写入文件
- run_python：执行短小的 Python 代码片段以验证逻辑

工作准则：
1. 回答代码相关问题前，先用工具阅读相关代码，不要凭空猜测。
2. 审查代码时，指出潜在 Bug、代码坏味道，并给出具体可执行的改进建议。
3. 写文件或执行代码前先说明你要做什么。
4. 最终回答使用简体中文，条理清晰，关键结论加粗。"""


def load_config(mock: bool = False) -> Config:
    cfg = Config()
    cfg.mock = mock
    return cfg
