# REQ-20260827-001：Codex 迁移基线

- 状态：已完成
- 提出日期：2026-08-27
- 负责人：项目维护者与 Codex

## 背景与目标

项目最初使用 Claude Code 开发，现迁移到 Codex，并计划在多台电脑上持续学习和开发。需要把工作区中尚未提交的学习实现整理为可验证、可同步的 Git 基线，同时建立适用于 Codex 的协作说明和变更记录机制。

## 原始需求

- 熟悉现有 Agent 学习项目及其 Claude Code 迁移背景。
- 整理当前未提交的代码和文档。
- 修复本机开发环境并验证项目。
- 文档更新后及时同步到 GitHub `main`。
- 后续为每次变更保留需求记录。
- 不修改由用户手工维护的 `docs/README-cyl.md`。

## 范围

- 工具、技能、权限、记忆、上下文、RAG、多循环、审批、通知、安全、MCP、可观测性、长任务和 CLI 的现有实现。
- API 与 ReAct 图的服务集成。
- 相关单元测试和集成测试。
- README、架构、开发、API 与 Codex 协作说明同步。
- Python/uv 环境恢复、锁文件更新、代码格式和静态检查修复。
- 需求、变更和事实文档体系。

## 非目标

- 不使用真实模型 API Key 运行在线模型测试。
- 不部署服务到生产环境。
- 不把 `.claude/settings.local.json` 等机器专属配置纳入共享提交。
- 不修改 `docs/README-cyl.md`。

## 验收标准

- 全量离线测试通过。
- Ruff 静态检查和格式检查通过。
- API 服务与 CLI 帮助入口可以启动。
- 仓库中不存在常见格式的明文密钥。
- 文档反映当前实现状态。
- 新增 `AGENTS.md`、需求记录、变更日志和项目事实文档。
- 经用户确认后提交并推送到 GitHub `main`。

## 设计与实现摘要

- 恢复 uv 环境并使用 Python 3.12 安装锁定依赖。
- 集成迁移前工作区中的 Phase 2–5 学习实现。
- 使用 Ruff 安全修复及人工修复清理代码质量问题，其中包括工具超时回调的闭包变量绑定问题。
- 更新项目阶段、API 端点、测试基线及开发命令。
- 新增项目级 Codex 说明及文档治理规则。

## 主要修改区域

- `src/agent_labs/`：Agent 核心、服务集成和新增学习模块。
- `src/agent_labs/tests/`：单元测试与集成测试。
- `README.md`、`TODO.md`、`docs/`：项目状态和使用文档。
- `AGENTS.md`、`CLAUDE.md`：编码 Agent 协作说明。
- `pyproject.toml`、`uv.lock`：开发依赖与锁文件。

## 验证结果

- `pytest`：250 passed，1 skipped。
- `ruff check src/`：通过。
- `ruff format --check src/`：通过。
- `python -m agent_labs --help`：通过。
- `python -m agent_labs chat --help`：通过。
- 常见密钥格式扫描：未发现匹配项。

## 风险与后续事项

- 当前实现属于生产级概念的学习实现，尚未经过真实生产负载验证。
- FastAPI 测试存在一项来自依赖包的弃用警告，后续升级依赖时处理。
- 在线模型、邮件、MCP 外部服务与 Docker 沙箱仍需在具备相应环境时做端到端验证。

## Git 提交

本文随 Codex 迁移基线提交一并合入，具体提交哈希以 Git 历史为准。
