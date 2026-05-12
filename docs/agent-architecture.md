# Agent 模块架构说明

本文档描述 `src/agent` 模块的代码架构和执行流程。

## 目录结构

```
src/agent/
├── orchestrator_agent.py    # 主Agent编排器
├── client.py                # AI客户端（API调用封装）
├── skill_loader.py          # Skill加载器
├── mcp_client.py            # MCP客户端
├── subagents/
│   ├── base.py              # Subagent基类
│   ├── registry.py          # Subagent注册表
│   └── log_analyzer.py      # 日志分析Subagent
├── skills/
│   └── analyze-log/SKILL.md # Skill定义
├── prompts/                 # 提示词模板
└── templates/               # HTML模板
```

## 核心组件关系

```
用户输入
    ↓
┌─────────────────────────────────────────────────────┐
│           OrchestratorAgent (主编排器)                │
│  - 理解用户意图                                        │
│  - 选择合适的 Skill/Subagent/MCP工具                   │
│  - 管理对话上下文（压缩、历史）                          │
│  - 内置工具：get_session_state, save_session_note,   │
│    list_available_tools, dispatch_subagent,          │
│    upload_log_file                                   │
└──────────────┬──────────────────────────────────────┘
               │
       ┌───────┼───────┬───────────────┐
       ↓       ↓       ↓               ↓
   AIClient  Skill  SubagentRegistry  MCPClient
       │       │       │               │
       │       │       ↓               │
       │       │  LogAnalyzerSubagent  │
       │       │       │               │
       └───────┴───────┴───────────────┘
                        ↓
                   AI分析结果
```

## 执行流程详解

### 1. OrchestratorAgent 初始化

文件：`orchestrator_agent.py:140-248`

```python
def __init__(self, user_id, session_id, ...):
    # 加载配置
    self.load_config()  # max_rounds, tool_call_limit, context_limit

    # 初始化AI客户端
    self.client = AIClient(orchestrator_api_config)

    # 注册Subagent
    register_log_analyzer_subagent(self.subagent_registry, ...)

    # 加载Skill
    self.skill_loader.scan()

    # 加载会话
    self.session = self.session_manager.get_session(session_id)
```

### 2. 主对话入口 chat()

文件：`orchestrator_agent.py:469-537`

```python
def chat(self, user_input: str) -> Tuple[str, Dict]:
    # 1. 构建消息列表
    messages = self._build_chat_messages(user_input)

    # 2. 检查并压缩上下文
    messages = self._check_and_compress_context(messages)

    # 3. 多轮交互循环
    while round_count < max_rounds:
        response = self.client.chat_with_tools(messages, self.tools)

        if response.has_tool_calls():
            # 执行工具调用
            for tool_call in response.tool_calls:
                result = self._process_tool_call(tool_call)
                messages.append(tool_result)
        else:
            # 返回最终响应
            final_response = response.content
            break

    # 4. 保存会话
    self._save_chat_session(...)
    return final_response, metadata
```

### 3. 工具调用处理 execute_tool_call()

文件：`orchestrator_agent.py:676-707`

```python
def execute_tool_call(self, tool_name: str, args: Dict) -> Dict:
    # 内置工具
    if tool_name in ORCHESTRATOR_TOOL_NAMES:
        return self.execute_builtin_tool(tool_name, args)

    # MCP工具
    if self.mcp_client and tool_name in self.mcp_client.tool_to_server:
        return self.mcp_client.call_tool(tool_name, args)

    return {"error": f"未知工具: {tool_name}"}
```

### 4. Subagent 调度 dispatch_subagent()

文件：`orchestrator_agent.py:796-859`

```python
def dispatch_subagent(self, subagent_name, request, user_intent=""):
    # 1. 执行准备函数
    prepare_handler = self.prepare_handlers.get(subagent_name)
    if prepare_handler:
        prepare_result = prepare_handler()  # 如 prepare_log_analyzer

    # 2. 构建上下文
    context = {
        "log_files": log_files,
        "kb_ids": kb_ids,
        "user_intent": user_intent,
        ...
    }

    # 3. 通过注册表执行
    result = self.subagent_registry.execute(subagent_name, request, context, work_dir)

    return {
        "success": result.success,
        "content": result.content,
        "intent_response": intent_response,
        ...
    }
```

