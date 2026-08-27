"""
内置工具集

提供开箱即用的基础工具：
- read_file — 读取文件内容
- write_file — 写入文件（需审批）
- web_search — 网络搜索
- execute_command — 执行系统命令（需沙箱）

使用方式：
    from agent_labs.tools.builtin import register_all_builtin_tools
    register_all_builtin_tools(registry)
"""

from __future__ import annotations

from .execute_command import ExecuteCommandTool
from .read_file import ReadFileTool
from .web_search import WebSearchTool
from .write_file import WriteFileTool

__all__ = [
    "ReadFileTool",
    "WriteFileTool",
    "WebSearchTool",
    "ExecuteCommandTool",
    "register_all_builtin_tools",
]


def register_all_builtin_tools(registry) -> None:
    """向注册表注册所有内置工具"""
    from .execute_command import ExecuteCommandTool
    from .read_file import ReadFileTool
    from .web_search import WebSearchTool
    from .write_file import WriteFileTool

    registry.register(ReadFileTool())
    registry.register(WriteFileTool())
    registry.register(WebSearchTool())
    registry.register(ExecuteCommandTool())
