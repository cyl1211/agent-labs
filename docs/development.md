# 开发指南

## 环境管理 (uv)

```bash
# 安装 uv（如未安装）
pip install uv

# 创建虚拟环境并同步依赖
uv sync

# 激活虚拟环境
# Windows:
.venv\Scripts\activate
# Linux:
source .venv/bin/activate

# 添加新依赖
uv add <package>
uv add --dev <dev-package>

# 更新依赖
uv sync --upgrade
```

## 常用命令

```bash
# 启动服务
python -m agent_labs
python -m agent_labs --port 8080 --log-level DEBUG

# 开发模式（热重载）
python -m agent_labs --reload

# 运行测试
pytest src/agent_labs/tests/ -v

# 覆盖率
coverage run -m pytest src/agent_labs/tests/
coverage report

# 代码检查
ruff check src/
ruff format src/

# 类型检查
mypy src/
```

## 环境变量

| 变量 | 用途 | 必需 |
|------|------|------|
| `ANTHROPIC_API_KEY` | Claude API 密钥 | 是（使用 Anthropic 时） |
| `OPENAI_API_KEY` | OpenAI API 密钥 | 否 |
| `SMTP_PASSWORD` | 邮件通知密码 | 否 |
| `AGENT_LABS_ENV` | 环境标识 (development/production) | 否 |

## 项目结构

```
agent-labs/
├── CLAUDE.md                 # AI 助手指南（精简版）
├── README.md                 # 项目说明
├── pyproject.toml            # 项目配置 & 依赖
├── uv.lock                   # 依赖锁定
├── .python-version           # Python 版本 (3.11)
├── config/                   # YAML 配置
│   ├── default.yaml          #   全局设置
│   ├── models.yaml           #   模型/提供商
│   └── tools.yaml            #   工具注册
├── docs/                     # 详细文档
│   ├── architecture.md       #   架构设计
│   ├── development.md        #   本文件
│   └── api.md                #   API 参考
└── src/agent_labs/
    ├── main.py               # 入口
    ├── core/                 # 抽象层 (Agent/Session/Memory)
    ├── agents/               # Agent 实现 (ReAct, ...)
    ├── models/               # 模型管理 (Anthropic, OpenAI, ...)
    ├── tools/                # 工具系统 (Registry, Executor)
    ├── sessions/             # 会话管理
    ├── memory/               # 四层记忆
    ├── graph/                # LangGraph (State, Nodes, Builder)
    ├── api/                  # FastAPI (Routes, Middleware)
    └── tests/                # 测试
```

## 开发阶段

| 阶段 | 内容 | 状态 |
|------|------|------|
| Phase 1 | 项目基础 + 单 Agent 核心 + FastAPI | ✅ 完成 |
| Phase 2 | 工具 + 技能 + 权限系统 | 🔜 待开始 |
| Phase 3 | 记忆系统 + 上下文工程 + RAG | 📋 计划中 |
| Phase 4 | 多 Agent + Human-in-the-Loop + 通知 | 📋 计划中 |
| Phase 5 | MCP + 可观测性 + 长任务 | 📋 计划中 |
| Phase 6 | 安全 + 测试 + 生产加固 | 📋 计划中 |

## 测试策略

```bash
# 单元测试
pytest src/agent_labs/tests/unit/ -v

# 集成测试（需要 LLM API key）
pytest src/agent_labs/tests/integration/ -v

# 全部测试
pytest src/agent_labs/tests/ -v
```

## 添加新 Agent 模式

1. 继承 `BaseAgent`
2. 实现 `invoke()` 和 `stream()`
3. 在 `agents/` 下创建文件
4. 在 `api/deps.py` 注册

```python
from agent_labs.core.base_agent import BaseAgent

class MyAgent(BaseAgent):
    async def invoke(self, input, context):
        # 自定义逻辑
        ...
```

## 添加新工具

1. 继承 `BaseTool`，实现 `execute()`
2. 在 `tools/registry.py` 注册
3. 在 `config/tools.yaml` 配置权限
