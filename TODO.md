# Agent-Labs 待办清单

## 🔴 P0 — 让 Agent 真正"能用"（✅ 全部完成 2025-06-18）

### #1 实现内置工具 ✅ 已完成 (2025-06-18)
- **文件**: `src/agent_labs/tools/builtin/`
- **内容**: 实现 4 个内置工具：
  - `read_file` — 读取文件内容（自动编码检测、行数限制、10MB 上限）
  - `write_file` — 写入文件（需审批、系统目录安全保护、自动创建父目录）
  - `web_search` — 网络搜索（DuckDuckGo + Google 后备、HTML 解析）
  - `execute_command` — 执行系统命令（需沙箱、危险命令黑名单、超时控制）
- **测试**: `tests/unit/test_tools/test_builtin_tools.py` (17 个测试)
- **依赖**: 无
- **状态**: ✅ 已完成

### #2 实现技能系统 ✅ 已完成 (2025-06-18)
- **文件**: `src/agent_labs/skills/`
- **内容**:
  - `base.py` — BaseSkill 抽象类（name/description/triggers/required_tools/execute）
  - `registry.py` — SkillRegistry 注册表（find_matching 关键词匹配）
  - `selector.py` — SkillSelector 选择逻辑（精确名→关键词→无匹配 三级策略）
  - `executor.py` — SkillExecutor 执行器（execute/execute_by_query/execute_sequential）
- **示例技能**: `skills/builtin/code_analysis.py` — "代码分析" = read_file + web_search 组合
- **测试**: `tests/unit/test_skills/test_skills.py` (18 个测试)
- **依赖**: #1
- **状态**: ✅ 已完成

### #3 实现工具/技能权限管理 ✅ 已完成 (2025-06-18)
- **文件**: `src/agent_labs/tools/permissions.py`, `src/agent_labs/skills/permissions.py`
- **内容**: 基于 `config/tools.yaml` 的 permission_level (read/write/execute) 做访问控制，与用户角色 (admin/editor/viewer) 关联
  - `ToolPermissionManager` — 工具权限加载、检查、审批判断、沙箱判断
  - `SkillPermissionManager` — 技能权限自动推断（=max(所需工具权限)）、继承审批需求
  - `ToolExecutor` 集成 `set_permission_manager()` 和 `get_accessible_tools()`
- **测试**: `tests/unit/test_tools/test_permissions.py` (22 个测试)
- **依赖**: #1, #2
- **状态**: ✅ 已完成

---

## 🟡 P1 — 让 Agent 有"记忆"和"知识"（✅ 全部完成 2025-06-18）

### #4 实现上下文工程 ✅ 已完成 (2025-06-18)
- **文件**: `src/agent_labs/context/`
- **内容**:
  - `builder.py` — ContextBuilder: 从 session+memory 构建上下文，token 预算管理、多来源整合
  - `compressor.py` — ContextCompressor: 超长对话自动摘要压缩，滑动窗口+关键消息保留策略
  - `knowledge.py` — KnowledgeInjector: 动态知识注入（语义/程序/情景记忆多源检索）
- **核心能力**: token 预算管理、消息截断、知识注入
- **测试**: `tests/unit/test_context/test_context.py` (16 个测试)
- **依赖**: 无（可独立实现）
- **状态**: ✅ 已完成

### #5 拆分四层记忆到独立文件 ✅ 已完成 (2025-06-18)
- **文件**: `src/agent_labs/memory/layers/`
- **内容**:
  - `working.py` — WorkingMemory: FIFO 容量队列、快速读写、会话级
  - `episodic.py` — EpisodicMemory: 按会话分组、时间衰减、摘要生成
  - `semantic.py` — SemanticMemory: 冲突检测（Jaccard相似度）、去重合并、事实排序
  - `procedural.py` — ProceduralMemory: 模式分类（reasoning/tool_chain/response/workflow）、强化/弱化学习
- **重构**: MemoryManager 委托到四层独立实现，向后兼容 BaseMemory 接口
- **测试**: `tests/unit/test_memory/test_layers.py` (22 个测试)
- **依赖**: 无（重构现有代码）
- **状态**: ✅ 已完成

