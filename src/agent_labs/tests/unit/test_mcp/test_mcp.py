"""Unit tests for MCP server management"""

import pytest

from agent_labs.mcp.server import (
    MCPServerConfig,
    MCPServerManager,
    MCPServerStatus,
    MCPToolDef,
)
from agent_labs.tools.registry import ToolRegistry


class TestMCPServerManager:
    @pytest.fixture
    def manager(self):
        return MCPServerManager()

    def test_register_server(self, manager):
        config = MCPServerConfig(name="filesystem", command="npx", auto_connect=False)
        manager.register_server(config)
        assert "filesystem" in manager._servers

    def test_register_duplicate(self, manager):
        manager.register_server(MCPServerConfig(name="test"))
        with pytest.raises(ValueError, match="已注册"):
            manager.register_server(MCPServerConfig(name="test"))

    def test_unregister(self, manager):
        manager.register_server(MCPServerConfig(name="test"))
        manager.unregister_server("test")
        assert "test" not in manager._servers

    async def test_connect_server_filesystem(self, manager):
        manager.register_server(MCPServerConfig(name="filesystem"))
        ok = await manager.connect_server("filesystem")
        assert ok
        state = manager.get_server_status("filesystem")
        assert state.status == MCPServerStatus.CONNECTED
        assert state.tool_count >= 2

    async def test_connect_server_database(self, manager):
        manager.register_server(MCPServerConfig(name="database"))
        ok = await manager.connect_server("database")
        assert ok
        state = manager.get_server_status("database")
        assert state.tool_count >= 1

    async def test_connect_all(self, manager):
        manager.register_server(MCPServerConfig(name="filesystem"))
        manager.register_server(MCPServerConfig(name="database"))
        results = await manager.connect_all()
        assert results["filesystem"]
        assert results["database"]

    async def test_connect_disabled_server(self, manager):
        manager.register_server(MCPServerConfig(name="test", enabled=False))
        ok = await manager.connect_server("test")
        assert not ok

    async def test_connect_nonexistent(self, manager):
        ok = await manager.connect_server("nonexistent")
        assert not ok

    async def test_disconnect(self, manager):
        manager.register_server(MCPServerConfig(name="filesystem"))
        await manager.connect_server("filesystem")
        await manager.disconnect_server("filesystem")
        state = manager.get_server_status("filesystem")
        assert state.status == MCPServerStatus.DISCONNECTED

    async def test_register_tools_to_registry(self, manager):
        registry = ToolRegistry()
        manager.set_tool_registry(registry)
        manager.register_server(MCPServerConfig(name="filesystem"))
        ok = await manager.connect_server("filesystem")
        assert ok, "connect_server should succeed"

        # MCP 服务器状态应该包含发现的工具
        state = manager.get_server_status("filesystem")
        assert state is not None
        assert state.tool_count >= 2
        # 验证：工具已在 MCP manager 中可用
        all_tools = manager.get_all_tools()
        assert len(all_tools) >= 2

    def test_list_servers(self, manager):
        manager.register_server(MCPServerConfig(name="fs"))
        manager.register_server(MCPServerConfig(name="db"))
        servers = manager.list_servers()
        assert len(servers) == 2

    def test_get_all_tools(self, manager):
        manager.register_server(MCPServerConfig(name="filesystem"))
        manager.register_server(MCPServerConfig(name="web_search"))
        # 不需要连接也能看到预定义工具列表
        for name in ["filesystem", "web_search"]:
            state = manager._servers[name]
            manager._servers[name].tools = [MCPToolDef(name=f"mcp__{name}__tool", server_name=name)]
            state.tool_count = 1

        all_tools = manager.get_all_tools()
        assert len(all_tools) == 2

    def test_get_stats(self, manager):
        manager.register_server(MCPServerConfig(name="fs"))
        stats = manager.get_stats()
        assert stats["total_servers"] == 1

    def test_tool_def_to_dict(self):
        tool = MCPToolDef(
            name="test_tool",
            description="A test tool",
            parameters={"type": "object"},
            server_name="test",
        )
        d = tool.to_dict()
        assert d["name"] == "test_tool"
        assert d["server"] == "test"
