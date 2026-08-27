"""
安全沙箱

提供：
- 进程沙箱：在隔离的子进程中执行代码
- Docker 沙箱：在 Docker 容器中执行（Phase 3 完整实现）
- 超时管理
- 资源限制
"""

from __future__ import annotations

import asyncio
import logging
import os
import tempfile
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class SandboxConfig:
    """沙箱配置"""

    mode: str = "process"  # process, docker
    timeout_seconds: int = 60
    max_memory_mb: int = 512
    max_disk_mb: int = 100
    allow_network: bool = False
    allow_file_system: bool = True
    working_dir: str = ""
    docker_image: str = "python:3.11-slim"


@dataclass
class SandboxResult:
    """沙箱执行结果"""

    success: bool
    stdout: str = ""
    stderr: str = ""
    exit_code: int = -1
    duration_ms: float = 0.0
    error: str = ""
    truncated: bool = False


class ProcessSandbox:
    """进程沙箱

    在隔离的子进程中执行代码/命令。

    安全措施：
    - 独立进程执行
    - 超时强制终止
    - 临时工作目录
    - 输出截断限制
    """

    def __init__(self, config: SandboxConfig | None = None):
        self.config = config or SandboxConfig()

    async def execute(
        self,
        code: str = "",
        command: str = "",
        timeout_seconds: int | None = None,
    ) -> SandboxResult:
        """在沙箱中执行代码或命令

        Args:
            code: Python 代码（将被写入临时文件并执行）
            command: Shell 命令
            timeout_seconds: 超时覆盖

        Returns:
            SandboxResult
        """
        import time

        timeout = timeout_seconds or self.config.timeout_seconds
        start = time.monotonic()

        # 确定工作目录
        cwd = self.config.working_dir or tempfile.mkdtemp(prefix="sandbox_")

        try:
            if code:
                result = await self._execute_code(code, cwd, timeout)
            elif command:
                result = await self._execute_command(command, cwd, timeout)
            else:
                return SandboxResult(
                    success=False,
                    error="No code or command specified",
                )
        finally:
            # 清理临时目录
            if not self.config.working_dir:
                try:
                    import shutil

                    shutil.rmtree(cwd, ignore_errors=True)
                except Exception:
                    pass

        result.duration_ms = (time.monotonic() - start) * 1000
        return result

    async def _execute_code(self, code: str, cwd: str, timeout: int) -> SandboxResult:
        """执行 Python 代码"""
        # 写入临时文件
        script_path = os.path.join(cwd, "script.py")
        with open(script_path, "w", encoding="utf-8") as f:
            f.write(code)

        process = await asyncio.create_subprocess_exec(
            "python",
            script_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
            env={**os.environ, "SANDBOX_MODE": "1"},
        )

        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
        except TimeoutError:
            process.kill()
            await process.wait()
            return SandboxResult(
                success=False,
                stdout="",
                stderr="",
                exit_code=-1,
                error=f"Code execution timed out ({timeout}s)",
            )

        stdout_str = stdout.decode("utf-8", errors="replace")
        stderr_str = stderr.decode("utf-8", errors="replace")

        # 截断输出
        max_output = 50000
        truncated = len(stdout_str) > max_output or len(stderr_str) > max_output
        stdout_str = stdout_str[:max_output]
        stderr_str = stderr_str[:max_output]

        return SandboxResult(
            success=process.returncode == 0,
            stdout=stdout_str,
            stderr=stderr_str,
            exit_code=process.returncode or 0,
            truncated=truncated,
        )

    async def _execute_command(self, command: str, cwd: str, timeout: int) -> SandboxResult:
        """执行 shell 命令"""
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
            env={**os.environ, "SANDBOX_MODE": "1"},
        )

        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
        except TimeoutError:
            process.kill()
            await process.wait()
            return SandboxResult(
                success=False,
                exit_code=-1,
                error=f"Command execution timed out ({timeout}s)",
            )

        stdout_str = stdout.decode("utf-8", errors="replace")
        stderr_str = stderr.decode("utf-8", errors="replace")

        max_output = 50000
        truncated = len(stdout_str) > max_output or len(stderr_str) > max_output

        return SandboxResult(
            success=process.returncode == 0,
            stdout=stdout_str[:max_output],
            stderr=stderr_str[:max_output],
            exit_code=process.returncode or 0,
            truncated=truncated,
        )


class DockerSandbox:
    """Docker 沙箱 (Phase 3 完整实现)

    在隔离的 Docker 容器中执行代码。

    当前阶段提供框架接口，后续对接 Docker SDK。
    """

    def __init__(self, config: SandboxConfig | None = None):
        self.config = config or SandboxConfig(mode="docker")

    async def execute(
        self,
        code: str = "",
        command: str = "",
        timeout_seconds: int | None = None,
    ) -> SandboxResult:
        """在 Docker 容器中执行（框架）

        实际执行需要使用 Docker SDK 或 subprocess 调用 docker CLI。
        """
        logger.info("[DockerSandbox] Docker 执行框架已就绪（Phase 3 完整实现）")
        return SandboxResult(
            success=False,
            error="Docker sandbox not yet implemented (Phase 3)",
        )


class SandboxFactory:
    """沙箱工厂"""

    @staticmethod
    def create(config: SandboxConfig) -> ProcessSandbox | DockerSandbox:
        """根据配置创建沙箱"""
        if config.mode == "docker":
            return DockerSandbox(config)
        return ProcessSandbox(config)
