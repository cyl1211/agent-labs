"""
执行命令工具

安全执行系统命令，支持超时控制和沙箱约束。
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any

from ...core.types import ToolResult
from ..base import BaseTool


class ExecuteCommandTool(BaseTool):
    """执行系统命令"""

    name = "execute_command"
    description = (
        "执行系统命令并返回输出。命令在隔离的子进程中运行，"
        "有超时限制和工作目录约束。需要审批权限和沙箱。"
    )
    permission_level = "execute"

    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "要执行的 Shell 命令",
            },
            "working_dir": {
                "type": "string",
                "description": "工作目录，默认为当前项目目录",
            },
            "timeout_seconds": {
                "type": "integer",
                "description": "超时时间（秒），默认 60，最大 120",
                "default": 60,
            },
        },
        "required": ["command"],
    }

    # 危险命令黑名单（完全禁止）
    _FORBIDDEN_COMMANDS = [
        "rm -rf /",
        "rd /s /q C:\\",
        "format",
        "mkfs",
        "dd if=",
        ":(){ :|:& };:",  # fork bomb
        "shutdown",
        "reboot",
        "halt",
        "chmod 777 /",
    ]

    # 允许的 shell（Windows 和 Unix）
    _ALLOWED_SHELLS = ["bash", "sh", "cmd", "powershell", "pwsh"]

    async def execute(
        self,
        command: str = "",
        working_dir: str = "",
        timeout_seconds: int = 60,
        **kwargs,
    ) -> ToolResult:
        """
        执行系统命令

        Args:
            command: 要执行的命令
            working_dir: 工作目录
            timeout_seconds: 超时(秒)

        Returns:
            ToolResult
        """
        if not command.strip():
            return ToolResult(
                success=False,
                content="",
                error="命令不能为空",
            )

        # 安全检查：禁止危险命令
        check_result = self._safety_check(command)
        if check_result:
            return ToolResult(
                success=False,
                content="",
                error=f"安全限制：{check_result}",
            )

        # 超时限制
        timeout_seconds = min(max(timeout_seconds, 5), 120)

        # 确定工作目录
        if working_dir:
            cwd = Path(working_dir).expanduser().resolve()
            if not cwd.exists():
                return ToolResult(
                    success=False,
                    content="",
                    error=f"工作目录不存在: {cwd}",
                )
            if not cwd.is_dir():
                return ToolResult(
                    success=False,
                    content="",
                    error=f"工作目录路径不是目录: {cwd}",
                )
        else:
            cwd = Path.cwd()

        try:
            # 使用 asyncio subprocess 执行命令
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(cwd),
                env={**os.environ},
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=timeout_seconds,
                )
            except TimeoutError:
                process.kill()
                await process.wait()
                return ToolResult(
                    success=False,
                    content="",
                    error=f"命令执行超时（{timeout_seconds}s）: {command[:100]}",
                    metadata={
                        "command": command,
                        "working_dir": str(cwd),
                        "timeout": True,
                    },
                )

            stdout_str = stdout.decode("utf-8", errors="replace")
            stderr_str = stderr.decode("utf-8", errors="replace")

            # 截断过长输出
            output = ""
            if stdout_str:
                output += stdout_str
            if stderr_str:
                if output:
                    output += "\n[STDERR]\n"
                output += stderr_str

            max_output = 10000
            truncated = len(output) > max_output
            if truncated:
                output = output[:max_output] + f"\n\n... [截断] 输出共 {len(output)} 字符"

            return ToolResult(
                success=process.returncode == 0,
                content=output or "(无输出)",
                metadata={
                    "command": command,
                    "working_dir": str(cwd),
                    "returncode": process.returncode,
                    "timeout_seconds": timeout_seconds,
                    "truncated": truncated,
                },
            )

        except FileNotFoundError:
            return ToolResult(
                success=False,
                content="",
                error=f"Shell 不可用或命令未找到: {command[:100]}",
            )
        except Exception as e:
            return ToolResult(
                success=False,
                content="",
                error=f"命令执行异常: {e}",
                metadata={"command": command},
            )

    def _safety_check(self, command: str) -> str | None:
        """安全检查：检测禁止的危险命令"""
        cmd_lower = command.lower()

        for forbidden in self._FORBIDDEN_COMMANDS:
            if forbidden.lower() in cmd_lower:
                return f"禁止执行危险命令: {forbidden}"

        return None
