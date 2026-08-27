"""
交互式 CLI 聊天模式

启动方式：
    python -m agent_labs chat
    python -m agent_labs chat --model claude-sonnet-4-6

功能：
- 对话式交互，支持多轮对话
- 实时显示 Agent 工具调用和思考过程
- 会话管理（/history、/clear）
- 内置命令（/help、/tools、/skills、/stats）
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import time
from typing import Any

from ..core.types import AgentContext, AgentInput, Message, Role

logger = logging.getLogger(__name__)

# ============================================================================
# ANSI 终端颜色
# ============================================================================

_RESET = "\033[0m"
_BOLD = "\033[1m"
_DIM = "\033[2m"
_RED = "\033[31m"
_GREEN = "\033[32m"
_YELLOW = "\033[33m"
_BLUE = "\033[34m"
_MAGENTA = "\033[35m"
_CYAN = "\033[36m"
_WHITE = "\033[37m"


def _color(text: str, code: str) -> str:
    """包装 ANSI 颜色（非 TTY 时跳过）"""
    if not sys.stdout.isatty():
        return text
    return f"{code}{text}{_RESET}"


def _bold(text: str) -> str:
    return _color(text, _BOLD)


def _dim(text: str) -> str:
    return _color(text, _DIM)


def _red(text: str) -> str:
    return _color(text, _RED)


def _green(text: str) -> str:
    return _color(text, _GREEN)


def _yellow(text: str) -> str:
    return _color(text, _YELLOW)


def _blue(text: str) -> str:
    return _color(text, _BLUE)


def _magenta(text: str) -> str:
    return _color(text, _MAGENTA)


def _cyan(text: str) -> str:
    return _color(text, _CYAN)


# ============================================================================
# Spinner
# ============================================================================


class Spinner:
    """简单的终端旋转动画"""

    _frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

    def __init__(self, message: str = "Thinking"):
        self.message = message
        self._running = False
        self._task: asyncio.Task[Any] | None = None

    async def _spin(self) -> None:
        i = 0
        while self._running:
            frame = self._frames[i % len(self._frames)]
            sys.stderr.write(f"\r{_cyan(frame)} {self.message}... ")
            sys.stderr.flush()
            await asyncio.sleep(0.1)
            i += 1
        # 清除 spinner 行
        sys.stderr.write("\r" + " " * (len(self.message) + 10) + "\r")
        sys.stderr.flush()

    async def start(self, message: str = "Thinking") -> None:
        self.message = message
        self._running = True
        self._task = asyncio.create_task(self._spin())

    async def stop(self) -> None:
        self._running = False
        if self._task:
            await self._task
            self._task = None


# ============================================================================
# 服务初始化
# ============================================================================


def _init_all_services() -> None:
    """初始化所有全局服务（与 API lifespan 相同逻辑）"""
    from ..api.deps import (
        get_approval_manager,
        get_context_builder,
        get_context_compressor,
        get_email_notifier,
        get_knowledge_injector,
        get_memory_manager,
        get_model_manager,
        get_session_manager,
        get_skill_permission_manager,
        get_skill_registry,
        get_timeout_manager,
        get_token_monitor,
        get_tool_executor,
        get_tool_permission_manager,
        get_tool_registry,
        get_tracer,
    )

    # 触发所有单例初始化
    get_model_manager()
    get_session_manager()
    get_memory_manager()
    get_context_builder()
    get_context_compressor()
    get_knowledge_injector()
    get_tracer()
    get_token_monitor()
    get_approval_manager()
    get_email_notifier()
    get_timeout_manager()

    # 注册内置工具
    from ..tools.builtin import register_all_builtin_tools

    registry = get_tool_registry()
    if len(registry) == 0:
        register_all_builtin_tools(registry)

    perm_mgr = get_tool_permission_manager()
    executor = get_tool_executor()
    executor.set_permission_manager(perm_mgr)

    # 注册内置技能
    from ..skills.builtin import register_all_builtin_skills

    skill_registry = get_skill_registry()
    if len(skill_registry) == 0:
        register_all_builtin_skills(skill_registry)

    skill_perm = get_skill_permission_manager()
    for skill in skill_registry.get_all():
        skill_perm.register_skill(
            skill_name=skill.name,
            required_tools=skill.required_tools,
        )


def _create_agent():
    """创建完整的 ReactAgent 实例"""
    from ..api.deps import get_react_agent

    return get_react_agent()


# ============================================================================
# 聊天引擎
# ============================================================================


class ChatEngine:
    """交互式聊天引擎"""

    def __init__(self, model_id: str | None = None):
        self.model_id = model_id
        self.session_id: str | None = None
        self.history: list[tuple[str, str]] = []  # (role, content)
        self.agent = _create_agent()

    async def start(self) -> None:
        """启动聊天会话"""
        from ..api.deps import get_session_manager

        session_mgr = get_session_manager()
        self.session_id = await session_mgr.create(agent_id=self.agent.agent_id)

        logger.info(f"Chat session created: {self.session_id}")

    async def send_message(self, query: str) -> dict[str, Any]:
        """发送消息并获取 Agent 响应"""
        from ..api.deps import get_memory_manager, get_session_manager

        session_mgr = get_session_manager()
        memory_mgr = get_memory_manager()

        # 记录用户消息
        user_message = Message(role=Role.USER, content=query)
        await session_mgr.add_message(self.session_id, user_message)

        # 获取上下文
        messages = await session_mgr.get_history(self.session_id, limit=30)
        memories = await memory_mgr.search(query, top_k=3)

        agent_input = AgentInput(
            query=query,
            session_id=self.session_id,
        )
        context = AgentContext(
            session_id=self.session_id,
            messages=messages,
            memories=memories,
        )

        # 如果指定了模型，设置到 metadata
        if self.model_id:
            context.metadata["model_id"] = self.model_id

        # 执行 Agent
        output = await self.agent.invoke(agent_input, context)

        # 记录助手消息
        assistant_message = Message(role=Role.ASSISTANT, content=output.answer)
        await session_mgr.add_message(self.session_id, assistant_message)

        # 写入情景记忆
        await memory_mgr.summarize_episode(
            self.session_id, messages + [assistant_message], importance=0.6
        )

        return {
            "answer": output.answer,
            "tool_calls": output.tool_calls_made,
            "iterations": output.iterations,
            "tokens_used": output.tokens_used,
            "duration_ms": output.duration_ms,
        }

    async def get_stats(self) -> dict[str, Any]:
        """获取当前会话统计"""
        from ..api.deps import get_session_manager, get_token_monitor, get_tracer

        session_mgr = get_session_manager()
        token_monitor = get_token_monitor()
        tracer = get_tracer()

        session_stats = {}
        if self.session_id:
            state = await session_mgr.get_state(self.session_id)
            if state:
                session_stats = {
                    "iterations": state.iterations,
                    "tool_calls": state.tool_calls_count,
                    "tokens": state.tokens_used,
                    "status": state.status.value,
                }

        global_tokens = token_monitor.get_global_stats()
        recent_traces = tracer.get_recent_traces(n=100)

        return {
            "session": session_stats,
            "global_tokens": global_tokens,
            "traces_count": len(recent_traces),
        }


# ============================================================================
# 命令处理器
# ============================================================================


def _format_tool_calls(tool_calls: list[dict[str, Any]]) -> str:
    """格式化工具调用信息"""
    if not tool_calls:
        return ""
    lines = []
    for tc in tool_calls:
        status_icon = _green("✓") if tc.get("success") else _red("✗")
        duration = tc.get("duration_ms", 0)
        lines.append(f"  {status_icon} {_cyan(tc['name'])} {_dim(f'({duration:.0f}ms)')}")
    return "\n".join(lines)


async def _run_chat_loop(engine: ChatEngine) -> None:
    """主聊天循环"""

    # 显示欢迎信息
    _print_welcome(engine)

    spinner = Spinner()

    while True:
        try:
            # 读取用户输入
            user_input = await asyncio.to_thread(input, f"\n{_bold(_blue('You'))} > ")
        except (EOFError, KeyboardInterrupt):
            print()
            break

        user_input = user_input.strip()

        if not user_input:
            continue

        # 处理内置命令
        if user_input.startswith("/"):
            should_exit = await _handle_command(user_input, engine)
            if should_exit:
                break
            continue

        # 发送给 Agent
        try:
            await spinner.start("Thinking")
            start = time.monotonic()
            result = await engine.send_message(user_input)
            elapsed = time.monotonic() - start
            await spinner.stop()

            # 显示工具调用
            tool_info = _format_tool_calls(result["tool_calls"])
            if tool_info:
                print(f"\n{_dim('── 工具调用 ──')}")
                print(tool_info)

            # 显示回答
            print(f"\n{_bold(_green('Agent'))} {_dim(f'({elapsed:.1f}s)')}")
            print(result["answer"])

            # 显示统计
            stats_parts = []
            if result["iterations"]:
                stats_parts.append(f"{result['iterations']} iterations")
            if result["tokens_used"]:
                stats_parts.append(f"{result['tokens_used']} tokens")
            if stats_parts:
                print(f"\n{_dim(' • '.join(stats_parts))}")

        except Exception as e:
            await spinner.stop()
            print(f"\n{_red('✗ Error:')} {e}")
            logger.exception("Chat error")


async def _handle_command(cmd: str, engine: ChatEngine) -> bool:
    """
    处理内置命令

    Returns:
        True 表示应退出聊天
    """
    parts = cmd.split()
    command = parts[0].lower()

    if command in ("/exit", "/quit", "/q"):
        print(_dim("\nGoodbye! 👋"))
        return True

    elif command == "/help":
        _print_help()

    elif command == "/clear":
        engine.history.clear()
        print(_green("✓ Chat history cleared."))

    elif command == "/tools":
        await _cmd_list_tools()

    elif command == "/skills":
        await _cmd_list_skills()

    elif command == "/history":
        await _cmd_show_history(engine)

    elif command == "/stats":
        await _cmd_show_stats(engine)

    elif command == "/model":
        await _cmd_show_models(engine, parts)

    else:
        print(f"{_yellow('Unknown command:')} {command}")
        print(_dim("Type /help for available commands."))

    return False


def _print_welcome(engine: ChatEngine) -> None:
    """打印欢迎横幅"""
    print()
    print(_bold(_cyan("╔══════════════════════════════════════════╗")))
    print(_bold(_cyan("║")) + _bold("     🤖 Agent-Labs CLI Chat Mode        ") + _bold(_cyan("║")))
    print(_bold(_cyan("╚══════════════════════════════════════════╝")))
    print()
    print(f"  Session:  {_dim(engine.session_id)}")
    print(f"  Agent:    {_cyan('ReAct')} (思考→行动→观察 循环)")
    if engine.model_id:
        print(f"  Model:    {_yellow(engine.model_id)}")
    print()
    _check_api_keys()
    print(_dim("  Type /help for available commands."))
    print()


def _print_help() -> None:
    """打印帮助信息"""
    print(f"""
{_bold("可用命令:")}
  {_cyan("/help")}      Show this help message
  {_cyan("/exit")}      Exit chat mode (aliases: /quit, /q)
  {_cyan("/clear")}     Clear chat history (start new session)
  {_cyan("/tools")}     List available tools
  {_cyan("/skills")}    List available skills
  {_cyan("/history")}   Show conversation history
  {_cyan("/stats")}     Show session & token statistics
  {_cyan("/model")}     Show or change the model
            /model              → show current model
            /model list         → list available models
            /model <model-id>   → switch model

