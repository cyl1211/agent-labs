"""
读取文件工具

支持读取文本文件，自动检测编码。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ...core.types import ToolResult
from ..base import BaseTool


class ReadFileTool(BaseTool):
    """读取文件内容"""

    name = "read_file"
    description = "读取指定路径的文件内容。支持文本文件，自动尝试 UTF-8 / GBK 编码。"
    permission_level = "read"

    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "要读取的文件路径（绝对路径或相对于工作目录的路径）",
            },
            "encoding": {
                "type": "string",
                "description": "文件编码，默认自动检测（先尝试 UTF-8，再尝试 GBK）",
                "default": "utf-8",
            },
            "max_lines": {
                "type": "integer",
                "description": "最大读取行数，默认 2000，设为 0 表示不限制",
                "default": 2000,
            },
        },
        "required": ["path"],
    }

    # 支持自动检测的编码列表
    _FALLBACK_ENCODINGS = ["utf-8", "gbk", "latin-1"]

    async def execute(
        self,
        path: str = "",
        encoding: str = "",
        max_lines: int = 2000,
        **kwargs,
    ) -> ToolResult:
        """
        读取文件内容

        Args:
            path: 文件路径
            encoding: 编码（留空自动检测）
            max_lines: 最大行数（0 = 不限制）

        Returns:
            ToolResult
        """
        file_path = Path(path).expanduser().resolve()

        if not file_path.exists():
            return ToolResult(
                success=False,
                content="",
                error=f"文件不存在: {file_path}",
            )

        if file_path.is_dir():
            return ToolResult(
                success=False,
                content="",
                error=f"路径是目录而非文件: {file_path}",
            )

        # 检查文件大小上限 (10MB)
        file_size = file_path.stat().st_size
        if file_size > 10 * 1024 * 1024:
            return ToolResult(
                success=False,
                content="",
                error=f"文件过大 ({file_size / 1024 / 1024:.1f}MB)，超过 10MB 上限",
            )

        # 读取文件
        read_error = None
        content = ""

        encodings_to_try = [encoding] if encoding else self._FALLBACK_ENCODINGS

        for enc in encodings_to_try:
            try:
                with open(file_path, encoding=enc) as f:
                    if max_lines > 0:
                        lines = []
                        for i, line in enumerate(f):
                            if i >= max_lines:
                                break
                            lines.append(line)
                        content = "".join(lines)
                    else:
                        content = f.read()
                read_error = None
                break
            except UnicodeDecodeError:
                read_error = f"无法以 {enc} 编码读取"
                continue
            except Exception as e:
                read_error = str(e)
                continue

        if read_error and not content:
            return ToolResult(
                success=False,
                content="",
                error=f"读取文件失败: {read_error}",
            )

        # 构造返回结果
        result_content = content
        if len(content) > 50000:
            result_content = (
                content[:50000] + f"\n\n... [截断] 文件共 {len(content)} 字符，仅显示前 50000 字符"
            )

        return ToolResult(
            success=True,
            content=result_content,
            metadata={
                "path": str(file_path),
                "size": file_size,
                "encoding": encoding or encodings_to_try[0],
                "total_chars": len(content),
                "truncated": len(content) > 50000,
            },
        )
