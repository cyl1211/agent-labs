"""通知机制 — 邮件通知（关键节点、错误、完成）"""

from __future__ import annotations

from .email import EmailConfig, EmailNotifier

__all__ = ["EmailNotifier", "EmailConfig"]
