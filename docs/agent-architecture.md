# Agent 模块架构设计

本文档描述 `src/agent` 模块的分层架构、统一接口和组件职责。

## 目录结构

```
src/agent/
├── __init__.py              # 模块导出入口（仅暴露 AgentService/AgentSession）
├── service.py               # 统一对外服务入口（AgentService）
├── session.py               # Agent会话管理（AgentSession）
├── client.py                # AI客户端（API调用封装）
├── skill_loader.py          # Skill加载器
├── mcp_client.py            # MCP客户端
├── orchestrator_agent.py    # 主Agent编排器（兼容保留，内部委托给core）
├── core/                    # 核心引擎层
│   ├── __init__.py
│   ├── query_engine.py      # 主循环引擎（QueryEngine）
│   ├── tool_router.py       # 工具调用路由器（ToolRouter）
│   ├── prompt_builder.py    # 系统Prompt构建器（SystemPromptBuilder）
│   └── context_manager.py   # 上下文管理器（ContextManager）
├── subagents/
│   ├── base.py              # Subagent基类
│   ├── registry.py          # Subagent注册表
│   └── log_analyzer.py      # 日志分析Subagent
├── skills/                  # Skill定义
├── prompts/                 # 提示词模板
└── templates/               # HTML模板
```

## 分层架构

Agent模块采用四层架构设计，与主程序通过统一接口解耦：

```
+-------------------------------------------------------------+
|                        主程序层                               |
|   Web路由  /  CLI命令  /  Serve服务  /  测试脚本              |
+----------------------------+--------------------------------+
                             │
                             ▼ 统一接口（AgentService）
+-------------------------------------------------------------+
|                      入口层（Entry Layer）                    |
|                     AgentService / AgentSession              |
|  - 封装所有Agent能力，对外提供简洁接口                           |
|  - 管理内部组件的延迟初始化                                     |
|  - 隐藏Subagent/QueryEngine等内部细节                          |
+----------------------------+--------------------------------+
                             │
                             ▼
+-------------------------------------------------------------+
|                    系统Prompt层（Prompt Layer）                |
|                   SystemPromptBuilder                        |
|  - 动态组装系统提示（Skill + Subagent + MCP + 知识库）          |
|  - 支持模板加载和默认模板回退                                   |
+----------------------------+--------------------------------+
                             │
                             ▼
+-------------------------------------------------------------+
|                主循环Query Engine层（Core Layer）              |
|    QueryEngine + ContextManager + ToolRouter                  |
|  - 上下文压缩（ContextManager）                                |
|  - AI Query（支持工具调用）                                    |
|  - Tool Use判断与路由（ToolRouter）                            |
|  - Stop Hook判断                                             |
|  - 循环直至完成                                               |
+----------------+-------------+--------------+---------------+
                 │             │              │
                 ▼             ▼              ▼
           内置工具       Subagent       MCP工具
          (session等)  (log_analyzer)  (download等)
```

## 统一对外接口

### AgentService（唯一对外入口）

外部调用者通过 `AgentService` 与Agent模块交互，无需了解内部组件。

```python
from src.agent import AgentService

agent_service = AgentService(
    config_manager=...,      # 可选，延迟初始化
    kb_manager=...,          # 可选，延迟初始化
    plugin_manager=...,      # 可选，延迟初始化
    log_metadata_manager=..., # 可选，延迟初始化
    mcp_client=...           # 可选
)
```

#### 1. 日志分析（analyze）

```python
result = agent_service.analyze(
    log_files=["path/to/system.log"],
    plugin_result={...},           # 可选，为None时触发智能选择
    kb_ids=["kb_001"],             # 可选
    user_prompt="分析重启原因",     # 可选
    log_rules_id="rules_001",      # 可选
    user_intent="用户意图",         # 可选
    user_id="employee_id"          # 可选
)
# 返回: {'html': str, 'interaction_record': dict, 'intent_response': str}
```

#### 2. 纯插件分析（run_plugin_only）

```python
result = agent_service.run_plugin_only(
    source='cli',
    plugin_ids=['CloudBMC_00001'],
    log_content={'system.log': ['line1', 'line2']},
    task_name='',
    bmc_ip='',
    date=''
)
```

