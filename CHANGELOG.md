# Changelog

本文件记录面向使用者和项目维护者的重要变化。详细需求、验收标准与验证结果参见 `docs/requirements/`。

## Unreleased

### Added

- 工具、技能及权限管理系统。
- 四层记忆、上下文工程和 RAG。
- Plan-Execute 与 Supervisor 学习实现。
- 人工审批、通知、安全沙箱和多级超时。
- MCP 管理、可观测性和长任务检查点。
- CLI 交互聊天模式及扩展 API。
- Codex 项目说明、逐次需求记录和项目事实文档。

### Changed

- ReAct 图接入上下文、记忆、技能、审批、可观测性和通知服务。
- 文档同步到当前实现状态。
- uv 开发依赖配置迁移到 `dependency-groups`。
- 代码通过 Ruff 清理和格式化。

### Validation

- 250 passed，1 skipped。
- Ruff 检查和格式检查通过。
