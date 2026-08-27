"""
人工确认机制

基于 LangGraph interrupt 机制实现审批工作流：
1. 高风险操作前暂停图执行
2. 等待人工审批
3. 审批通过 → 继续执行
4. 审批拒绝 → 取消操作

审批场景：
- 文件写入操作
- 命令执行
- 外部 API 调用
- 删除操作
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

logger = logging.getLogger(__name__)


class ApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class ApprovalAction(StrEnum):
    WRITE_FILE = "write_file"
    EXECUTE_COMMAND = "execute_command"
    WEB_FETCH = "web_fetch"
    DELETE_DATA = "delete_data"
    API_CALL = "api_call"
    CUSTOM = "custom"


@dataclass
class ApprovalRequest:
    """审批请求"""

    request_id: str
    action: ApprovalAction
    description: str
    details: dict[str, Any] = field(default_factory=dict)
    status: ApprovalStatus = ApprovalStatus.PENDING
    created_by: str = ""
    session_id: str = ""
    risk_level: str = "medium"  # low, medium, high, critical
    auto_expire_seconds: int = 300  # 5 分钟自动过期

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "action": self.action.value,
            "description": self.description,
            "details": self.details,
            "status": self.status.value,
            "risk_level": self.risk_level,
            "session_id": self.session_id,
        }

    def to_user_message(self) -> str:
        """生成给用户的审批提示消息"""
        risk_icons = {
            "low": "ℹ️",
            "medium": "⚠️",
            "high": "🔴",
            "critical": "🚨",
        }
        icon = risk_icons.get(self.risk_level, "❓")

        return "\n".join(
            [
                f"{icon} **Agent Approval Required** [{self.risk_level.upper()} RISK]",
                "",
                f"**Action:** {self.action.value}",
                f"**Description:** {self.description}",
                "",
                "**Details:**",
            ]
            + [f"  - {k}: {str(v)[:100]}" for k, v in self.details.items()]
            + [
                "",
                f"Request ID: {self.request_id}",
                "Reply with **APPROVE** or **REJECT** to proceed.",
            ]
        )


class ApprovalManager:
    """审批管理器

    管理审批请求的生命周期：
    - 创建审批请求
    - 暂停图执行（通过 LangGraph interrupt）
    - 处理审批结果
    - 自动过期管理

    使用方式：
        manager = ApprovalManager()
        request = manager.create_request(
            action=ApprovalAction.WRITE_FILE,
            description="Write to config.yaml",
            details={"path": "/etc/config.yaml", "size": "2KB"},
        )
        # ... 等待用户审批 ...
        manager.approve(request.request_id)
        # 或 manager.reject(request.request_id, "理由")
    """

    def __init__(self, auto_expire_seconds: int = 300):
        self.auto_expire_seconds = auto_expire_seconds
        self._requests: dict[str, ApprovalRequest] = {}
        self._session_pending: dict[str, list[str]] = {}  # session_id → [request_ids]

    def create_request(
        self,
        action: ApprovalAction,
        description: str,
        details: dict[str, Any] | None = None,
        session_id: str = "",
        risk_level: str = "medium",
    ) -> ApprovalRequest:
        """创建审批请求"""
        import uuid

        request_id = f"approval_{uuid.uuid4().hex[:12]}"
        request = ApprovalRequest(
            request_id=request_id,
            action=action,
            description=description,
            details=details or {},
            session_id=session_id,
            risk_level=risk_level,
            auto_expire_seconds=self.auto_expire_seconds,
        )
        self._requests[request_id] = request

        if session_id:
            self._session_pending.setdefault(session_id, []).append(request_id)

        logger.info(f"[Approval] 创建请求: {request_id} (action={action.value}, risk={risk_level})")
        return request

    def approve(self, request_id: str, comment: str = "") -> ApprovalRequest | None:
        """批准请求"""
        request = self._requests.get(request_id)
        if not request:
            logger.warning(f"[Approval] 请求不存在: {request_id}")
            return None

        if request.status != ApprovalStatus.PENDING:
            logger.warning(f"[Approval] 请求 {request_id} 状态为 {request.status}，不能批准")
            return None

        request.status = ApprovalStatus.APPROVED
        logger.info(f"[Approval] 已批准: {request_id}" + (f" ({comment})" if comment else ""))
        return request

    def reject(self, request_id: str, reason: str = "") -> ApprovalRequest | None:
        """拒绝请求"""
        request = self._requests.get(request_id)
        if not request:
            return None

        if request.status != ApprovalStatus.PENDING:
            return None

        request.status = ApprovalStatus.REJECTED
        request.details["reject_reason"] = reason
        logger.info(f"[Approval] 已拒绝: {request_id}" + (f" ({reason})" if reason else ""))
        return request

    def cancel(self, request_id: str) -> ApprovalRequest | None:
        """取消请求"""
        request = self._requests.get(request_id)
        if not request:
            return None

        request.status = ApprovalStatus.CANCELLED
        return request

    def get_request(self, request_id: str) -> ApprovalRequest | None:
        """获取审批请求"""
        return self._requests.get(request_id)

    def get_pending(self, session_id: str = "") -> list[ApprovalRequest]:
        """获取待审批的请求"""
        if session_id:
            ids = self._session_pending.get(session_id, [])
            return [
                r
                for r in (self._requests.get(rid) for rid in ids)
                if r and r.status == ApprovalStatus.PENDING
            ]
        return [r for r in self._requests.values() if r.status == ApprovalStatus.PENDING]

    def get_session_requests(self, session_id: str) -> list[ApprovalRequest]:
        """获取会话的所有请求"""
        ids = self._session_pending.get(session_id, [])
        return [r for r in (self._requests.get(rid) for rid in ids) if r]

    def expire_old_requests(self) -> int:
        """使过期的请求自动失效"""

        expired = 0
        for request in self._requests.values():
            if request.status != ApprovalStatus.PENDING:
                continue
            # 简单检查（实际应基于 created_at）
            request.status = ApprovalStatus.EXPIRED
            expired += 1

        if expired:
            logger.info(f"[Approval] {expired} 个请求已过期")
        return expired

    def needs_approval(self, tool_name: str) -> bool:
        """检查工具是否需要审批"""
        approval_required_tools = {
            "write_file": ApprovalAction.WRITE_FILE,
            "execute_command": ApprovalAction.EXECUTE_COMMAND,
            "web_fetch": ApprovalAction.WEB_FETCH,
        }
        return tool_name in approval_required_tools

    def get_approval_action(self, tool_name: str) -> ApprovalAction | None:
        """获取工具对应的审批动作类型"""
        mapping = {
            "write_file": ApprovalAction.WRITE_FILE,
            "execute_command": ApprovalAction.EXECUTE_COMMAND,
            "web_fetch": ApprovalAction.WEB_FETCH,
        }
        return mapping.get(tool_name)

    def get_stats(self) -> dict[str, int]:
        """获取审批统计"""
        stats = {"total": len(self._requests)}
        for status in ApprovalStatus:
            stats[status.value] = sum(1 for r in self._requests.values() if r.status == status)
        return stats