#### 3. 对话（chat）

```python
response, metadata = agent_service.chat(
    session_id='session_001',
    user_input='帮我分析这份日志',
    user_id='employee_id',
    kb_context='知识库检索结果...',  # 可选
    kb_ids=['kb_001']              # 可选
)
```

#### 4. 流式对话（chat_stream）

```python
for chunk in agent_service.chat_stream(
    session_id='session_001',
    user_input='帮我分析这份日志',
    user_id='employee_id',
    kb_context='...',
    kb_ids=['kb_001']
):
    print(chunk, end='')
```

## 核心组件详解

### QueryEngine（主循环引擎）

文件：`src/agent/core/query_engine.py`

负责执行核心的Agent处理循环：

```python
class QueryEngine:
    def __init__(self, ai_client, tool_router, context_manager, prompt_builder,
                 max_rounds=20, tool_call_limit=50):
        ...

    def run(self, session_state, user_input, conversation_history, session_context):
        # 1. 构建消息（system prompt + 历史 + 用户输入）
        # 2. 上下文压缩
        messages = self.context_manager.check_and_compress(messages, tools)
        # 3. 多轮交互循环
        while round_count < max_rounds:
            response = self.ai_client.chat_with_tools(messages, tools)
            if response.has_tool_calls():
                # 4. 工具路由
                result = self.tool_router.execute(tool_name, args)
            else:
                # 5. 输出最终响应
                break
        return {'final_response': ..., 'metadata': ..., 'messages': ...}

    def run_stream(self, ...):
        # 流式执行（无工具调用）
        for chunk in self.ai_client.chat(messages):
            yield chunk
```

### ToolRouter（工具路由器）

文件：`src/agent/core/tool_router.py`

统一分发所有工具调用：

```python
class ToolRouter:
    def execute(self, tool_name, args):
        if tool_name in 内置工具:
            return self._execute_builtin(tool_name, args)
        if tool_name in MCP工具:
            return self._execute_mcp(tool_name, args)
        return {"error": "未知工具"}
```

支持的工具类型：
- **内置工具**：`get_session_state`, `save_session_note`, `list_available_tools`, `dispatch_subagent`, `upload_log_file`
- **Subagent**：`log_analyzer` 等（通过注册表调度）
- **MCP工具**：外部MCP服务提供的工具

### ContextManager（上下文管理器）

文件：`src/agent/core/context_manager.py`

```python
class ContextManager:
    def calculate_usage(self, messages, tools) -> int:
        # 估算token使用量

    def check_and_compress(self, messages, tools) -> List[Dict]:
        # 检查使用率，超过阈值时自动压缩

    def compress(self, messages, tools) -> List[Dict]:
        # 保留system消息和最近N轮对话
        # 中间对话通过AI生成摘要
```

### SystemPromptBuilder（系统Prompt构建器）

文件：`src/agent/core/prompt_builder.py`

```python
class SystemPromptBuilder:
    def build(self, session_context) -> str:
        # 动态组装系统提示：
        # - 可用Skill列表
        # - 可用Subagent列表
        # - 当前会话状态（工作目录、使用率等）
        # - 知识库上下文（如有）
```

### AgentSession（会话管理）

文件：`src/agent/session.py`

```python
class AgentSession:
    def __init__(self, session_id, user_id, work_dir, outputs_dir):
        self.conversation_history = []
        self.state = {"notes": {}, "uploaded_files": [], ...}

    def to_prompt_context(self) -> Dict:
        # 转换为构建prompt所需的上下文字典
```

## 数据流

### 日志分析流程

```
用户上传日志
    │
    ▼
+--------------------------------------------------+
| 主程序（analyze_api.py / cli/handler.py）         |
| - 文件上传/解压                                   |
| - 调用 plugin_manager.run_analysis() 执行插件分析  |
+----------------------------+---------------------+
                             │
                             ▼
+--------------------------------------------------+
| AgentService.analyze()                            |
| - 初始化 LogAnalyzerSubagent                      |
| - 智能选择（可选）                                 |
| - 调用 subagent.analyze()                         |
+----------------------------+---------------------+
                             │
+--------------------------------------------------+
| LogAnalyzerSubagent.analyze()                     |
| - 预处理（机器信息、知识库检索）                     |
| - 调用 run_ai_analysis()                          |
|   - AI多轮工具调用（read_log_by_keyword等）        |
|   - 生成HTML报告                                   |
+----------------------------+---------------------+
                             │
                             ▼
                        返回结果
```