### 5. LogAnalyzerSubagent 执行

文件：`log_analyzer.py:473-543`

```python
def analyze(self, log_files, plugin_result=None, kb_ids=None,
            user_prompt=None, user_intent=None, ...):
    # 1. 智能选择（如果plugin_result=None）
    if plugin_result is None:
        selection = self.smart_select(log_files, user_prompt)
        plugin_result = self.run_plugin_analysis(selected_plugins, selected_files)

    # 2. 预处理
    machine_info = self.extract_machine_info(plugin_result)
    knowledge_content = self.retrieve_knowledge(kb_ids, plugin_result)

    # 3. AI分析（多轮工具调用）
    result = self.run_ai_analysis(...)

    return {
        'html': html,
        'interaction_record': {...},
        'intent_response': '针对用户意图的回应'
    }
```

## AIClient 核心方法

文件：`client.py`

| 方法 | 用途 |
|------|------|
| `chat(messages)` | 流式对话，返回文本片段生成器 |
| `chat_with_tools(messages, tools)` | 支持工具调用的非流式对话 |
| `count_tokens(messages, tools)` | 估算token数量 |
| `analyze(prompt)` | 便捷分析方法 |

## Subagent Registry

文件：`registry.py`

```python
# 全局注册表
_registry = SubagentRegistry()

# 注册方式
registry.register(subagent_instance)  # 注册实例
registry.register_class(name, cls)     # 注册类（延迟实例化）

# 执行
result = registry.execute(subagent_name, request, context, work_dir)
```

## Skill 加载机制

文件：`skill_loader.py`

Skill 定义在 `src/agent/skills/*/SKILL.md`：

```markdown
---
name: skill-name
description: 功能描述
allowed-tools: tool1 tool2
---

# Skill内容
...
```

```python
# 扫描加载
skill_loader = get_skill_loader()
skills = skill_loader.scan()

# 获取Skill信息
skill = skill_loader.get("skill-name")
```

## 数据流总结

```
1. 用户输入 → OrchestratorAgent.chat()
      ↓
2. 构建消息（system prompt + 历史对话 + 用户输入）
      ↓
3. AI调用 → 返回工具调用或直接响应
      ↓
4. 工具调用：
   - 内置工具 → execute_builtin_tool()
   - MCP工具 → mcp_client.call_tool()
   - Subagent → registry.execute()
      ↓
5. Subagent执行：
   - 智能选择插件和文件
   - 运行插件分析
   - 知识库检索
   - AI多轮分析
   - 生成HTML报告
      ↓
6. 返回结果 → 保存会话 → 返回用户
```

## 内置工具定义

OrchestratorAgent 定义了以下内置工具（`orchestrator_agent.py:44-132`）：

| 工具名 | 功能 |
|--------|------|
| `get_session_state` | 获取当前会话状态信息 |
| `save_session_note` | 保存重要信息到会话状态 |
| `list_available_tools` | 列出所有可用工具 |
| `dispatch_subagent` | 调用指定Subagent执行任务 |
| `upload_log_file` | 上传日志文件到会话工作目录 |

## LogAnalyzerSubagent 内置工具

文件：`log_analyzer.py:23-104`

| 工具名 | 功能 |
|--------|------|
| `read_log_by_keyword` | 按关键词搜索日志内容 |
| `read_log_by_range` | 按行号范围读取日志 |
| `get_log_file_info` | 获取日志文件信息 |
| `search_knowledge_base` | 搜索知识库内容 |

## 上下文压缩机制

当上下文使用率超过 80% 时，OrchestratorAgent 会自动压缩历史对话：

```python
def compress_context(self, messages: List[Dict]) -> List[Dict]:
    # 保留 system 消息和最近 N 轮对话
    # 将中间对话压缩为摘要
    # 摘要通过 AI 生成
```

配置项（`config/system_config.json`）：
- `orchestrator.context_limit`: 上下文token限制（默认120000）
- `orchestrator.compression_threshold`: 压缩阈值（默认0.8）
- `orchestrator.compression_retain_rounds`: 保留最近对话轮数（默认5）

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

OrchestratorAgent 使用 `api` 配置块作为 API 设置：

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