### #6 实现 RAG 系统 ✅ 已完成 (2025-06-18)
- **文件**: `src/agent_labs/rag/`
- **内容**:
  - `indexing.py` — DocumentIndexer: 多策略分块（固定/段落/句子）、倒排索引、文档元数据
  - `retrieval.py` — VectorRetriever: 多策略检索（关键词/TF-IDF/语义/混合）、余弦相似度、结果融合
  - `pipeline.py` — RAGPipeline: 端到端流程（查询→多源检索→去重排序→上下文构建）
- **整合**: 与 semantic 记忆层、程序记忆层深度整合
- **测试**: `tests/unit/test_rag/test_rag.py` (16 个测试)
- **依赖**: #5（需与 semantic 记忆层整合）
- **状态**: ✅ 已完成

---

## 🟢 P2 — 锦上添花（✅ 全部完成 2025-06-18）

### #7 实现其他循环模式 ✅ 已完成 (2025-06-18)
- **文件**: `src/agent_labs/loops/`
- **内容**:
  - `plan_execute.py` — PlanExecutor + Plan/PlanStep/StepStatus: 计划制定、步骤依赖管理、进度追踪、自动修订
  - `supervisor.py` — Supervisor + Worker/Task/SupervisorState: 多Agent协调、能力匹配分配、任务完成追踪
- **测试**: `tests/unit/test_loops/test_loops.py` (16 个测试)
- **状态**: ✅ 已完成

### #8 实现可观测性 ✅ 已完成 (2025-06-18)
- **文件**: `src/agent_labs/observability/`
- **内容**:
  - `tracer.py` — Tracer/Trace/TraceSpan: 节点级span追踪、输入/输出/耗时/token记录
  - `monitor.py` — TokenMonitor/TokenUsage/NodeStats: 全局+会话级统计、预算预警、文本仪表板
- **测试**: `tests/unit/test_observability/test_observability.py` (16 个测试)
- **状态**: ✅ 已完成

### #9 实现通知机制 ✅ 已完成 (2025-06-18)
- **文件**: `src/agent_labs/notifications/`
- **内容**:
  - `email.py` — EmailNotifier/EmailConfig: SMTP邮件通知、HTML+纯文本双格式、通知级别过滤、send_error/completion/warning快捷方法
- **状态**: ✅ 已完成

### #10 实现人工确认 ✅ 已完成 (2025-06-18)
- **文件**: `src/agent_labs/human_loop/`
- **内容**:
  - `approval.py` — ApprovalManager/ApprovalRequest: 5种审批动作、风险等级、审批/拒绝/取消/过期状态管理、工具审批映射
- **测试**: `tests/unit/test_human_loop/test_approval.py` (10 个测试)
- **状态**: ✅ 已完成

### #11 实现安全沙箱 ✅ 已完成 (2025-06-18)
- **文件**: `src/agent_labs/security/`
- **内容**:
  - `sandbox.py` — ProcessSandbox/DockerSandbox/SandboxFactory: 进程隔离执行、代码/命令双模式、输出截断、临时目录管理
  - `timeout.py` — TimeoutManager: 协程超时包装、工具/节点/LLM/请求多级超时、超时统计
- **测试**: `tests/unit/test_security/test_security.py` (11 个测试)
- **状态**: ✅ 已完成

### #12 实现长任务支持 ✅ 已完成 (2025-06-18)
- **文件**: `src/agent_labs/long_running/`
- **内容**:
  - `decomposer.py` — TaskDecomposer/LongTask/SubTask/Checkpoint: 线性/并行/阶段三种分解策略、检查点持久化(JSON)、断点续传、进度追踪
- **测试**: `tests/unit/test_long_running/test_long_running.py` (12 个测试)
- **状态**: ✅ 已完成

### #13 实现 MCP 接入 ✅ 已完成 (2025-06-18)
- **文件**: `src/agent_labs/mcp/`
- **内容**:
  - `server.py` — MCPServerManager: 多MCP服务器管理、动态工具发现(filesystem/database/web_search)、ToolRegistry自动注册、命名冲突处理
- **测试**: `tests/unit/test_mcp/test_mcp.py` (14 个测试)
- **状态**: ✅ 已完成

---

## 🔵 P3 — 集成阶段：打通经络（✅ 全部完成 2025-06-18）

