# Agent-Labs

基于 **LangGraph + FastAPI** 的生产级 Agent 学习项目，涵盖现代 Agent 系统的核心技术概念和工程实践。

## 技术栈

| 类别 | 技术 |
|------|------|
| 平台 | Linux / Windows |
| 语言 | Python >= 3.11 |
| Agent 框架 | LangGraph |
| API 框架 | FastAPI |
| 环境管理 | [uv](https://github.com/astral-sh/uv) |
| 模型支持 | Anthropic Claude, OpenAI |

## 快速开始

```bash
# 1. 安装 uv
pip install uv

# 2. 克隆并同步依赖
git clone https://github.com/cyl1211/agent-labs.git
cd agent-labs
uv sync

# 3. 设置 API Key
export ANTHROPIC_API_KEY="your-api-key"

# 4. 启动服务
python -m agent_labs --reload

# 5. 访问 API 文档
# http://localhost:8000/docs
```

## 项目结构

```
agent-labs/
├── config/              # YAML 配置 (模型、工具、权限)
├── docs/                # 详细文档
│   ├── architecture.md  #   架构设计
│   ├── development.md   #   开发指南
│   └── api.md           #   API 参考
└── src/agent_labs/
    ├── core/            # 抽象接口层 (Agent/Session/Memory 解耦)
    ├── agents/          # Agent 实现 (ReAct)
    ├── models/          # 多平台模型管理
    ├── tools/           # 工具系统 (注册、执行、重试、超时)
    ├── sessions/        # 会话状态管理
    ├── memory/          # 四层记忆架构
    ├── graph/           # LangGraph 图 (State, Nodes, Builder)
    ├── api/             # FastAPI 路由与中间件
    └── tests/           # 单元测试 & 集成测试
```

## 核心特性

- **三层解耦**: Agent / Session / Memory 通过抽象接口独立，可接入其他 Agent 系统
- **多模型管理**: 统一的模型管理器，支持 strong/weak 分层策略
- **工具系统**: 工具注册、执行重试、超时控制、批量并行
- **四层记忆**: Working / Episodic / Semantic / Procedural
- **LangGraph 循环**: ReAct 模式，11 个节点，条件路由
- **跨平台**: Windows / Linux 双平台支持

## 开发阶段

| 阶段 | 内容 | 状态 |
|------|------|------|
| Phase 1 | 项目基础 + 单 Agent 核心 | ✅ |
| Phase 2 | 工具 + 技能 + 权限系统 | 🔜 |
| Phase 3 | 记忆系统 + 上下文工程 + RAG | 📋 |
| Phase 4 | 多 Agent + Human-in-the-Loop + 通知 | 📋 |
| Phase 5 | MCP + 可观测性 + 长任务 | 📋 |
| Phase 6 | 安全 + 测试 + 生产加固 | 📋 |

## 文档

- [架构设计](docs/architecture.md) — 三层解耦、LangGraph 图、数据流
- [开发指南](docs/development.md) — uv 使用、环境变量、添加新模块
- [API 参考](docs/api.md) — 所有端点、请求/响应示例

## 测试

```bash
pytest src/agent_labs/tests/ -v
```
