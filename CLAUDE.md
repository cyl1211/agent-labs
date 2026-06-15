# CLAUDE.md — Agent-Labs 项目指南

## 项目概述

Agent-Labs 是一个基于 **LangGraph + FastAPI** 的生产级 Agent 学习项目，涵盖 Agent 系统的最新概念和工程实践。

- **语言**: Python >= 3.11
- **框架**: LangGraph (Agent 编排), FastAPI (API 服务)
- **平台**: Windows / Linux 双平台支持

---

## 目录结构

```
agent-labs/
├── CLAUDE.md                  # 本文件
├── README.md                  # 项目需求文档
├── pyproject.toml             # 项目配置与依赖
├── config/
│   ├── default.yaml           # 全局默认配置
│   ├── models.yaml            # 模型/提供商配置
│   └── tools.yaml             # 工具注册与权限
└── src/agent_labs/
    ├── main.py                # 入口 (uvicorn)
    ├── core/                  # 核心抽象层 ★
    │   ├── base_agent.py      #   Agent 抽象接口
    │   ├── base_session.py    #   Session 抽象接口
    │   ├── base_memory.py     #   Memory 抽象接口
    │   └── types.py           #   共享类型 (Message, AgentInput/Output, MemoryEntry 等)
    ├── config/                # 配置管理
    │   └── settings.py        #   pydantic 数据类 + YAML 加载
    ├── agents/                # Agent 实现
    │   └── react_agent.py     #   ReAct Agent (Phase 1 主要实现)
    ├── models/                # 模型管理
    │   ├── manager.py         #   多平台模型管理器
    │   └── providers/         #   模型提供商适配
    ├── tools/                 # 工具系统
    │   ├── base.py            #   工具基类
    │   ├── registry.py        #   工具注册表
    │   └── executor.py        #   工具执行器 (重试/超时)
    ├── sessions/              # 会话管理
    │   └── manager.py         #   会话状态管理
    ├── memory/                # 记忆系统
    │   └── manager.py         #   四层记忆管理
    ├── graph/                 # LangGraph 图
    │   ├── state.py           #   图状态定义
    │   ├── nodes.py           #   11 个核心节点
    │   └── builder.py         #   图构建工厂
    └── api/                   # FastAPI
        ├── app.py             #   应用工厂
        ├── deps.py            #   依赖注入
        ├── routes/            #   路由 (agents, sessions, tools)
        └── middleware/        #   中间件 (logging)
```

---

## 核心设计原则

### 1. 三层解耦架构

```
┌─────────┐     ┌────────────┐     ┌──────────┐
│  Agent  │────→│AgentContext│←────│ Session  │
│ (执行)  │     │ (只读视图)  │     │ (状态)   │
└─────────┘     └────────────┘     └──────────┘
                      ↑
                 ┌──────────┐
                 │  Memory  │
                 │ (知识)   │
                 └──────────┘
```

- **Agent**: 只负责"如何执行任务"，不管理状态
- **Session**: 只负责"存储运行时状态"（消息历史、迭代次数）
- **Memory**: 只负责"存储长期知识"（跨会话的事实、经验）
- **AgentContext**: Agent 只看到 context 的只读视图，不直接依赖 Session/Memory 实现

### 2. 接口抽象

所有核心组件通过抽象基类定义接口：
- `BaseAgent.invoke(input, context) → output`
- `BaseSession.create/get_state/update_state/get_history/close`
- `BaseMemory.write/read/search/collect_garbage`

任何外部 Agent 系统只需实现这些接口即可接入。

### 3. 配置驱动

所有行为通过 YAML 配置控制：
- `default.yaml` → 通用设置（超时、循环次数、上下文大小）
- `models.yaml` → 模型定义、提供商、层级策略
- `tools.yaml` → 工具注册、权限级别

---

## 数据流

```
HTTP Request
  → FastAPI Route (agents.py)
    → SessionManager.get_or_create()
    → MemoryManager.search(query) → memories
    → AgentContext(session_id, messages, memories)
    → ReactAgent.invoke(input, context)
      → LangGraph Graph Execution
        → input_node → context_node → decide_node
        → tool_node → memory_node → loop_node
        → output_node → notify_node
    → SessionManager.update_state()
    → AgentOutput → HTTP Response
```

---

## 关键命令

```bash
# 安装依赖
pip install -e ".[dev]"

# 启动服务
python -m agent_labs
# 或指定端口
python -m agent_labs --port 8080 --log-level DEBUG

# 开发模式 (热重载)
python -m agent_labs --reload

# 运行测试
pytest src/agent_labs/tests/

# 代码检查
ruff check src/
ruff format src/

# API 文档
# 启动后访问 http://localhost:8000/docs
```

---

## API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/health` | 健康检查 |
| POST | `/api/v1/agents/invoke` | 同步执行 Agent |
| WS | `/api/v1/agents/stream` | 流式执行 Agent |
| GET | `/api/v1/sessions` | 列出会话 |
| POST | `/api/v1/sessions` | 创建会话 |
| GET | `/api/v1/sessions/{id}` | 获取会话状态 |
| GET | `/api/v1/sessions/{id}/history` | 获取消息历史 |
| GET | `/api/v1/tools` | 列出所有工具 |

---

## 开发阶段

### Phase 1 (当前) — 项目基础 + 单 Agent
- ✅ 项目结构与依赖
- ✅ 核心抽象 (Agent/Session/Memory)
- ✅ 模型管理 (Anthropic + OpenAI)
- ✅ LangGraph ReAct 循环
- ✅ FastAPI 服务
- ⬜ 测试编写

### Phase 2 — 工具 + 技能 + 权限
### Phase 3 — 记忆系统 + 上下文工程 + RAG
### Phase 4 — 多 Agent + Human-in-the-Loop + 通知
### Phase 5 — MCP + 可观测性 + 长任务
### Phase 6 — 安全 + 测试 + 生产加固

---

## 跨平台注意事项

1. **asyncio**: Windows 使用 `WindowsSelectorEventLoopPolicy`
2. **路径**: 统一使用 `pathlib.Path`
3. **编码**: 所有文件操作显式指定 `encoding="utf-8"`
4. **子进程**: 使用 `spawn` 上下文，`shutil.which()` 查找可执行文件
5. **沙箱**: 默认进程隔离，Docker 为可选后端
