# CLAUDE.md — Agent-Labs

基于 LangGraph + FastAPI 的 Agent 学习项目。Python>=3.11, uv 管理环境。

## 核心原则
- **Agent/Session/Memory 三层解耦**，通过抽象接口 `BaseAgent/BaseSession/BaseMemory` 隔离
- **配置驱动**: YAML 配置文件在 `config/`
- **跨平台**: Windows/Linux 双支持 (asyncio 策略自动适配)

## 常用命令
```bash
uv sync                    # 安装依赖
python -m agent_labs       # 启动服务
pytest src/agent_labs/tests/ -v  # 测试
ruff check src/ && ruff format src/  # 代码检查
```

## 详细文档
- 架构设计 → `docs/architecture.md`
- 开发指南 → `docs/development.md`
- API 参考 → `docs/api.md`
- 项目需求 → `README.md`
