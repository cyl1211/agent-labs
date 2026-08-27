"""
代码分析技能

组合 read_file + web_search 两个工具，实现代码阅读与分析流程：
1. 读取目标代码文件
2. 搜索相关技术文档或最佳实践
3. 汇总分析结果
"""

from __future__ import annotations

import logging

from ...core.types import SkillContext, SkillResult
from ..base import BaseSkill

logger = logging.getLogger(__name__)


class CodeAnalysisSkill(BaseSkill):
    """代码分析技能

    读取指定代码文件，并结合网络搜索提供分析建议。
    """

    name = "代码分析"
    description = "读取代码文件并搜索相关技术文档，提供代码分析报告"
    triggers = [
        "分析代码",
        "代码分析",
        "code analysis",
        "review code",
        "审查代码",
        "分析这段代码",
        "看看这段代码",
        "代码审查",
        "帮我分析",
        "分析文件",
    ]
    required_tools = ["read_file", "web_search"]

    async def execute(self, context: SkillContext) -> SkillResult:
        """执行代码分析

        从 context.params 中获取:
        - file_path: 要分析的文件路径
        - analysis_focus: 分析重点（可选，如 "安全"、"性能"、"风格"）

        执行流程:
        1. 读取目标文件
        2. 搜索相关技术文档
        3. 汇总结果
        """
        file_path = context.params.get("file_path", "")
        analysis_focus = context.params.get("analysis_focus", "")
        query = context.params.get("query", "")

        if not file_path:
            return SkillResult(
                success=False,
                content="",
                error="缺少参数: file_path (要分析的文件路径)",
            )

        tool_results = context.tool_results
        tool_calls = []

        # Step 1: 读取文件
        read_result = tool_results.get("read_file")
        if read_result is None:
            # 如果上下文中没有预执行的结果，记录需要的工具调用
            tool_calls.append(
                {
                    "tool": "read_file",
                    "args": {"path": file_path},
                    "purpose": "读取目标代码文件",
                }
            )
            file_content = ""
        elif not read_result.success:
            return SkillResult(
                success=False,
                content="",
                error=f"无法读取文件 {file_path}: {read_result.error}",
                tool_calls=tool_calls,
            )
        else:
            file_content = read_result.content

        # Step 2: 搜索相关文档
        search_query = query or self._build_search_query(file_path, analysis_focus, file_content)
        search_result = tool_results.get("web_search")
        if search_result is None:
            tool_calls.append(
                {
                    "tool": "web_search",
                    "args": {"query": search_query, "num_results": 5},
                    "purpose": "搜索相关技术文档和最佳实践",
                }
            )
        elif not search_result.success:
            logger.warning(f"[CodeAnalysis] 搜索失败: {search_result.error}")
            # 搜索失败不阻止整个分析过程

        # Step 3: 如果没有预执行的结果，返回需要执行的工具列表
        if tool_calls:
            return SkillResult(
                success=True,
                content="",
                error=None,
                tool_calls=tool_calls,
                metadata={
                    "stage": "pending_tools",
                    "file_path": file_path,
                    "analysis_focus": analysis_focus,
                },
            )

        # Step 4: 汇总分析
        analysis_text = self._build_analysis(
            file_path,
            file_content,
            analysis_focus,
            search_result.content if search_result and search_result.success else "",
        )

        return SkillResult(
            success=True,
            content=analysis_text,
            tool_calls=[
                {"tool": "read_file", "purpose": "读取目标文件"},
                {"tool": "web_search", "purpose": "搜索相关文档"},
            ],
            metadata={
                "file_path": file_path,
                "analysis_focus": analysis_focus,
                "file_size": len(file_content),
            },
        )

    def _build_search_query(
        self,
        file_path: str,
        analysis_focus: str,
        file_content: str,
    ) -> str:
        """构建搜索查询"""
        import os

        file_name = os.path.basename(file_path)
        file_ext = os.path.splitext(file_name)[1]

        # 检测语言/框架
        lang_hints = self._detect_language_hints(file_path, file_content)

        parts = []
        if analysis_focus:
            parts.append(f"{analysis_focus} best practices")

        if lang_hints:
            parts.append(f"{lang_hints} {file_ext}")

        if not parts:
            parts.append("code review best practices")

        parts.append(file_name)
        return " ".join(parts)

    def _detect_language_hints(self, file_path: str, content: str) -> str:
        """检测代码语言和框架提示"""
        ext_map = {
            ".py": "Python",
            ".js": "JavaScript",
            ".ts": "TypeScript",
            ".rs": "Rust",
            ".go": "Go",
            ".java": "Java",
            ".cpp": "C++",
            ".c": "C",
            ".rb": "Ruby",
            ".php": "PHP",
        }

        import os

        ext = os.path.splitext(file_path)[1].lower()
        lang = ext_map.get(ext, "")

        # 检测框架
        frameworks = []
        content_lower = content[:2000].lower() if content else ""
        if "fastapi" in content_lower:
            frameworks.append("FastAPI")
        if "flask" in content_lower:
            frameworks.append("Flask")
        if "django" in content_lower:
            frameworks.append("Django")
        if "react" in content_lower or "jsx" in content_lower:
            frameworks.append("React")
        if "vue" in content_lower:
            frameworks.append("Vue")
        if "langgraph" in content_lower:
            frameworks.append("LangGraph")
        if "pydantic" in content_lower:
            frameworks.append("Pydantic")

        if frameworks:
            return " ".join(frameworks)
        return lang

    def _build_analysis(
        self,
        file_path: str,
        file_content: str,
        analysis_focus: str,
        search_results: str,
    ) -> str:
        """构建分析报告"""
        import os

        file_name = os.path.basename(file_path)
        lines = file_content.split("\n")
        line_count = len(lines)
        char_count = len(file_content)

        report = []
        report.append(f"=== 代码分析报告: {file_name} ===")
        report.append("")
        report.append(f"文件路径: {file_path}")
        report.append(f"文件大小: {line_count} 行 / {char_count} 字符")
        report.append("")

        if analysis_focus:
            report.append(f"分析重点: {analysis_focus}")
            report.append("")

        # 文件内容摘要
        report.append("--- 文件内容 ---")
        if line_count <= 50:
            report.append(file_content)
        else:
            report.append("\n".join(lines[:30]))
            report.append(f"\n... [省略 {line_count - 50} 行] ...\n")
            report.append("\n".join(lines[-20:]))

        # 搜索参考
        if search_results:
            report.append("")
            report.append("--- 相关参考资料 ---")
            report.append(search_results)

        report.append("")
        report.append("--- 分析提示 ---")
        report.append("1. 请关注代码中的潜在问题：命名规范、错误处理、性能瓶颈")
        report.append("2. 参考以上搜索结果的建议改进代码")
        report.append("3. 建议增加适当的单元测试覆盖")

        return "\n".join(report)
