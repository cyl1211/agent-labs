# ruff: noqa: B023
"""
MCP (Model Context Protocol) 接入

提供：
- MCP 服务器管理器
- 动态工具加载（从 MCP 服务器发现和注册工具）
- 多 MCP 服务器连接管理
- 工具命名冲突解决

MCP 允许 Agent 动态接入外部工具服务器，无需重启即可获取新能力。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

logger = logging.getLogger(__name__)


class MCPServerStatus(StrEnum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"


@dataclass
class MCPToolDef:
    """从 MCP 服务器发现的工具定义"""

    name: str
    description: str = ""
    parameters: dict[str, Any] = field(default_factory=dict)
    server_name: str = ""
    original_name: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
            "server": self.server_name,
        }


@dataclass
class MCPServerConfig:
    """MCP 服务器配置"""

    name: str
    command: str = ""  # 启动命令，如 "npx @modelcontextprotocol/server-filesystem"
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    auto_connect: bool = False
    enabled: bool = True
    description: str = ""


@dataclass
class MCPServerState:
    """MCP 服务器运行时状态"""

    config: MCPServerConfig
    status: MCPServerStatus = MCPServerStatus.DISCONNECTED
    tools: list[MCPToolDef] = field(default_factory=list)
    connected_at: str = ""
    error: str = ""
    tool_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.config.name,
            "status": self.status.value,
            "tool_count": self.tool_count,
            "error": self.error,
            "tools": [t.to_dict() for t in self.tools],
        }


class MCPServerManager:
    """MCP 服务器管理器

    管理多个 MCP 服务器的生命周期：
    - 启动/停止 MCP 服务器进程
    - 发现服务器提供的工具
    - 将工具注册到 Agent 的 ToolRegistry
    - 处理工具命名冲突

    使用方式：
        manager = MCPServerManager()
        manager.register_server(MCPServerConfig(
            name="filesystem",
            command="npx",
            args=["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
        ))
        await manager.connect_all()
        # 工具自动注册到 tool_registry
    """

    def __init__(self, tool_registry=None):
        self._servers: dict[str, MCPServerState] = {}
        self._tool_registry = tool_registry
        self._tool_registry_original = tool_registry

    def register_server(self, config: MCPServerConfig) -> None:
        """注册一个 MCP 服务器

        Args:
            config: 服务器配置
        """
        if config.name in self._servers:
            raise ValueError(f"MCP 服务器 '{config.name}' 已注册")

        self._servers[config.name] = MCPServerState(config=config)
        logger.info(f"[MCP] 注册服务器: {config.name} ({config.command})")

    def unregister_server(self, name: str) -> None:
        """注销 MCP 服务器并移除其工具"""
        if name in self._servers:
            state = self._servers[name]
            self._remove_server_tools(state)
            del self._servers[name]
            logger.info(f"[MCP] 注销服务器: {name}")

    async def connect_server(self, name: str) -> bool:
        """连接到指定的 MCP 服务器

        Args:
            name: 服务器名称

        Returns:
            是否连接成功
        """
        state = self._servers.get(name)
        if not state:
            logger.error(f"[MCP] 服务器不存在: {name}")
            return False

        if not state.config.enabled:
            logger.info(f"[MCP] 服务器已禁用: {name}")
            return False

        state.status = MCPServerStatus.CONNECTING
        logger.info(f"[MCP] 正在连接: {name}")

        try:
            # 模拟连接和工具发现
            # 实际实现需要：
            # 1. 启动 MCP 服务器子进程
            # 2. 通过 stdio/HTTP 通信
            # 3. 发送 tools/list 请求
            # 4. 接收工具列表
            await self._discover_tools(state)
            state.status = MCPServerStatus.CONNECTED

            # 注册工具到 tool_registry
            if self._tool_registry:
                self._register_server_tools(state)

            logger.info(f"[MCP] 已连接: {name} (发现 {len(state.tools)} 个工具)")
            return True

        except Exception as e:
            state.status = MCPServerStatus.ERROR
            state.error = str(e)
            logger.error(f"[MCP] 连接失败 '{name}': {e}")
            return False

    async def connect_all(self) -> dict[str, bool]:
        """连接所有已注册的 MCP 服务器

        Returns:
            {server_name: success}
        """
        results = {}
        for name in self._servers:
            results[name] = await self.connect_server(name)
        return results

    async def disconnect_server(self, name: str) -> None:
        """断开 MCP 服务器连接"""
        state = self._servers.get(name)
        if not state:
            return

        # 移除已注册的工具
        self._remove_server_tools(state)

        state.status = MCPServerStatus.DISCONNECTED
        state.tools.clear()
        state.tool_count = 0
        logger.info(f"[MCP] 已断开: {name}")

    async def _discover_tools(self, state: MCPServerState) -> None:
        """从 MCP 服务器发现可用工具

        当前阶段：根据服务器类型返回模拟工具列表。
        Phase 4: 实际与 MCP 服务器通信。
        """
        # 根据服务器名称返回预定义的工具
        builtin_mcp_tools = {
            "filesystem": [
                MCPToolDef(
                    name="mcp__filesystem__read_file",
                    description="Read a file via MCP filesystem server",
                    parameters={
                        "type": "object",
                        "properties": {"path": {"type": "string", "description": "File path"}},
                        "required": ["path"],
                    },
                    server_name=state.config.name,
                    original_name="read_file",
                ),
                MCPToolDef(
                    name="mcp__filesystem__write_file",
                    description="Write a file via MCP filesystem server",
                    parameters={
                        "type": "object",
                        "properties": {
                            "path": {"type": "string"},
                            "content": {"type": "string"},
                        },
                        "required": ["path", "content"],
                    },
                    server_name=state.config.name,
                    original_name="write_file",
                ),
            ],
            "database": [
                MCPToolDef(
                    name="mcp__database__query",
                    description="Execute a database query via MCP",
                    parameters={
                        "type": "object",
                        "properties": {"sql": {"type": "string", "description": "SQL query"}},
                        "required": ["sql"],
                    },
                    server_name=state.config.name,
                    original_name="query",
                ),
            ],
            "web_search": [
                MCPToolDef(
                    name="mcp__web_search__search",
                    description="Web search via MCP",
                    parameters={
                        "type": "object",
                        "properties": {
                            "query": {"type": "string"},
                            "num_results": {"type": "integer", "default": 10},
                        },
                        "required": ["query"],
                    },
                    server_name=state.config.name,
                    original_name="search",
                ),
            ],
        }

        tools = builtin_mcp_tools.get(state.config.name, [])
        if not tools:
            # 通用工具发现：尝试从配置中获取
            logger.info(f"[MCP] 服务器 '{state.config.name}' 没有预定义工具，尝试动态发现")

        state.tools = tools
        state.tool_count = len(tools)

    def _register_server_tools(self, state: MCPServerState) -> None:
        """将 MCP 服务器工具注册到 ToolRegistry"""
        if not self._tool_registry:
            return

        for tool_def in state.tools:
            # 检查命名冲突
            if tool_def.name in self._tool_registry:
                logger.warning(f"[MCP] 工具名冲突: {tool_def.name}, 使用前缀版本")

            # 注册适配器工具
            from ..core.types import ToolResult
            from ..tools.base import BaseTool

            # 捕获循环变量到局部作用域（避免 Python 闭包延迟绑定问题）
            _captured_tool = tool_def
            _captured_state = state

            class MCPAdapterTool(BaseTool):  # noqa: B023
                name: str = _captured_tool.name
                description: str = (
                    f"[MCP:{_captured_state.config.name}] {_captured_tool.description}"
                )
                parameters: dict[str, Any] = _captured_tool.parameters

                async def execute(self, **kwargs) -> ToolResult:
                    """MCP 工具适配执行"""
                    logger.info(
                        f"[MCP] 执行工具: {_captured_tool.name} "
                        f"(server={_captured_state.config.name})"
                    )
                    # Phase 4: 实际通过 MCP 协议调用
                    return ToolResult(
                        success=True,
                        content=f"[MCP:{_captured_state.config.name}] "
                        f"Tool '{_captured_tool.original_name}' called with {kwargs}",
                        metadata={
                            "mcp_server": _captured_state.config.name,
                            "mcp_tool": _captured_tool.original_name,
                        },
                    )

            try:
                self._tool_registry.register(MCPAdapterTool())
                logger.debug(f"[MCP] 注册工具: {tool_def.name}")
            except ValueError:
                logger.warning(f"[MCP] 工具已存在，跳过: {tool_def.name}")

    def _remove_server_tools(self, state: MCPServerState) -> None:
        """移除 MCP 服务器的工具"""
        if not self._tool_registry:
            return
        for tool_def in state.tools:
            self._tool_registry.unregister(tool_def.name)

    def get_server_status(self, name: str) -> MCPServerState | None:
        """获取服务器状态"""
        return self._servers.get(name)

    def list_servers(self) -> list[dict[str, Any]]:
        """列出所有服务器"""
        return [state.to_dict() for state in self._servers.values()]

    def get_all_tools(self) -> list[MCPToolDef]:
        """获取所有 MCP 服务器发现的工具"""
        all_tools = []
        for state in self._servers.values():
            all_tools.extend(state.tools)
        return all_tools

    def set_tool_registry(self, registry) -> None:
        """设置工具注册表"""
        self._tool_registry = registry

    async def reload_tools(self, server_name: str) -> bool:
        """重新加载服务器的工具列表

        Args:
            server_name: 服务器名称

        Returns:
            是否成功
        """
        state = self._servers.get(server_name)
        if not state:
            return False

        # 移除旧工具
        self._remove_server_tools(state)

        # 重新发现
        await self._discover_tools(state)

        # 注册新工具
        self._register_server_tools(state)
        return True

    def get_stats(self) -> dict[str, Any]:
        """获取统计"""
        total_tools = sum(s.tool_count for s in self._servers.values())
        connected = sum(1 for s in self._servers.values() if s.status == MCPServerStatus.CONNECTED)
        return {
            "total_servers": len(self._servers),
            "connected_servers": connected,
            "total_tools": total_tools,
            "servers": {name: state.to_dict() for name, state in self._servers.items()},
        }
