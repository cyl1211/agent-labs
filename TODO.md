# Agent-Labs 待办清单

## 🔴 P0 — 让 Agent 真正"能用"（优先实现）

### #1 实现内置工具
- **文件**: `src/agent_labs/tools/builtin/`
- **内容**: 实现 4 个内置工具：
  - `read_file` — 读取文件内容
  - `write_file` — 写入文件（需审批）
  - `web_search` — 网络搜索
  - `execute_command` — 执行系统命令（需沙箱）
- **依赖**: 无
- **状态**: ⬜ 待开始

### #2 实现技能系统
- **文件**: `src/agent_labs/skills/`
- **内容**:
  - `base.py` — BaseSkill 抽象类
  - `registry.py` — SkillRegistry 注册表
  - `selector.py` — SkillSelector 选择逻辑
  - `executor.py` — SkillExecutor 执行器
- **示例技能**: "代码分析" = read_file + web_search 组合
- **依赖**: #1（需要工具可用）
- **状态**: ⬜ 待开始

### #3 实现工具/技能权限管理
- **文件**: `src/agent_labs/tools/permissions.py`, `src/agent_labs/skills/permissions.py`
- **内容**: 基于 `config/tools.yaml` 的 permission_level (read/write/execute) 做访问控制，与用户角色关联
- **依赖**: #1, #2
- **状态**: ⬜ 待开始

---

## 🟡 P1 — 让 Agent 有"记忆"和"知识"（下一步）

### #4 实现上下文工程
- **文件**: `src/agent_labs/context/`
- **内容**:
  - `builder.py` — 从 session+memory 构建上下文
  - `compressor.py` — 超长对话自动摘要压缩
  - `knowledge.py` — 动态知识注入
- **核心难点**: token 预算管理
- **依赖**: 无（可独立实现）
- **状态**: ⬜ 待开始

### #5 拆分四层记忆到独立文件
- **文件**: `src/agent_labs/memory/layers/`
- **内容**:
  - `working.py` — 工作记忆
  - `episodic.py` — 情景记忆
  - `semantic.py` — 语义记忆
  - `procedural.py` — 程序记忆
- **依赖**: 无（重构现有代码）
- **状态**: ⬜ 待开始

### #6 实现 RAG 系统
- **文件**: `src/agent_labs/rag/`
- **内容**:
  - `indexing.py` — 文档索引
  - `retrieval.py` — 向量检索
  - `pipeline.py` — 检索增强生成管道
- **依赖**: #5（需与 semantic 记忆层整合）
- **状态**: ⬜ 待开始

---

## 🟢 P2 — 锦上添花（基础扎实后）

### #7 实现其他循环模式
- **文件**: `src/agent_labs/loops/`
- **内容**: Plan-Execute 循环、Supervisor 循环
- **状态**: ⬜ 待开始

### #8 实现可观测性
- **文件**: `src/agent_labs/observability/`
- **内容**: 完整 tracing、token 监控仪表板
- **状态**: ⬜ 待开始

### #9 实现通知机制
- **文件**: `src/agent_labs/notifications/`
- **内容**: 邮件通知（关键节点、错误、完成）
- **状态**: ⬜ 待开始

### #10 实现人工确认
- **文件**: `src/agent_labs/human_loop/`
- **内容**: LangGraph interrupt 机制 + 审批工作流
- **状态**: ⬜ 待开始

### #11 实现安全沙箱
- **文件**: `src/agent_labs/security/`
- **内容**: Docker 沙箱、超时管理
- **状态**: ⬜ 待开始

### #12 实现长任务支持
- **文件**: `src/agent_labs/long_running/`
- **内容**: 任务分解器、检查点持久化
- **状态**: ⬜ 待开始

### #13 实现 MCP 接入
- **文件**: `src/agent_labs/mcp/`
- **内容**: MCP 服务器管理、动态加载
- **状态**: ⬜ 待开始

---

## 环境信息

- **外部中间件**: 无需搭建（零依赖）
- **包管理**: uv（`uv sync` 安装依赖）
- **Python**: 3.11（`.python-version` 锁定）
