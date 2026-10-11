"""Agent 核心：实现 输入 → 推理 → 工具调用 → 输出 的循环，带上下文记忆与重试。"""
from __future__ import annotations

import json
import time
from typing import Any, Protocol

from .config import Config, SYSTEM_PROMPT
from .tools import ToolRegistry


class LLMClient(Protocol):
    """LLM 客户端接口：便于测试时用 Mock 替换真实 API。"""

    def chat(self, messages: list[dict], tools: list[dict]) -> dict[str, Any]: ...


class OpenAICompatClient:
    """OpenAI 兼容协议客户端（OpenAI / DeepSeek / 通义千问 / Ollama 均可用）。"""

    def __init__(self, cfg: Config):
        from openai import OpenAI
        self.cfg = cfg
        self.client = OpenAI(api_key=cfg.api_key or "EMPTY", base_url=cfg.base_url)

    def chat(self, messages: list[dict], tools: list[dict]) -> dict[str, Any]:
        last_err: Exception | None = None
        for attempt in range(1, self.cfg.api_retries + 1):
            try:
                resp = self.client.chat.completions.create(
                    model=self.cfg.model,
                    messages=messages,
                    tools=tools if tools else None,
                    temperature=0.3,
                )
                return resp.choices[0].message
            except Exception as e:  # 网络超时 / 限流 / 服务端错误 → 指数退避重试
                last_err = e
                if attempt < self.cfg.api_retries:
                    wait = 2 ** attempt
                    print(f"  [LLM 调用失败({attempt}/{self.cfg.api_retries}): {e}，{wait}s 后重试]")
                    time.sleep(wait)
        raise RuntimeError(f"LLM 调用在 {self.cfg.api_retries} 次重试后仍失败: {last_err}")


class Agent:
    """代码助手 Agent。"""

    def __init__(self, cfg: Config, client: LLMClient | None = None):
        self.cfg = cfg
        self.tools = ToolRegistry(cfg)
        self.client = client or OpenAICompatClient(cfg)
        self.messages: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}]

    # ---------- 记忆管理 ----------
    def reset(self) -> None:
        """清空对话历史，开始新会话。"""
        self.messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    # ---------- Agent 主循环 ----------
    def run(self, user_input: str) -> str:
        """处理一次用户输入，返回 Agent 最终的文本回答。

        循环: 用户输入 → LLM 推理 → (工具调用 → 结果回传 → 再推理)* → 最终输出
        """
        self.messages.append({"role": "user", "content": user_input})
        final_text = ""

        for step in range(1, self.cfg.max_steps + 1):
            message = self.client.chat(self.messages, self.tools.schemas)
            tool_calls = getattr(message, "tool_calls", None)

            if not tool_calls:
                final_text = getattr(message, "content", "") or "(模型未返回内容)"
                self.messages.append({"role": "assistant", "content": final_text})
                break

            # 记录 assistant 的工具调用意图
            self.messages.append({
                "role": "assistant",
                "content": getattr(message, "content", None),
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                    }
                    for tc in tool_calls
                ],
            })

            # 逐个执行工具，把结果回传给 LLM
            for tc in tool_calls:
                name = tc.function.name
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}
                print(f"  [调用工具] {name}({json.dumps(args, ensure_ascii=False)[:120]})")
                result = self.tools.execute(name, args)
                print(f"  [工具结果] {result[:100].replace(chr(10), ' | ')}")
                self.messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})
        else:
            final_text = f"已达到最大推理步数({self.cfg.max_steps})，为避免死循环强制停止。"
            self.messages.append({"role": "assistant", "content": final_text})

        return final_text
