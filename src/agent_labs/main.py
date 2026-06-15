"""
Agent-Labs 入口文件

启动方式：
    python -m agent_labs
    # 或
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


def main() -> None:
    """主入口"""
    setup_platform()

    parser = argparse.ArgumentParser(description="Agent-Labs Server")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind")
    parser.add_argument("--log-level", default="INFO", help="Log level")
    parser.add_argument("--reload", action="store_true", help="Enable hot reload (dev mode)")
    args = parser.parse_args()

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


if __name__ == "__main__":
    main()
