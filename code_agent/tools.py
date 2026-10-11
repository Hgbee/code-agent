"""工具集：Agent 可调用的 5 个工具，全部限制在 workspace 沙箱内执行。"""
from __future__ import annotations

import fnmatch
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

from .config import Config

# 可读取/写入的文本文件后缀（防止误读二进制文件）
TEXT_SUFFIXES = {
    ".py", ".js", ".ts", ".tsx", ".jsx", ".java", ".c", ".cpp", ".h", ".go",
    ".rs", ".rb", ".php", ".sh", ".bat", ".ps1", ".md", ".txt", ".json",
    ".yaml", ".yml", ".toml", ".ini", ".cfg", ".csv", ".html", ".css", ".sql", ""
}


def _resolve(cfg: Config, path: str) -> Path:
    """把用户给的路径解析到沙箱内的绝对路径，越界直接抛异常。"""
    root = Path(cfg.workspace)
    p = Path(path)
    full = p if p.is_absolute() else (root / p)
    full = full.resolve()
    if not full.is_relative_to(root.resolve()):
        raise PermissionError(f"拒绝访问沙箱外的路径: {path}")
    return full


class ToolRegistry:
    """工具注册中心：同时维护可调用函数与 OpenAI function-calling 的 JSON Schema。"""

    def __init__(self, cfg: Config):
        self.cfg = cfg
        self._tools: dict[str, Callable[..., str]] = {}
        self._schemas: list[dict[str, Any]] = []
        self._register_all()

    # ---------- 注册 ----------
    def _add(self, name: str, desc: str, params: dict, func: Callable[..., str]) -> None:
        self._tools[name] = func
        self._schemas.append({
            "type": "function",
            "function": {"name": name, "description": desc, "parameters": params},
        })

    def _register_all(self) -> None:
        cfg = self.cfg

        def read_file(path: str) -> str:
            """读取沙箱内文本文件内容（截断到 8000 字符）。"""
            full = _resolve(cfg, path)
            if not full.is_file():
                return f"错误: 文件不存在: {path}"
            if full.suffix.lower() not in TEXT_SUFFIXES:
                return f"错误: 不支持读取二进制文件: {path}"
            text = full.read_text(encoding="utf-8", errors="replace")
            return text[:8000] + ("\n...[已截断]" if len(text) > 8000 else "")

        def write_file(path: str, content: str) -> str:
            """将文本内容写入沙箱内文件（自动创建父目录）。"""
            full = _resolve(cfg, path)
            full.parent.mkdir(parents=True, exist_ok=True)
            full.write_text(content, encoding="utf-8")
            return f"已写入 {len(content)} 字符到 {path}"

        def list_files(path: str = ".") -> str:
            """列出目录树（最多 3 层、200 个条目），忽略常见噪音目录。"""
            full = _resolve(cfg, path)
            if not full.is_dir():
                return f"错误: 目录不存在: {path}"
            ignore = {"__pycache__", ".git", "node_modules", ".venv", "venv", ".idea", ".vscode"}
            lines: list[str] = []
            for dirpath, dirnames, filenames in os.walk(full):
                dirnames[:] = [d for d in dirnames if d not in ignore]
                depth = len(Path(dirpath).relative_to(full).parts)
                if depth > 3:
                    dirnames[:] = []
                    continue
                for name in sorted(dirnames + filenames):
                    lines.append(str(Path(dirpath).relative_to(full) / name))
                if len(lines) >= 200:
                    lines.append("...[结果过多已截断]")
                    break
            return "\n".join(lines) or "(空目录)"

        def search_code(pattern: str, path: str = ".") -> str:
            """在沙箱内按正则搜索代码内容，返回 文件:行号:匹配行。"""
            full = _resolve(cfg, path)
            if not full.exists():
                return f"错误: 路径不存在: {path}"
            try:
                rx = re.compile(pattern)
            except re.error as e:
                return f"错误: 无效正则: {e}"
            ignore = {"__pycache__", ".git", "node_modules", ".venv", "venv"}
            hits: list[str] = []
            for dirpath, dirnames, filenames in os.walk(full):
                dirnames[:] = [d for d in dirnames if d not in ignore]
                for fn in filenames:
                    f = Path(dirpath) / fn
                    if f.suffix.lower() not in TEXT_SUFFIXES:
                        continue
                    try:
                        for i, line in enumerate(f.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                            if rx.search(line):
                                rel = f.relative_to(cfg.workspace)
                                hits.append(f"{rel}:{i}:{line.strip()[:120]}")
                                if len(hits) >= 100:
                                    hits.append("...[结果过多已截断]")
                                    return "\n".join(hits)
                    except OSError:
                        continue
            return "\n".join(hits) or "(无匹配结果)"

        def run_python(code: str) -> str:
            """在沙箱目录下执行一段 Python 代码，返回 stdout/stderr（带超时保护）。"""
            full = _resolve(cfg, ".")
            try:
                r = subprocess.run(
                    [sys.executable, "-c", code],
                    capture_output=True, text=True,
                    timeout=cfg.tool_timeout, cwd=str(full),
                )
            except subprocess.TimeoutExpired:
                return f"错误: 代码执行超时(>{cfg.tool_timeout}s)，已终止"
            out = (r.stdout or "") + (("\n[stderr]\n" + r.stderr) if r.stderr else "")
            return (out or "(无输出)")[:6000]

        self._add("read_file", "读取沙箱内的文本文件内容", {
            "type": "object", "properties": {
                "path": {"type": "string", "description": "相对工作区的文件路径"}},
            "required": ["path"]}, read_file)
        self._add("write_file", "将文本内容写入沙箱内的文件", {
            "type": "object", "properties": {
                "path": {"type": "string", "description": "目标文件路径"},
                "content": {"type": "string", "description": "要写入的完整文本内容"}},
            "required": ["path", "content"]}, write_file)
        self._add("list_files", "列出目录结构，浏览项目文件", {
            "type": "object", "properties": {
                "path": {"type": "string", "description": "目录路径，默认当前目录"}},
            "required": []}, list_files)
        self._add("search_code", "按正则表达式搜索代码内容", {
            "type": "object", "properties": {
                "pattern": {"type": "string", "description": "正则表达式"},
                "path": {"type": "string", "description": "搜索范围目录，默认整个工作区"}},
            "required": ["pattern"]}, search_code)
        self._add("run_python", "执行一段 Python 代码并返回输出", {
            "type": "object", "properties": {
                "code": {"type": "string", "description": "要执行的 Python 代码"}},
            "required": ["code"]}, run_python)

    # ---------- 对外接口 ----------
    @property
    def schemas(self) -> list[dict[str, Any]]:
        return self._schemas

    @property
    def names(self) -> list[str]:
        return list(self._tools)

    def execute(self, name: str, arguments: dict[str, Any]) -> str:
        func = self._tools.get(name)
        if func is None:
            return f"错误: 未知工具 {name}"
        try:
            return str(func(**arguments))
        except TypeError as e:
            return f"错误: 工具参数不匹配: {e}"
        except Exception as e:  # 工具执行失败不中断 Agent，错误信息回传给 LLM 自行处理
            return f"工具执行出错: {type(e).__name__}: {e}"
