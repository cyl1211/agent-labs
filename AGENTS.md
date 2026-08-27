# AGENTS.md — Agent-Labs

本仓库是基于 LangGraph + FastAPI 的 Agent 工程学习项目，目标是在便于学习的同时尽量贴近生产实践。

## 项目约定

- Python >= 3.11，使用 `uv` 管理环境与锁文件。
- 保持 Agent、Session、Memory 三层解耦，通过 `BaseAgent`、`BaseSession`、`BaseMemory` 抽象接口协作。
- 配置集中在 `config/`，不要把 API Key、密码或机器专属路径写入仓库。
- 同时支持 Windows 与 Linux；路径使用 `pathlib.Path`，文件显式使用 UTF-8。
- 修改应聚焦当前任务，不回退或覆盖工作区中不相关的已有改动。

## 验证命令

```bash
uv sync
uv run pytest src/agent_labs/tests/ -q
uv run ruff check src/
uv run ruff format --check src/
```

涉及运行入口时，同时验证：

```bash
uv run python -m agent_labs --help
uv run python -m agent_labs chat --help
```

## 文档与 Git 协作

- 实现变化后同步更新 `README.md`、`TODO.md` 和 `docs/` 中相关说明。
- 每项实质变更在 `docs/requirements/` 建立或更新需求记录，并同步维护 `CHANGELOG.md`。
- 稳定且可验证的项目事实维护在 `docs/facts.md`，不要混入计划、推测或临时状态。
- `docs/README-cyl.md` 由用户手工维护，未经用户明确要求不得修改。
- 用户会在多台电脑上学习本项目；经验证的文档更新应及时提交并推送到 GitHub `main`。
- 推送前检查 `git status` 和暂存区，排除 `.env`、密钥、本机虚拟环境及机器专属设置。
- `.claude/settings.local.json` 属于本机 Claude Code 配置，默认不纳入功能提交。

## 架构入口

- 总体架构：`docs/architecture.md`
- 开发方式：`docs/development.md`
- API：`docs/api.md`
- 阶段与任务：`TODO.md`
- 项目事实：`docs/facts.md`
- 逐次需求：`docs/requirements/`
- 变更索引：`CHANGELOG.md`
- 应用入口：`src/agent_labs/main.py`
- ReAct 图：`src/agent_labs/graph/`
- 服务装配：`src/agent_labs/api/deps.py`
