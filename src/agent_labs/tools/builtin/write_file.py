"""
写入文件工具

支持创建和覆写文件，需要审批权限。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ...core.types import ToolResult
from ..base import BaseTool


class WriteFileTool(BaseTool):
    """写入文件内容"""

    name = "write_file"
    description = "将内容写入文件。会创建父目录（如不存在），默认覆写已存在的文件。需要审批权限。"
    permission_level = "write"

    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "要写入的文件路径（绝对路径或相对于工作目录的路径）",
            },
            "content": {
                "type": "string",
                "description": "要写入的文件内容",
            },
            "encoding": {
                "type": "string",
                "description": "文件编码，默认 UTF-8",
                "default": "utf-8",
            },
            "mode": {
                "type": "string",
                "description": "写入模式: 'w' 覆写, 'a' 追加。默认 'w'",
                "enum": ["w", "a"],
                "default": "w",
            },
        },
        "required": ["path", "content"],
    }

    async def execute(
        self,
        path: str = "",
        content: str = "",
        encoding: str = "utf-8",
        mode: str = "w",
        **kwargs,
    ) -> ToolResult:
        """
        写入文件

        Args:
            path: 文件路径
            content: 写入内容
            encoding: 编码
            mode: 写入模式

        Returns:
            ToolResult
        """
        file_path = Path(path).expanduser().resolve()

        # 安全检查：不允许写入到系统敏感目录
        forbidden_prefixes = [
            "/etc/",
            "/sys/",
            "/proc/",
            "/dev/",
            "C:\\Windows",
            "C:\\windows",
            "/System/",
            "/Library/System/",
        ]
        path_str = str(file_path).replace("\\", "/")
        for prefix in forbidden_prefixes:
            if path_str.startswith(prefix.replace("\\", "/")):
                return ToolResult(
                    success=False,
                    content="",
                    error=f"安全限制：不允许写入到系统目录 ({prefix})",
                )

        try:
            # 确保父目录存在
            file_path.parent.mkdir(parents=True, exist_ok=True)

            written_bytes = 0
            with open(file_path, mode, encoding=encoding) as f:
                f.write(content)
                written_bytes = len(content.encode(encoding))

            return ToolResult(
                success=True,
                content=f"文件已写入: {file_path} ({written_bytes} bytes)",
                metadata={
                    "path": str(file_path),
                    "mode": mode,
                    "encoding": encoding,
                    "bytes_written": written_bytes,
                    "chars_written": len(content),
                },
            )
        except PermissionError as e:
            return ToolResult(
                success=False,
                content="",
                error=f"权限不足，无法写入文件: {e}",
            )
        except OSError as e:
            return ToolResult(
                success=False,
                content="",
                error=f"写入文件失败 ({e.__class__.__name__}): {e}",
            )
