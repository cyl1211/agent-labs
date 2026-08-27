# 项目事实

本文件只记录稳定、可验证且会影响协作判断的事实。需求和计划写入 `docs/requirements/` 与 `TODO.md`，设计解释写入 `docs/architecture.md`，不要在这里记录推测或临时状态。

## 项目定位

- 项目名称：Agent-Labs。
- 用途：学习现代 Agent 系统概念与工程实践，并尽量贴近生产级设计。
- 代码仓库：`https://github.com/cyl1211/agent-labs.git`。
- 默认共享分支：`main`。
- 开发者会在多台 Windows/Linux 电脑上使用该仓库。

## 技术基线

- Python：>= 3.11。
- 环境与依赖管理：uv。
- Agent 框架：LangGraph。
- API 框架：FastAPI。
- 模型提供商适配：Anthropic、OpenAI。
- 测试目录：`src/agent_labs/tests/`。
- 配置目录：`config/`。

## 架构约束

- Agent、Session、Memory 必须解耦。
- 核心抽象接口为 `BaseAgent`、`BaseSession`、`BaseMemory`。
- 配置驱动模型、工具、安全、上下文、记忆和可观测性行为。
- 代码需要兼容 Windows 与 Linux。

## 文档所有权

- `docs/README-cyl.md`：由用户手工维护；Codex 未经用户明确要求不得修改。
- `docs/requirements/`：每次实质变更的需求与验收记录。
- `CHANGELOG.md`：重要变化的简要索引。
- `TODO.md`：阶段任务和后续工作。
- `AGENTS.md`：Codex 在本仓库中的协作约定。

## 当前已验证基线

- 验证日期：2026-08-27。
- Python：3.12。
- 测试：250 passed，1 skipped。
- Ruff 静态检查：通过。
- Ruff 格式检查：通过。
- API 和 CLI 帮助入口：通过。

## 事实维护规则

- 只写可由代码、配置、测试或用户明确声明验证的内容。
- 事实变化时，在同一变更中更新本文件和对应需求记录。
- 不保存密钥、账号、个人隐私、本机绝对路径或短期运行状态。
