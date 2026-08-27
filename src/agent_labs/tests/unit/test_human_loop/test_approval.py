"""Unit tests for human-in-the-loop approval"""

from agent_labs.human_loop.approval import (
    ApprovalAction,
    ApprovalManager,
    ApprovalRequest,
    ApprovalStatus,
)


class TestApprovalManager:
    def test_create_request(self):
        mgr = ApprovalManager()
        req = mgr.create_request(
            ApprovalAction.WRITE_FILE,
            "Write config",
            {"path": "/etc/test.yaml"},
            session_id="s1",
        )
        assert req.request_id
        assert req.action == ApprovalAction.WRITE_FILE
        assert req.status == ApprovalStatus.PENDING
        assert req.session_id == "s1"

    def test_approve(self):
        mgr = ApprovalManager()
        req = mgr.create_request(ApprovalAction.EXECUTE_COMMAND, "Run test")
        result = mgr.approve(req.request_id, "looks good")
        assert result is not None
        assert result.status == ApprovalStatus.APPROVED

    def test_reject(self):
        mgr = ApprovalManager()
        req = mgr.create_request(ApprovalAction.WRITE_FILE, "Write")
        result = mgr.reject(req.request_id, "too risky")
        assert result is not None
        assert result.status == ApprovalStatus.REJECTED
        assert "too risky" in result.details["reject_reason"]

    def test_cancel(self):
        mgr = ApprovalManager()
        req = mgr.create_request(ApprovalAction.API_CALL, "Call API")
        result = mgr.cancel(req.request_id)
        assert result.status == ApprovalStatus.CANCELLED

    def test_cannot_approve_twice(self):
        mgr = ApprovalManager()
        req = mgr.create_request(ApprovalAction.WRITE_FILE, "Write")
        mgr.approve(req.request_id)
        result = mgr.approve(req.request_id)
        assert result is None

    def test_get_pending_by_session(self):
        mgr = ApprovalManager()
        mgr.create_request(ApprovalAction.WRITE_FILE, "w1", session_id="s1")
        mgr.create_request(ApprovalAction.WRITE_FILE, "w2", session_id="s1")
        mgr.create_request(ApprovalAction.WRITE_FILE, "w3", session_id="s2")
        pending_s1 = mgr.get_pending(session_id="s1")
        assert len(pending_s1) == 2
        pending_s2 = mgr.get_pending(session_id="s2")
        assert len(pending_s2) == 1

    def test_needs_approval(self):
        mgr = ApprovalManager()
        assert mgr.needs_approval("write_file")
        assert mgr.needs_approval("execute_command")
        assert not mgr.needs_approval("read_file")

    def test_get_approval_action(self):
        mgr = ApprovalManager()
        assert mgr.get_approval_action("write_file") == ApprovalAction.WRITE_FILE
        assert mgr.get_approval_action("unknown_tool") is None

    def test_to_user_message(self):
        req = ApprovalRequest(
            request_id="test-1",
            action=ApprovalAction.EXECUTE_COMMAND,
            description="Run dangerous script",
            details={"command": "rm -rf /"},
            risk_level="critical",
        )
        msg = req.to_user_message()
        assert "CRITICAL" in msg
        assert "rm -rf" in msg
        assert "APPROVE" in msg

    def test_get_stats(self):
        mgr = ApprovalManager()
        mgr.create_request(ApprovalAction.WRITE_FILE, "w1")
        mgr.create_request(ApprovalAction.EXECUTE_COMMAND, "e1")
        mgr.approve(list(mgr._requests.keys())[0])
        stats = mgr.get_stats()
        assert stats["total"] == 2
        assert stats["approved"] == 1
        assert stats["pending"] == 1
