# API 参考

启动服务后访问 `http://localhost:8000/docs` 查看 Swagger UI。

## 端点一览

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/health` | 健康检查 |
| POST | `/api/v1/agents/invoke` | 同步执行 Agent |
| WS | `/api/v1/agents/stream` | 流式执行 Agent |
| GET | `/api/v1/sessions` | 列出所有会话 |
| POST | `/api/v1/sessions` | 创建新会话 |
| GET | `/api/v1/sessions/{id}` | 获取会话状态 |
| GET | `/api/v1/sessions/{id}/history` | 获取消息历史 |
| DELETE | `/api/v1/sessions/{id}` | 关闭会话 |
| GET | `/api/v1/tools` | 列出所有工具 |
| POST | `/api/v1/tools/execute` | 直接执行工具 |

## POST /api/v1/agents/invoke

请求体：
```json
{
  "query": "帮我分析这个项目的架构",
  "session_id": "可选，已有会话ID",
  "user_id": "可选，用户标识"
}
```

响应：
```json
{
  "session_id": "f69335de9cc44e20",
  "answer": "这个项目采用三层解耦架构...",
  "tool_calls_made": [
    {"name": "read_file", "success": true, "duration_ms": 35.2}
  ],
  "iterations": 3,
  "tokens_used": 1500,
  "duration_ms": 3200.5,
  "metadata": {"error": null, "next_action": "answer"}
}
```

## WebSocket /api/v1/agents/stream

客户端发送：
```json
{"query": "帮我写一个Python脚本", "session_id": "optional"}
```

服务端逐步推送事件：
```json
{"event_type": "thinking", "data": {"thought": "我需要先了解需求..."}, "timestamp": "..."}
{"event_type": "tool_call", "data": {"name": "write_file", "input": {...}}, "timestamp": "..."}
{"event_type": "tool_result", "data": {"name": "write_file", "result": "..."}, "timestamp": "..."}
{"event_type": "answer", "data": {"answer": "我已经写好脚本..."}, "timestamp": "..."}
```

## GET /api/v1/sessions

查询参数：
- `status`: 过滤状态 (active / completed / error)

响应：
```json
{
  "sessions": ["abc123", "def456"],
  "count": 2
}
```

## GET /api/v1/sessions/{id}

响应：
```json
{
  "session_id": "abc123",
  "agent_id": "ReactAgent:react",
  "status": "active",
  "messages": [...],
  "iterations": 5,
  "tool_calls_count": 3,
  "tokens_used": 2500,
  "created_at": "2026-06-15T10:30:00Z",
  "updated_at": "2026-06-15T10:32:15Z"
}
```
