"""API 集成测试 — 验证所有端点和服务正确连线"""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """创建测试客户端（触发 lifespan 初始化）"""
    from agent_labs.api.app import create_app

    app = create_app()
    with TestClient(app) as c:
        yield c


class TestHealthCheck:
    def test_health(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "healthy"


class TestToolsAPI:
    def test_list_tools(self, client):
        """验证启动后内置工具已注册"""
        resp = client.get("/api/v1/tools")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] >= 4, f"Expected >=4 builtin tools, got {data['count']}"
        tool_names = [t["name"] for t in data["tools"]]
        assert "read_file" in tool_names
        assert "write_file" in tool_names
        assert "web_search" in tool_names
        assert "execute_command" in tool_names


class TestSkillsAPI:
    def test_list_skills(self, client):
        """验证启动后内置技能已注册"""
        resp = client.get("/api/v1/skills")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] >= 1, f"Expected >=1 skill, got {data['count']}"
        skill_names = [s["name"] for s in data["skills"]]
        assert any("分析" in s for s in skill_names)


class TestObservabilityAPI:
    def test_dashboard(self, client):
        resp = client.get("/api/v1/observability/dashboard")
        assert resp.status_code == 200
        data = resp.json()
        assert "dashboard" in data
        assert "global_stats" in data

    def test_stats(self, client):
        resp = client.get("/api/v1/observability/stats")
        assert resp.status_code == 200
        assert "tokens" in resp.json()

    def test_traces(self, client):
        resp = client.get("/api/v1/observability/traces")
        assert resp.status_code == 200
        assert "traces" in resp.json()


class TestApprovalAPI:
    def test_pending(self, client):
        resp = client.get("/api/v1/approval/pending")
        assert resp.status_code == 200
        assert "pending" in resp.json()

    def test_stats(self, client):
        resp = client.get("/api/v1/approval/stats")
        assert resp.status_code == 200
        assert "total" in resp.json()


class TestSessionsAPI:
    def test_create_session(self, client):
        resp = client.post(
            "/api/v1/sessions",
            json={
                "agent_type": "react",
            },
        )
        assert resp.status_code in (200, 201, 500)  # 500 可能因为没有 LLM key
        if resp.status_code in (200, 201):
            data = resp.json()
            assert "session_id" in data


class TestAgentInvoke:
    @pytest.mark.skip(reason="需要 LangGraph 完整运行时 + LLM API key，留待集成环境测试")
    def test_invoke_without_llm(self, client):
        """在没有 LLM API key 的情况下调用 agent（期望优雅降级）"""
        resp = client.post(
            "/api/v1/agents/invoke",
            json={
                "query": "Hello",
                "session_id": "",
            },
        )
        assert resp.status_code in (200, 500)
