# Agent-Labs 架构设计

## 三层解耦

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

- **Agent**: 只负责"如何执行任务"——调用 LLM、规划步骤、使用工具。不管理状态。
- **Session**: 只负责"存储运行时状态"——消息历史、迭代次数、检查点。不涉及长期知识。
- **Memory**: 只负责"存储长期知识"——跨会话的事实、用户偏好、成功模式。

## 核心接口

```python
# Agent — 通过 AgentContext 获取只读视图
class BaseAgent(ABC):
    async def invoke(input: AgentInput, context: AgentContext) -> AgentOutput
    async def stream(input: AgentInput, context: AgentContext) -> AsyncIterator[AgentEvent]

# Session — 独立于 Agent 实现
class BaseSession(ABC):
    async def create(agent_id: str) -> str
    async def get_state(session_id: str) -> SessionState
    async def add_message(session_id: str, message: Message)
    async def get_history(session_id: str, limit: int) -> list[Message]

# Memory — 四层架构
class BaseMemory(ABC):
    async def write(entry: MemoryEntry) -> str
    async def search(query: str, top_k: int) -> list[MemoryEntry]
    async def collect_garbage() -> int
```

## LangGraph 图

11 个节点，3 种边类型：

```
[input] → [context] → [decide]
                         ├── tool_call → [tool] → [memory] → [loop] → decide
                         ├── answer → [output] → [notify] → END
                         ├── human_approval → [human] → loop → decide
                         └── error → [error] → loop/END
```

### 路由逻辑

| 路由函数 | 判断条件 |
|----------|----------|
| `_route_after_decide` | LLM 输出的 next_action: tool_call / answer / error |
| `_route_after_tool` | 工具执行完后返回 decide 继续推理 |
| `_route_after_loop` | should_continue 标志 + iteration 计数 |
| `_route_after_error` | 是否超过 max_iterations，可重试则回 loop |

### 终止条件

1. LLM 输出包含 `TASK_COMPLETE` 或 `FINAL_ANSWER`
2. 达到 `max_iterations`（默认 25）
3. 图递归深度超限（LangGraph `recursion_limit`）
4. 手动中断

## 三种 Agent 循环模式

| 模式 | 流程 | 适用场景 | 实现状态 |
|------|------|----------|----------|
| **ReAct** | decide ⇄ tool → output | 通用任务、需要工具的场景 | ✅ Phase 1 |
| **Plan-Execute** | plan → [step1, step2, ...] → review | 复杂多步任务 | 🔜 Phase 4 |
| **Supervisor** | supervisor ⇄ [worker_a, worker_b, ...] | 多 Agent 协作 | 🔜 Phase 4 |

## 数据流

```
HTTP Request
  → FastAPI Route
    → SessionManager.get_or_create()
    → MemoryManager.search(query)
    → AgentContext(session_id, messages, memories)
    → ReactAgent.invoke(input, context)
      → LangGraph 图执行 (11 节点循环)
    → SessionManager.update_state()
    → MemoryManager.summarize_episode()
    → AgentOutput → HTTP Response
```

## 模型选择策略

```yaml
# config/models.yaml
selection:
  orchestrator_tier: strong    # Claude Opus/Sonnet, GPT-4o
  worker_tier: weak            # Claude Haiku, GPT-4o-mini
  tool_calling_tier: strong    # 结构输出需要强模型
```

## 跨平台设计

| 风险点 | 解决方案 |
|--------|----------|
| asyncio 事件循环 | Windows: `SelectorEventLoopPolicy`；Linux: 默认 |
| 文件路径 | 统一 `pathlib.Path` |
| 文件编码 | 显式 `encoding="utf-8"` |
| 子进程 | `asyncio.create_subprocess_exec` + `shutil.which()` |
| 沙箱 | 默认进程隔离，Docker 可选 |