{_bold("快捷键:")}
  Ctrl+C       Interrupt current generation
  Ctrl+D       Exit chat mode
""")


def _check_api_keys() -> None:
    """检查 API Key 配置情况"""
    keys_status: list[tuple[str, bool]] = []
    if os.getenv("ANTHROPIC_API_KEY"):
        keys_status.append(("Anthropic", True))
    else:
        keys_status.append(("Anthropic", False))

    if os.getenv("OPENAI_API_KEY"):
        keys_status.append(("OpenAI", True))
    else:
        keys_status.append(("OpenAI", False))

    configured = [name for name, ok in keys_status if ok]
    if not configured:
        print(
            _yellow("  ⚠ No API keys configured!")
            + f"\n  {_dim('Set ANTHROPIC_API_KEY or OPENAI_API_KEY in .env file.')}"
            + f"\n  {_dim('The agent will not be able to respond without an LLM.')}"
        )
    else:
        print(_dim(f"  API Keys: {', '.join(configured)} configured"))
    print()


async def _cmd_list_tools() -> None:
    """列出可用工具"""
    from ..api.deps import get_tool_permission_manager, get_tool_registry

    registry = get_tool_registry()
    perm_mgr = get_tool_permission_manager()

    tools = registry.get_all()
    if not tools:
        print(_yellow("No tools registered."))
        return

    print(f"\n{_bold('Available Tools')} ({len(tools)}):")
    for tool in tools:
        perm_config = perm_mgr.get(tool.name)
        perm_level = perm_config.permission_level if perm_config else "read"
        perm_icon = {"read": "👁", "write": "✏️", "execute": "⚡"}.get(perm_level, "❓")
        desc = tool.description[:80] if tool.description else ""
        print(f"  {perm_icon} {_cyan(tool.name):<22s} {_dim(desc)}")
    print()


async def _cmd_list_skills() -> None:
    """列出可用技能"""
    from ..api.deps import get_skill_registry

    registry = get_skill_registry()
    skills = registry.get_all()
    if not skills:
        print(_yellow("No skills registered."))
        return

    print(f"\n{_bold('Available Skills')} ({len(skills)}):")
    for skill in skills:
        triggers = ", ".join(skill.triggers[:3]) if skill.triggers else "none"
        desc = skill.description[:80] if skill.description else ""
        print(f"  🔧 {_cyan(skill.name):<22s} triggers=[{triggers}]")
        if desc:
            print(f"     {_dim(desc)}")
    print()


async def _cmd_show_history(engine: ChatEngine) -> None:
    """显示对话历史"""
    from ..api.deps import get_session_manager

    if not engine.session_id:
        print(_yellow("No active session."))
        return

    messages = await get_session_manager().get_history(engine.session_id, limit=50)
    if not messages:
        print(_dim("No message history."))
        return

    print(f"\n{_bold('Conversation History')} ({len(messages)} messages):")
    for i, msg in enumerate(messages):
        role_icon = {"user": "👤", "assistant": "🤖", "tool": "🔧", "system": "⚙️"}.get(
            msg.role.value, "❓"
        )
        preview = msg.content[:100].replace("\n", " ")
        suffix = "..." if len(msg.content) > 100 else ""
        print(f"  {_dim(f'[{i + 1}]')} {role_icon} {preview}{suffix}")
    print()


async def _cmd_show_stats(engine: ChatEngine) -> None:
    """显示统计信息"""
    stats = await engine.get_stats()

    print(f"\n{_bold('📊 Statistics')}")
    session = stats.get("session", {})
    if session:
        print(f"  Session:     {_dim(session.get('status', 'unknown'))}")
        print(f"  Iterations:  {session.get('iterations', 0)}")
        print(f"  Tool calls:  {session.get('tool_calls', 0)}")
        print(f"  Tokens:      {session.get('tokens', 0)}")

    global_tokens = stats.get("global_tokens", {})
    if global_tokens:
        total = global_tokens.get("total_input", 0) + global_tokens.get("total_output", 0)
        print(f"  Total tokens (all sessions): {total}")
    print(f"  Traces:      {stats.get('traces_count', 0)}")
    print()


async def _cmd_show_models(engine: ChatEngine, parts: list[str]) -> None:
    """显示或切换模型"""
    from ..api.deps import get_model_manager

    model_mgr = get_model_manager()

    if len(parts) == 1:
        # /model — 显示当前模型
        if engine.model_id:
            print(f"  Current model: {_yellow(engine.model_id)}")
        else:
            print(f"  Current model: {_dim('auto (orchestrator: strong, worker: weak)')}")
        print(f"  {_dim('Use /model list to see available models.')}")
        print(f"  {_dim('Use /model <model-id> to switch.')}")
        return

    sub = parts[1].lower()

    if sub == "list":
        models = model_mgr.list_available_models()
        if not models:
            print(_yellow("No models configured."))
            return
        print(f"\n{_bold('Available Models')}:")
        for m in models:
            tier_icon = "⭐" if m.get("tier") == "strong" else "💡"
            cost_in = m.get("cost_per_1k_input", 0)
            cost_out = m.get("cost_per_1k_output", 0)
            print(
                f"  {tier_icon} {_cyan(m['id']):<24s} "
                f"{_dim(m['provider'])}  "
                f"${cost_in:.4f}/${cost_out:.4f} per 1k"
            )
        print()
        return

    # /model <model-id> — 切换模型
    try:
        provider_name, resolved = model_mgr._resolve_model(model_id=sub)
        engine.model_id = resolved
        print(f"  {_green('✓')} Switched to {_yellow(resolved)} ({provider_name})")
    except ValueError:
        print(f"  {_red('✗')} Unknown model: {sub}")
        print(f"  {_dim('Use /model list to see available models.')}")


# ============================================================================
# 公开入口
# ============================================================================


async def run_chat(
    model_id: str | None = None,
    log_level: str = "WARNING",
) -> None:
    """
    启动交互式聊天模式

    Args:
        model_id: 指定模型 ID，不指定则自动选择
        log_level: 日志级别（聊天模式下默认较高以避免干扰）
    """
    # 设置日志（聊天模式下减少噪音）
    logging.basicConfig(
        level=getattr(logging, log_level.upper(), logging.WARNING),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    # 抑制第三方库日志
    for lib in ("httpx", "httpcore", "urllib3", "asyncio", "langgraph"):
        logging.getLogger(lib).setLevel(logging.WARNING)

    print(_dim("Initializing services..."), end="\r")

    try:
        _init_all_services()
    except Exception as e:
        print(f"\n{_red('✗ Failed to initialize services:')} {e}")
        logger.exception("Service initialization failed")
        sys.exit(1)

    engine = ChatEngine(model_id=model_id)

    try:
        await engine.start()
        await _run_chat_loop(engine)
    except KeyboardInterrupt:
        print(f"\n{_dim('Interrupted. Goodbye! 👋')}")
    except Exception as e:
        print(f"\n{_red('Fatal error:')} {e}")
        logger.exception("Chat fatal error")
    finally:
        await engine.agent.cleanup()
