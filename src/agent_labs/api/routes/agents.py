"""
Agent API 路由

端点：
- POST /agents/invoke — 同步执行 Agent
- WS   /agents/stream — 流式执行 Agent
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from ...core.types import AgentContext, AgentInput, AgentOutput, Message, Role
from ..deps import get_memory_manager, get_react_agent, get_session_manager

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/invoke", response_model=AgentOutput)
async def invoke_agent(request: dict[str, Any]) -> AgentOutput:
    """
    同步执行 Agent

    请求体：
    ```json
    {
        "query": "用户的请求",
        "session_id": "可选，已有会话 ID",
        "user_id": "可选，用户标识"
    }
    ```

    返回 AgentOutput，包含 answer、iterations、tokens_used 等。
    """
    query = request.get("query", "")
    if not query:
        raise HTTPException(status_code=400, detail="'query' field is required")

    session_manager = get_session_manager()
    memory_manager = get_memory_manager()
    agent = get_react_agent()

    # 获取或创建会话
    session_id = request.get("session_id")
    if session_id:
        existing_state = await session_manager.get_state(session_id)
        if not existing_state:
            raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")
    else:
        session_id = await session_manager.create(agent_id=agent.agent_id)
        # 将 user query 加入会话
        user_message = Message(role=Role.USER, content=query)
        await session_manager.add_message(session_id, user_message)

    # 获取会话历史
    messages = await session_manager.get_history(session_id, limit=30)

    # 查询相关记忆
    memories = await memory_manager.search(query, top_k=3)

    # 构建 Agent 输入和上下文
    agent_input = AgentInput(
        query=query,
        session_id=session_id,
        user_id=request.get("user_id"),
    )
    context = AgentContext(
        session_id=session_id,
        user_id=request.get("user_id"),
        messages=messages,
        memories=memories,
    )

    # 执行 Agent
    output = await agent.invoke(agent_input, context)

    # 更新会话
    assistant_message = Message(role=Role.ASSISTANT, content=output.answer)
    await session_manager.add_message(session_id, assistant_message)

    # 写入情景记忆
    await memory_manager.summarize_episode(
        session_id, messages + [assistant_message], importance=0.6
    )

    return output


@router.websocket("/stream")
async def stream_agent(websocket: WebSocket) -> None:
    """
    WebSocket 流式执行 Agent

    客户端发送 JSON:
    ```json
    {"query": "...", "session_id": "optional"}
    ```

    服务端逐步推送事件:
    ```json
    {"event_type": "thinking", "data": {"thought": "..."}}
    {"event_type": "tool_call", "data": {"name": "...", "args": {...}}}
    {"event_type": "tool_result", "data": {"name": "...", "result": "..."}}
    {"event_type": "answer", "data": {"answer": "..."}}
    {"event_type": "error", "data": {"message": "..."}}
    ```
    """
    await websocket.accept()
    logger.info("WebSocket connection accepted")

    session_manager = get_session_manager()
    memory_manager = get_memory_manager()
    agent = get_react_agent()

    try:
        # 接收请求
        raw = await websocket.receive_json()
        query = raw.get("query", "")
        if not query:
            await websocket.send_json({"event_type": "error", "data": {"message": "query is required"}})
            await websocket.close()
            return

        # 获取或创建会话
        session_id = raw.get("session_id")
        if session_id:
            existing_state = await session_manager.get_state(session_id)
            if not existing_state:
                await websocket.send_json({"event_type": "error", "data": {"message": f"Session not found: {session_id}"}})
                await websocket.close()
                return
        else:
            session_id = await session_manager.create(agent_id=agent.agent_id)
            user_message = Message(role=Role.USER, content=query)
            await session_manager.add_message(session_id, user_message)

        # 构建上下文
        messages = await session_manager.get_history(session_id, limit=30)
        memories = await memory_manager.search(query, top_k=3)

        agent_input = AgentInput(
            query=query,
            session_id=session_id,
            user_id=raw.get("user_id"),
        )
        context = AgentContext(
            session_id=session_id,
            user_id=raw.get("user_id"),
            messages=messages,
            memories=memories,
        )

        # 流式执行
        full_answer = ""
        async for event in agent.stream(agent_input, context):
            await websocket.send_json(event.model_dump())
            if event.event_type == "answer":
                full_answer = event.data.get("answer", "")

        # 记录会话
        if full_answer:
            assistant_message = Message(role=Role.ASSISTANT, content=full_answer)
            await session_manager.add_message(session_id, assistant_message)

        await websocket.close()

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        try:
            await websocket.send_json({"event_type": "error", "data": {"message": str(e)}})
            await websocket.close()
        except Exception:
            pass