### #14 启动时注册内置工具+技能 ✅ 已完成 (2025-06-18)
- **内容**: `app.py` lifespan 中调用 `register_all_builtin_tools()` + `register_all_builtin_skills()`，加载 `ToolPermissionManager` 并注入 `ToolExecutor`
- **同时**: `deps.py` 新增 14 个全局服务单例（Tracer/TokenMonitor/ApprovalManager/EmailNotifier/TimeoutManager/SkillRegistry/SkillExecutor/ContextBuilder/ContextCompressor/KnowledgeInjector/ToolPermissionManager/SkillPermissionManager）
- **依赖**: 无
- **状态**: ✅ 已完成

### #15 接入上下文工程到 GraphNodes ✅ 已完成 (2025-06-18)
- **内容**: `context_node` 集成 `ContextCompressor`（超长对话自动压缩）+ `KnowledgeInjector`（动态知识检索）+ `ContextBuilder`（结构化上下文构建）
- **同时**: `memory_node` 接入 `MemoryManager.summarize_episode()` 实际写入记忆
- **依赖**: #14
- **状态**: ✅ 已完成

### #16 接入可观测性到 Agent 执行链路 ✅ 已完成 (2025-06-18)
- **内容**: `decide_node`/`tool_node`/`skill_node` 中集成 `Tracer`（span 追踪）+ `TokenMonitor`（token 统计）
- **同时**: `ReactAgent._get_graph()` 传递所有注入服务到 `GraphNodes`
- **依赖**: #15
- **状态**: ✅ 已完成

### #17 接入审批+通知到 tool_node/human_node ✅ 已完成 (2025-06-18)
- **内容**: `tool_node` 检查 `ApprovalManager.needs_approval()`，高权限工具自动暂停；`notify_node` 调用 `EmailNotifier` 发送错误/完成通知；`human_node` 集成审批状态检查
- **同时**: `tool_node` 接入 `TimeoutManager` 统一超时管理
- **依赖**: #16
- **状态**: ✅ 已完成

### #18 实现 skill_node 并接入 SkillExecutor ✅ 已完成 (2025-06-18)
- **内容**: `GraphNodes.skill_node` 实现技能执行（LLM 触发 CALL_SKILL → 解析技能名 → 调用 SkillExecutor）；`GraphBuilder` 支持 `enable_skill_node` 参数
- **依赖**: #14, #17
- **状态**: ✅ 已完成

### #19 API 层扩展 + 集成测试 ✅ 已完成 (2025-06-18)
- **新增端点**:
  - `GET/POST /api/v1/skills` — 技能列表和执行
  - `GET /api/v1/observability/traces` — 追踪列表
  - `GET /api/v1/observability/dashboard` — 监控仪表板
  - `GET /api/v1/observability/stats` — 全局统计
  - `GET/POST /api/v1/approval/pending` — 审批管理
- **新增测试**: 25 个集成测试（API 端点 + Graph 编译 + 节点隔离 + 工具/技能集成）
- **测试结果**: 250 passed, 1 skipped（2026-08-27，Python 3.12）
- **依赖**: #15, #16, #17, #18
- **状态**: ✅ 已完成

---

## 🟣 P4 — 交互体验增强

### #20 实现 CLI 聊天模式 ✅ 已完成 (2025-06-18)
- **文件**: `src/agent_labs/cli/chat.py`
- **内容**:
  - `ChatEngine` — 交互式聊天引擎，多轮对话 + 会话管理
  - `Spinner` — asyncio 终端旋转动画（⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏）
  - 内置命令系统：`/help`, `/exit`, `/clear`, `/tools`, `/skills`, `/history`, `/stats`, `/model`
  - 模型切换：`/model list` 查看可用模型，`/model <id>` 动态切换
  - ANSI 颜色输出（自动检测 TTY，管道时禁用颜色）
  - API Key 检测：启动时检查 ANTHROPIC_API_KEY / OPENAI_API_KEY
  - 服务初始化复用 `deps.py`，与 API 模式共享全局单例
- **入口**: `python -m agent_labs chat [--model claude-sonnet-4-6]`
- **测试**: `tests/integration/test_cli.py` (28 个测试)
- **依赖**: 无
- **状态**: ✅ 已完成

---

## 环境信息

- **外部中间件**: 无需搭建（零依赖）
- **包管理**: uv（`uv sync` 安装依赖）
- **Python**: 3.11（`.python-version` 锁定）
