"""
上下文工程

提供上下文构建、压缩和知识注入的核心功能。
"""

from __future__ import annotations

from .builder import ContextBuilder
from .compressor import CompressionResult, ContextCompressor
from .knowledge import KnowledgeInjector, KnowledgeItem

__all__ = [
    "ContextBuilder",
    "ContextCompressor",
    "CompressionResult",
    "KnowledgeInjector",
    "KnowledgeItem",
]
