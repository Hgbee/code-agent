"""离线演示用 Mock LLM：不联网即可体验完整 Agent 循环。"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def make_message(content: str | None = None, calls: list[tuple[str, dict]] | None = None):
    """构造 OpenAI SDK 风格的 message 对象（content 和/或 tool_calls）。"""

    class TC:
        def __init__(self, name: str, args: dict):
            self.id = f"call_{name}"
            self.function = type("F", (), {"name": name, "arguments": json.dumps(args)})()

    class Msg:
        def __init__(self, content, tool_calls):
            self.content = content
            self.tool_calls = tool_calls

    tcs = [TC(n, a) for n, a in (calls or [])]
    return Msg(content, tcs or None)


class ScriptedLLM:
    """按预设脚本依次返回响应，用于自动化测试。"""

    def __init__(self, script: list[dict]):
        self.script = script
        self.i = 0

    def chat(self, messages, tools):
        step = self.script[min(self.i, len(self.script) - 1)]
        self.i += 1
        return make_message(step.get("content"), [tuple(x) for x in step.get("calls", [])])


class DemoLLM:
    """离线演示：模拟一次『浏览目录 → 读取首个 Python 文件 → 给出点评』的 Agent 流程。"""

    def __init__(self, workspace: str):
        self.workspace = workspace
        self.step = 0

    def chat(self, messages: list[dict], tools) -> Any:
        def last_tool_result() -> str:
            for m in reversed(messages):
                if m.get("role") == "tool":
                    return m.get("content", "")
            return ""

        self.step += 1
        if self.step == 1:
            return make_message(calls=[("list_files", {})])
        if self.step == 2:
            listing = last_tool_result()
            first_py = next((ln for ln in listing.splitlines() if ln.strip().endswith(".py")), "")
            if first_py:
                return make_message(calls=[("read_file", {"path": first_py.strip()})])
            return make_message("【离线演示】当前工作区没有 Python 文件，请用 /exit 退出后把 AGENT_WORKSPACE 指向你的项目目录再试。")
        if self.step == 3:
            code = last_tool_result()
            head = "\n".join(code.splitlines()[:8])
            return make_message(
                "【离线演示】我已通过工具读取该文件，内容预览：\n```python\n" + head + "\n```\n"
                "在线模式下我会继续深入分析并给出审查意见。设置 LLM_API_KEY 后即可使用真实模型。"
            )
        return make_message("【离线演示】本会话脚本已结束，请 /reset 后重来，或配置真实 API Key 体验完整能力。")
