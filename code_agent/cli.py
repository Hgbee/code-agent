"""命令行交互入口：python -m code_agent 或 python main.py"""
from __future__ import annotations

import sys

from .agent import Agent
from .config import load_config

HELP = """命令列表:
  /help    显示本帮助
  /tools   查看可用工具
  /reset   清空对话记忆，开始新会话
  /exit    退出
其余输入将作为自然语言指令交给 Agent 处理。"""


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):  # Windows GBK 控制台兼容
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    mock = "--mock" in sys.argv
    cfg = load_config(mock=mock)
    if not cfg.api_key and not mock:
        print("提示: 未检测到 LLM_API_KEY，请先设置环境变量（详见 README.md）。")
        print("      也可使用离线演示模式: python main.py --mock\n")

    if mock:
        from .mock import DemoLLM
        agent = Agent(cfg, client=DemoLLM(cfg.workspace))
    else:
        agent = Agent(cfg)
    print(f"=== 代码助手 Agent ===  模型: {cfg.model}{' (离线演示模式)' if mock else ''}")
    print(f"工作区沙箱: {cfg.workspace}\n输入 /help 查看命令。\n")

    while True:
        try:
            user_input = input("你> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见!")
            return 0
        if not user_input:
            continue
        if user_input in ("/exit", "/quit"):
            print("再见!")
            return 0
        if user_input == "/help":
            print(HELP)
            continue
        if user_input == "/tools":
            for s in agent.tools.schemas:
                f = s["function"]
                print(f"- {f['name']}: {f['description']}")
            continue
        if user_input == "/reset":
            agent.reset()
            print("已清空对话记忆。\n")
            continue

        try:
            answer = agent.run(user_input)
            print(f"\nAgent> {answer}\n")
        except Exception as e:
            print(f"\n[发生错误] {type(e).__name__}: {e}\n请检查网络与 API Key 配置后重试。\n")


if __name__ == "__main__":
    sys.exit(main())