### 智能助手对话流程

```
用户输入
    │
    ▼
+--------------------------------------------------+
| 主程序（assistant_api.py）                         |
| - 知识库检索（可选）                               |
| - 调用 AgentService.chat() / chat_stream()        |
+----------------------------+---------------------+
                             │
                             ▼
+--------------------------------------------------+
| AgentService.chat()                               |
| - 加载/创建 AgentSession                          |
| - 构建 QueryEngine                                |
| - 调用 query_engine.run()                         |
+----------------------------+---------------------+
                             │
                             ▼
+--------------------------------------------------+
| QueryEngine.run()                                 |
| - 构建系统Prompt（SystemPromptBuilder）            |
| - 上下文压缩（ContextManager）                     |
| - AI Query（AIClient.chat_with_tools）            |
| - Tool Use判断                                    |
|   ├─ 是 → ToolRouter.execute() → 循环            |
|   └─ 否 → 输出最终响应                             |
+----------------------------+---------------------+
                             │
                             ▼
+--------------------------------------------------+
| ToolRouter.execute()                              |
| - 内置工具（直接执行）                             |
| - Subagent（通过SubagentRegistry调度）             |
| - MCP工具（通过MCPClient调用）                     |
+----------------------------+---------------------+
                             │
                             ▼
                        保存会话 → 返回用户
```

## 配置项

### Orchestrator 配置

```json
{
    "orchestrator": {
        "max_rounds": 20,
        "tool_call_limit": 50,
        "context_limit": 120000,
        "compression_threshold": 0.8,
        "compression_retain_rounds": 5
    }
}
```

### API 配置

```json
{
    "api": {
        "base_url": "...",
        "api_key": "...",
        "model": "...",
        "temperature": 0.7,
        "max_tokens": 4096
    }
}
```

## 内置工具定义

### Orchestrator 内置工具

| 工具名 | 功能 |
|--------|------|
| `get_session_state` | 获取当前会话状态信息 |
| `save_session_note` | 保存重要信息到会话状态 |
| `list_available_tools` | 列出所有可用工具 |
| `dispatch_subagent` | 调用指定Subagent执行任务 |
| `upload_log_file` | 上传日志文件到会话工作目录 |

### LogAnalyzerSubagent 内置工具

| 工具名 | 功能 |
|--------|------|
| `read_log_by_keyword` | 按关键词搜索日志内容 |
| `read_log_by_range` | 按行号范围读取日志 |
| `get_log_file_info` | 获取日志文件信息 |
| `search_knowledge_base` | 搜索知识库内容 |

## 迁移说明

### 旧接口（直接调用内部组件）

```python
# 日志分析
from src.agent.subagents.log_analyzer import LogAnalyzerSubagent
subagent = LogAnalyzerSubagent(config_manager=..., kb_manager=..., ...)
result = subagent.analyze(log_files=..., ...)

# 智能助手
from src.agent.orchestrator_agent import OrchestratorAgent
agent = OrchestratorAgent(user_id=..., session_id=..., ...)
response, metadata = agent.chat(user_input)
```

### 新接口（统一通过AgentService）

```python
from src.agent import AgentService

agent_service = AgentService()

# 日志分析
result = agent_service.analyze(log_files=..., ...)

# 智能助手
response, metadata = agent_service.chat(session_id=..., user_input=..., ...)
```

## 设计原则

1. **统一入口**：所有外部调用者通过 `AgentService` 与Agent模块交互
2. **内部分层**：入口层 → Prompt层 → Query Engine层，职责清晰
3. **延迟初始化**：内部依赖（config_manager, kb_manager等）按需初始化
4. **向后兼容**：`orchestrator_agent.py` 中的 `OrchestratorAgent` 保留，内部可逐步委托给 `QueryEngine`
5. **工具统一路由**：所有工具调用（内置/Subagent/MCP）通过 `ToolRouter` 分发
