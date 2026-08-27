"""
内置技能集

提供开箱即用的技能：
- 代码分析 — 读取代码文件 + 搜索相关文档/最佳实践
"""

from __future__ import annotations

from .code_analysis import CodeAnalysisSkill

__all__ = [
    "CodeAnalysisSkill",
    "register_all_builtin_skills",
]


def register_all_builtin_skills(registry) -> None:
    """向注册表注册所有内置技能"""
    from .code_analysis import CodeAnalysisSkill

    registry.register(CodeAnalysisSkill())
