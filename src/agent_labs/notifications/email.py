"""
邮件通知机制

支持：
- 关键节点通知（开始、完成、错误）
- SMTP 发送（支持 TLS/SSL）
- 通知级别过滤
- HTML + 纯文本双格式
"""

from __future__ import annotations

import logging
import smtplib
from dataclasses import dataclass, field
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

from ..core.types import NotificationLevel

logger = logging.getLogger(__name__)


@dataclass
class EmailConfig:
    """邮件配置"""

    enabled: bool = False
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    use_tls: bool = True
    from_addr: str = ""
    to_addrs: list[str] = field(default_factory=list)
    cc_addrs: list[str] = field(default_factory=list)
    # 通知级别过滤
    min_level: NotificationLevel = NotificationLevel.WARNING


class EmailNotifier:
    """邮件通知器

    在关键节点发送邮件通知。

    使用方式：
        config = EmailConfig(
            enabled=True,
            smtp_host="smtp.example.com",
            smtp_user="agent@example.com",
            smtp_password="***",
            to_addrs=["admin@example.com"],
        )
        notifier = EmailNotifier(config)
        await notifier.send("Task Completed", "The agent has finished.", level="completion")
    """

    def __init__(self, config: EmailConfig | None = None):
        self.config = config or EmailConfig()

    async def send(
        self,
        title: str,
        message: str,
        level: NotificationLevel = NotificationLevel.INFO,
        session_id: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """发送邮件通知

        Args:
            title: 通知标题
            message: 通知内容
            level: 通知级别
            session_id: 关联的会话 ID
            metadata: 附加元数据

        Returns:
            是否发送成功
        """
        if not self.config.enabled:
            logger.debug(f"[Email] 邮件通知已禁用，跳过: {title}")
            return False

        # 级别过滤
        if level.value < self.config.min_level.value:
            logger.debug(f"[Email] 通知级别 {level.value} 低于最低阈值，跳过")
            return False

        if not self.config.to_addrs:
            logger.warning("[Email] 未配置收件人，跳过发送")
            return False

        # 构建邮件
        subject = f"[Agent-Labs] [{level.value.upper()}] {title}"
        html_body = self._build_html(title, message, level, session_id, metadata)
        text_body = self._build_text(title, message, level, session_id, metadata)

        try:
            await self._send_email(subject, html_body, text_body)
            logger.info(f"[Email] 通知已发送: {subject}")
            return True
        except Exception as e:
            logger.error(f"[Email] 发送失败: {e}")
            return False

    async def send_error(
        self,
        error: str,
        session_id: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """发送错误通知"""
        return await self.send(
            title="Agent Error",
            message=f"An error occurred:\n\n{error}",
            level=NotificationLevel.ERROR,
            session_id=session_id,
            metadata=metadata,
        )

    async def send_completion(
        self,
        result_summary: str,
        session_id: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """发送完成通知"""
        return await self.send(
            title="Task Completed",
            message=f"Task completed successfully:\n\n{result_summary}",
            level=NotificationLevel.COMPLETION,
            session_id=session_id,
            metadata=metadata,
        )

    async def send_warning(
        self,
        warning: str,
        session_id: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """发送警告通知"""
        return await self.send(
            title="Agent Warning",
            message=warning,
            level=NotificationLevel.WARNING,
            session_id=session_id,
            metadata=metadata,
        )

    async def _send_email(self, subject: str, html_body: str, text_body: str) -> None:
        """通过 SMTP 发送邮件"""
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = self.config.from_addr or self.config.smtp_user
        msg["To"] = ", ".join(self.config.to_addrs)
        if self.config.cc_addrs:
            msg["Cc"] = ", ".join(self.config.cc_addrs)

        msg.attach(MIMEText(text_body, "plain", "utf-8"))
        msg.attach(MIMEText(html_body, "html", "utf-8"))

        all_recipients = self.config.to_addrs + self.config.cc_addrs

        if self.config.use_tls:
            server = smtplib.SMTP(self.config.smtp_host, self.config.smtp_port, timeout=30)
            server.starttls()
        else:
            server = smtplib.SMTP_SSL(self.config.smtp_host, self.config.smtp_port, timeout=30)

        try:
            if self.config.smtp_user:
                server.login(self.config.smtp_user, self.config.smtp_password)
            server.sendmail(msg["From"], all_recipients, msg.as_string())
        finally:
            server.quit()

    def _build_html(
        self,
        title: str,
        message: str,
        level: NotificationLevel,
        session_id: str,
        metadata: dict[str, Any] | None,
    ) -> str:
        """构建 HTML 邮件"""
        level_colors = {
            NotificationLevel.INFO: "#4a90d9",
            NotificationLevel.WARNING: "#f0ad4e",
            NotificationLevel.ERROR: "#d9534f",
            NotificationLevel.COMPLETION: "#5cb85c",
        }
        color = level_colors.get(level, "#666")

        meta_html = ""
        if session_id:
            meta_html += f"<p><strong>Session:</strong> {session_id}</p>\n"
        if metadata:
            for k, v in metadata.items():
                meta_html += f"<p><strong>{k}:</strong> {v}</p>\n"

        return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
    <div style="background: {color}; padding: 15px; border-radius: 5px 5px 0 0;">
        <h2 style="color: white; margin: 0;">[{level.value.upper()}] {title}</h2>
    </div>
    <div style="border: 1px solid #ddd; padding: 20px; border-radius: 0 0 5px 5px;">
        {meta_html}
        <pre style="background: #f5f5f5; padding: 15px; border-radius: 3px;
                    white-space: pre-wrap; word-wrap: break-word;">{message}</pre>
    </div>
    <p style="color: #999; font-size: 12px; text-align: center;">
        Sent by Agent-Labs Notification System
    </p>
</body>
</html>"""

    def _build_text(
        self,
        title: str,
        message: str,
        level: NotificationLevel,
        session_id: str,
        metadata: dict[str, Any] | None,
    ) -> str:
        """构建纯文本邮件"""
        lines = [
            f"[{level.value.upper()}] {title}",
            "=" * 50,
            "",
        ]
        if session_id:
            lines.append(f"Session: {session_id}")
        if metadata:
            for k, v in metadata.items():
                lines.append(f"{k}: {v}")
        lines.extend(["", message, "", "-- Agent-Labs Notification System"])
        return "\n".join(lines)
