"""
Agent-Labs 入口文件

启动方式：
    python -m agent_labs              # 启动 API 服务
    python -m agent_labs chat         # 启动 CLI 交互聊天
    python -m agent_labs chat --model claude-sonnet-4-6
    agent-labs  (安装后)

跨平台注意事项：
- Windows: 强制 SelectorEventLoop，兼容 uvicorn + asyncio 子进程
- Linux:   使用默认 SelectorEventLoop
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys


def setup_platform() -> None:
    """平台适配设置"""
    if sys.platform == "win32":
        # Windows 上使用 SelectorEventLoopPolicy 以确保
        # uvicorn + asyncio 子进程正常工作
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        # 设置 UTF-8 编码（中文 Windows 默认 GBK）
        import io

        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")


def setup_logging(level: str = "INFO") -> None:
    """配置日志"""
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.StreamHandler(sys.stdout),
        ],
    )


def run_server(args: argparse.Namespace) -> None:
    """启动 FastAPI 服务"""
    setup_logging(args.log_level)

    import uvicorn

    uvicorn.run(
        "agent_labs.api.app:create_app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        factory=True,
        log_level=args.log_level.lower(),
    )


def run_chat(args: argparse.Namespace) -> None:
    """启动 CLI 交互聊天"""
    from agent_labs.cli.chat import run_chat as _run_chat

    asyncio.run(
        _run_chat(
            model_id=args.model,
            log_level=args.log_level,
        )
    )


def main() -> None:
    """主入口"""
    setup_platform()

    parser = argparse.ArgumentParser(description="Agent-Labs")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # ---- server 子命令 (默认) ----
    server_parser = subparsers.add_parser("server", help="Start the API server (default)")
    server_parser.add_argument("--host", default="0.0.0.0", help="Host to bind")
    server_parser.add_argument("--port", type=int, default=8000, help="Port to bind")
    server_parser.add_argument("--log-level", default="INFO", help="Log level")
    server_parser.add_argument("--reload", action="store_true", help="Enable hot reload (dev mode)")

    # ---- chat 子命令 ----
    chat_parser = subparsers.add_parser("chat", help="Start interactive CLI chat mode")
    chat_parser.add_argument(
        "--model",
        "-m",
        default=None,
        help="Model ID to use (e.g. claude-sonnet-4-6, gpt-4o). Auto-select by tier if omitted.",
    )
    chat_parser.add_argument(
        "--log-level",
        default="WARNING",
        help="Log level for chat mode (default: WARNING to reduce noise)",
    )

    # 也支持顶层参数（向后兼容：python -m agent_labs --host ... --port ...）
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind")
    parser.add_argument("--log-level", default="INFO", help="Log level")
    parser.add_argument("--reload", action="store_true", help="Enable hot reload (dev mode)")

    args = parser.parse_args()

    if args.command == "chat":
        run_chat(args)
    elif args.command == "server" or args.command is None:
        # 将顶层参数合并给 server
        if args.command is None:
            # 没有子命令时的向后兼容
            pass
        run_server(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
