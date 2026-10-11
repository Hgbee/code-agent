"""离线测试：不联网，验证工具沙箱安全与 Agent 完整循环。

运行: python -m pytest tests/ -v  （或 python tests/test_agent.py）
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from code_agent.agent import Agent
from code_agent.config import Config, SYSTEM_PROMPT
from code_agent.mock import ScriptedLLM


def make_agent(tmp: Path, script: list[dict]) -> Agent:
    cfg = Config(workspace=str(tmp), mock=True)
    return Agent(cfg, client=ScriptedLLM(script))


# ---------- 工具沙箱测试 ----------
def test_tools_sandbox(tmp_path: Path):
    cfg = Config(workspace=str(tmp_path))
    from code_agent.tools import ToolRegistry
    reg = ToolRegistry(cfg)

    # 写入并读回
    assert "已写入" in reg.execute("write_file", {"path": "a.py", "content": "x = 1\n"})
    assert "x = 1" in reg.execute("read_file", {"path": "a.py"})

    # 目录越界被拒绝
    out = reg.execute("read_file", {"path": "../secret.txt"})
    assert "拒绝访问" in out or "错误" in out

    # run_python 正常执行 & 超时保护
    assert "42" in reg.execute("run_python", {"code": "print(6*7)"})
    cfg.tool_timeout = 1
    assert "超时" in reg.execute("run_python", {"code": "import time; time.sleep(5)"})

    # search_code 命中
    hits = reg.execute("search_code", {"pattern": "x = 1"})
    assert "a.py:1" in hits


# ---------- Agent 循环端到端测试 ----------
def test_agent_full_loop(tmp_path: Path):
    (tmp_path / "buggy.py").write_text("def div(a, b):\n    return a / b\n", encoding="utf-8")
    script = [
        {"calls": [("read_file", {"path": "buggy.py"})]},
        {"calls": [("run_python", {"code": "try:\n    print(1/0)\nexcept ZeroDivisionError as e:\n    print('BUG:', e)"})]},
        {"content": "已读取代码并实际运行验证：`div(a, b)` 未处理 **除零风险**，建议加参数校验。"},
    ]
    agent = make_agent(tmp_path, script)
    answer = agent.run("审查 buggy.py")

    assert "除零" in answer
    # 验证上下文记忆中包含工具结果
    tool_msgs = [m for m in agent.messages if m["role"] == "tool"]
    assert len(tool_msgs) == 2
    assert "a / b" in tool_msgs[0]["content"]

    # 第二轮提问验证记忆保留
    script.append({"content": "如前所述，该函数存在除零风险。"})
    assert "除零" in agent.run("刚才说到什么风险?")


def test_agent_error_feedback(tmp_path: Path):
    """工具报错时错误信息回传 LLM，Agent 循环不中断。"""
    script = [
        {"calls": [("read_file", {"path": "不存在.py"})]},
        {"content": "文件不存在，请先创建。"},
    ]
    agent = make_agent(tmp_path, script)
    answer = agent.run("读一下不存在.py")
    assert "文件不存在" in answer
    assert "不存在.py" in agent.messages[-2]["content"]


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):  # Windows GBK 控制台兼容
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    import tempfile
    ok = 0
    for fn in (test_tools_sandbox, test_agent_full_loop, test_agent_error_feedback):
        with tempfile.TemporaryDirectory() as d:
            fn(Path(d))
        print(f"PASS {fn.__name__}")
        ok += 1
    print(f"\n{ok}/3 tests passed.")
