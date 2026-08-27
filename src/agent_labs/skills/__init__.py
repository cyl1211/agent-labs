"""
技能系统

提供技能注册、选择和执行的核心功能。
"""

from __future__ import annotations

from .base import BaseSkill
from .executor import SkillExecutor
from .registry import SkillRegistry
from .selector import SkillSelector

__all__ = [
    "BaseSkill",
    "SkillRegistry",
    "SkillSelector",
    "SkillExecutor",
]
