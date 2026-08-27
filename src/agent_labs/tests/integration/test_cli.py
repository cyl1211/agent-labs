"""CLI 聊天模式测试"""

import pytest


@pytest.fixture
def engine():
    """创建 ChatEngine 实例（测试环境，不连接 LLM）"""
    # 初始化服务（测试环境中 lru_cache 共享）
    from agent_labs.cli.chat import ChatEngine, _init_all_services

    _init_all_services()
    return ChatEngine(model_id="claude-sonnet-4-6")


class TestChatEngine:
    """测试 ChatEngine 核心功能"""

    async def test_engine_creation(self, engine):
        """引擎创建后应有正确的初始状态"""
        assert engine.model_id == "claude-sonnet-4-6"
        assert engine.session_id is None
        assert engine.history == []
        assert engine.agent is not None

    async def test_engine_start_creates_session(self, engine):
        """start() 应创建新会话"""
        await engine.start()
        assert engine.session_id is not None
        assert len(engine.session_id) > 0

    async def test_get_stats_no_session(self, engine):
        """无会话时获取统计不应崩溃"""
        stats = await engine.get_stats()
        assert "session" in stats
        assert "global_tokens" in stats
        assert "traces_count" in stats

    async def test_get_stats_with_session(self, engine):
        """有会话时获取统计应包含会话信息"""
        await engine.start()
        stats = await engine.get_stats()
        assert stats["session"] is not None


class TestServiceInitialization:
    """测试服务初始化"""

    def test_init_all_services(self):
        """服务初始化不应抛出异常"""
        from agent_labs.cli.chat import _init_all_services

        _init_all_services()  # 不应抛出异常

    def test_init_all_services_idempotent(self):
        """重复初始化不应出错"""
        from agent_labs.cli.chat import _init_all_services

        _init_all_services()
        _init_all_services()  # 第二次调用也不应出错

    def test_init_registers_tools(self):
        """初始化后应注册内置工具"""
        from agent_labs.api.deps import get_tool_registry
        from agent_labs.cli.chat import _init_all_services

        _init_all_services()
        registry = get_tool_registry()
        assert len(registry) >= 4

    def test_init_registers_skills(self):
        """初始化后应注册内置技能"""
        from agent_labs.api.deps import get_skill_registry
        from agent_labs.cli.chat import _init_all_services

        _init_all_services()
        registry = get_skill_registry()
        assert len(registry) >= 1

    def test_create_agent_has_all_services(self):
        """创建的 Agent 应有所有注入的服务"""
        from agent_labs.cli.chat import _create_agent, _init_all_services

        _init_all_services()
        agent = _create_agent()
        assert agent.tracer is not None
        assert agent.token_monitor is not None
        assert agent.context_builder is not None
        assert agent.context_compressor is not None
        assert agent.knowledge_injector is not None
        assert agent.approval_manager is not None
        assert agent.timeout_manager is not None
        assert agent.skill_executor is not None


class TestAnsiColors:
    """测试 ANSI 颜色工具函数"""

    def test_color_non_tty_returns_plain_text(self, monkeypatch):
        """非 TTY 环境下应返回纯文本"""
        import sys

        monkeypatch.setattr(sys.stdout, "isatty", lambda: False)
        from agent_labs.cli.chat import _bold, _dim, _green, _red

        assert _bold("hello") == "hello"
        assert _red("error") == "error"
        assert _green("ok") == "ok"
        assert _dim("dim") == "dim"

    def test_color_tty_adds_ansi(self, monkeypatch):
        """TTY 环境下应添加 ANSI 转义码"""
        import sys

        monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
        from agent_labs.cli.chat import _bold, _cyan, _yellow

        assert "\033[" in _bold("hello")
        assert "\033[" in _cyan("info")
        assert "\033[" in _yellow("warn")


