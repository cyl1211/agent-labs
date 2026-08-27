"""
Unit tests for built-in tools
"""

import os
import tempfile
from pathlib import Path

from agent_labs.tools.builtin.execute_command import ExecuteCommandTool
from agent_labs.tools.builtin.read_file import ReadFileTool
from agent_labs.tools.builtin.write_file import WriteFileTool


class TestReadFileTool:
    async def test_read_existing_file(self):
        tool = ReadFileTool()
        # 使用临时文件
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, encoding="utf-8"
        ) as f:
            f.write("line1\nline2\nline3\n")
            tmp_path = f.name

        try:
            result = await tool.execute(path=tmp_path)
            assert result.success
            assert "line1" in result.content
            assert "line2" in result.content
        finally:
            os.unlink(tmp_path)

    async def test_read_nonexistent_file(self):
        tool = ReadFileTool()
        result = await tool.execute(path="/nonexistent/file.txt")
        assert not result.success
        assert "不存在" in result.error

    async def test_read_directory(self):
        tool = ReadFileTool()
        result = await tool.execute(path=tempfile.gettempdir())
        assert not result.success
        assert "目录" in result.error

    async def test_read_with_max_lines(self):
        tool = ReadFileTool()
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, encoding="utf-8"
        ) as f:
            for i in range(100):
                f.write(f"line {i}\n")
            tmp_path = f.name

        try:
            result = await tool.execute(path=tmp_path, max_lines=10)
            assert result.success
            lines = result.content.strip().split("\n")
            assert len(lines) <= 10
        finally:
            os.unlink(tmp_path)

    async def test_tool_schema(self):
        tool = ReadFileTool()
        schema = tool.to_openai_schema()
        assert schema["type"] == "function"
        assert schema["function"]["name"] == "read_file"
        assert "path" in schema["function"]["parameters"]["required"]

        anthropic_schema = tool.to_anthropic_schema()
        assert anthropic_schema["name"] == "read_file"


class TestWriteFileTool:
    async def test_write_and_read(self):
        write_tool = WriteFileTool()
        read_tool = ReadFileTool()

        with tempfile.TemporaryDirectory() as tmp_dir:
            file_path = os.path.join(tmp_dir, "test_output.txt")
            result = await write_tool.execute(path=file_path, content="Hello, World!")
            assert result.success
            assert "已写入" in result.content

            # 验证内容
            read_result = await read_tool.execute(path=file_path)
            assert read_result.success
            assert "Hello, World!" in read_result.content

    async def test_write_to_forbidden_path(self):
        tool = WriteFileTool()
        result = await tool.execute(path="C:\\Windows\\test.txt", content="bad")
        assert not result.success
        assert "安全限制" in result.error

    async def test_write_creates_parent_dirs(self):
        tool = WriteFileTool()
        with tempfile.TemporaryDirectory() as tmp_dir:
            nested_path = os.path.join(tmp_dir, "a", "b", "c", "test.txt")
            result = await tool.execute(path=nested_path, content="nested")
            assert result.success
            assert Path(nested_path).exists()

    async def test_append_mode(self):
        tool = WriteFileTool()
        with tempfile.TemporaryDirectory() as tmp_dir:
            file_path = os.path.join(tmp_dir, "append_test.txt")
            await tool.execute(path=file_path, content="first\n", mode="w")
            result = await tool.execute(path=file_path, content="second\n", mode="a")
            assert result.success

            read_tool = ReadFileTool()
            read_result = await read_tool.execute(path=file_path)
            assert "first" in read_result.content
            assert "second" in read_result.content


class TestExecuteCommandTool:
    async def test_execute_echo(self):
        tool = ExecuteCommandTool()
        result = await tool.execute(command="echo hello")
        assert result.success
        assert "hello" in result.content

    async def test_execute_empty_command(self):
        tool = ExecuteCommandTool()
        result = await tool.execute(command="")
        assert not result.success
        assert "不能为空" in result.error

    async def test_execute_forbidden_command(self):
        tool = ExecuteCommandTool()
        result = await tool.execute(command="shutdown /s")
        assert not result.success
        assert "安全限制" in result.error

    async def test_execute_nonexistent_workdir(self):
        tool = ExecuteCommandTool()
        result = await tool.execute(
            command="echo test",
            working_dir="/nonexistent/directory/path",
        )
        assert not result.success
        assert "不存在" in result.error

    async def test_execute_with_timeout(self):
        tool = ExecuteCommandTool()
        # Windows/Unix 兼容的 sleep 命令
        import platform

        cmd = "ping -n 30 127.0.0.1 > nul" if platform.system() == "Windows" else "sleep 30"
        result = await tool.execute(command=cmd, timeout_seconds=1)
        assert not result.success
        assert "超时" in result.error

    async def test_tool_schema(self):
        tool = ExecuteCommandTool()
        schema = tool.to_dict()
        assert schema["name"] == "execute_command"
        assert "command" in schema["parameters"]["required"]