class TestFormatToolCalls:
    """测试工具调用格式化"""

    def test_empty_tool_calls(self):
        from agent_labs.cli.chat import _format_tool_calls

        assert _format_tool_calls([]) == ""

    def test_successful_tool_call(self):
        from agent_labs.cli.chat import _format_tool_calls

        result = _format_tool_calls(
            [
                {"name": "read_file", "success": True, "duration_ms": 35.2},
            ]
        )
        assert "read_file" in result
        assert "35" in result  # duration

    def test_failed_tool_call(self):
        from agent_labs.cli.chat import _format_tool_calls

        result = _format_tool_calls(
            [
                {"name": "write_file", "success": False, "duration_ms": 10.0},
            ]
        )
        assert "write_file" in result

    def test_multiple_tool_calls(self):
        from agent_labs.cli.chat import _format_tool_calls

        result = _format_tool_calls(
            [
                {"name": "read_file", "success": True, "duration_ms": 10.0},
                {"name": "web_search", "success": True, "duration_ms": 500.0},
            ]
        )
        assert "read_file" in result
        assert "web_search" in result


class TestSpinner:
    """测试 Spinner 动画"""

    async def test_spinner_start_stop(self):
        from agent_labs.cli.chat import Spinner

        spinner = Spinner()
        await spinner.start("Testing")
        assert spinner._running is True
        assert spinner._task is not None
        await spinner.stop()
        assert spinner._running is False


class TestCheckApiKeys:
    """测试 API Key 检查"""

    def test_no_keys_configured(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        from agent_labs.cli.chat import _check_api_keys

        _check_api_keys()  # 不应崩溃，应打印警告

    def test_anthropic_key_configured(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        from agent_labs.cli.chat import _check_api_keys

        _check_api_keys()  # 不应崩溃


class TestCommandParsing:
    """测试命令解析"""

    async def test_exit_commands(self, engine):
        """退出命令应返回 True"""
        from agent_labs.cli.chat import _handle_command

        for cmd in ["/exit", "/quit", "/q"]:
            result = await _handle_command(cmd, engine)
            assert result is True, f"{cmd} should return True"

    async def test_help_command(self, engine):
        """帮助命令应返回 False（不退出）"""
        from agent_labs.cli.chat import _handle_command

        result = await _handle_command("/help", engine)
        assert result is False

    async def test_unknown_command(self, engine):
        """未知命令应返回 False 并提示"""
        from agent_labs.cli.chat import _handle_command

        result = await _handle_command("/foobar", engine)
        assert result is False

    async def test_tools_command(self, engine):
        """tools 命令列出工具"""
        from agent_labs.cli.chat import _handle_command

        result = await _handle_command("/tools", engine)
        assert result is False

    async def test_skills_command(self, engine):
        """skills 命令列出技能"""
        from agent_labs.cli.chat import _handle_command

        result = await _handle_command("/skills", engine)
        assert result is False

    async def test_stats_command(self, engine):
        """stats 命令显示统计"""
        await engine.start()
        from agent_labs.cli.chat import _handle_command

        result = await _handle_command("/stats", engine)
        assert result is False

    async def test_model_command_show(self, engine):
        """model 命令显示当前模型"""
        from agent_labs.cli.chat import _handle_command

        result = await _handle_command("/model", engine)
        assert result is False

    async def test_model_command_list(self, engine):
        """model list 命令列出可用模型"""
        from agent_labs.cli.chat import _handle_command

        result = await _handle_command("/model list", engine)
        assert result is False

    async def test_model_command_switch(self, engine):
        """model <id> 命令切换模型"""
        from agent_labs.cli.chat import _handle_command

        result = await _handle_command("/model claude-haiku-4-5", engine)
        assert result is False
        assert engine.model_id == "claude-haiku-4-5"

    async def test_model_command_invalid(self, engine):
        """model 无效模型 ID"""
        from agent_labs.cli.chat import _handle_command

        result = await _handle_command("/model nonexistent-model", engine)
        assert result is False
