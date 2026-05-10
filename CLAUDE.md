# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Build/Run Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run web interface
python main.py web                    # Default: http://127.0.0.1:18888
python main.py web --port 9000 --host 0.0.0.0  # Custom port/host
python main.py web --no-debug         # Disable debug mode

# Run tests
pytest tests/                          # Run all tests
pytest tests/test_json_parser.py -v    # Run single test with verbose output

# CLI usage
python main.py config set api.base_url <url>
python main.py config set api.api_key <key>
python main.py config set api.model <model_name>
python main.py kb create --name "Knowledge Base Name"
python main.py kb add --kb-id <id> --file <document>
python main.py analyze <path>                       # 插件分析（无AI）
python main.py analyze <path> --ai                  # 插件分析+AI分析
python main.py analyze <path> --log-rules <rules_id>  # 使用日志规则辅助分析
python main.py plugin list
python main.py plugin select <category>  # CloudBMC/iBMC/LxBMC
python main.py log-rules list  # 日志规则管理
python main.py cache stats  # 缓存统计

# 插件独立CLI（脚本集成用）
python plugins/cli_main.py plugin list
echo '{"system.log": "内容"}' | python plugins/cli_main.py analyze --plugin-id CloudBMC_00001
echo '{"system.log": "内容"}' | python plugins/cli_main.py analyze --plugin-id CloudBMC_00001 --task-name "任务" --bmc-ip "192.168.1.1" --date "2026-05-09"
```

## Architecture

This is a BMC server log analysis tool that uses AI to identify problems and suggest solutions.

### Core Flow
1. **Plugin Analysis**: Plugins (in `plugins/`) parse and analyze log files
2. **Knowledge Base Retrieval**: BM25/vector search retrieves relevant documents from `document/`
3. **AI Analysis**: Combines plugin results + knowledge base context, calls LLM API with streaming

### Agent Architecture
系统采用分层Agent架构：
- **Orchestrator Agent** (`orchestrator_agent.py`): 主编排Agent，理解用户意图、选择Skill、调用Subagent/MCP工具、整合结果
- **Subagent Registry**: Subagent注册表，管理可用的Subagent
- **Log Analyzer Subagent**: 日志分析Subagent，执行具体的日志分析任务（含智能选择功能）

### Key Modules

| Module | Location | Purpose |
|--------|----------|---------|
| Settings Manager | `src/system_config_manager/` | System config (API, BM25, embedding) |
| User Config | `src/user_config_manager/` | User-level preferences (plugin selection, KB selection) |
| Knowledge Base | `src/knowledge_base/` | CRUD, BM25+Vector indexing, hybrid search (RRF fusion) |
| Agent | `src/agent/` | Prompt building, API calls with streaming |
| Orchestrator Agent | `src/agent/orchestrator_agent.py` | 主Agent编排器，理解用户意图、调度Subagent/MCP工具 |
| Log Analyzer Subagent | `src/agent/subagents/log_analyzer.py` | 日志分析Subagent（核心分析引擎，含智能选择） |
| Subagent Registry | `src/agent/subagents/registry.py` | Subagent注册表 |
| Skill Loader | `src/agent/skill_loader.py` | Skill扫描和加载 |
| Log Metadata | `src/log_metadata/` | Log file description rules for AI selection |
| Plugin System | `plugins/` (submodule) | Dynamic plugin discovery and execution |
| Custom Plugins | `custom_plugins/` | User-defined plugins |
| Web Interface | `src/web/` | Flask routes, SSE streaming for analysis |
| Authentication | `src/auth/` | User authentication, password hashing, permission decorators |
| User Model | `src/models/` | User data model, database management |
| Admin API | `src/web/routes/admin_api.py` | User management, system configuration |
| Storage | `src/storage/` | User storage quota management |
| Session Manager | `src/session_manager/` | 智能助手会话管理 |

#### SSE Streaming
Analysis results stream to web UI via Server-Sent Events (`/api/analyze/stream`), allowing real-time progress updates during long-running AI analysis.

### Plugin System
- Plugins extend log analysis capabilities
- **Submodule**: `plugins/` is a git submodule (`log-analyzer-plugins` repo)
- **Builtin plugins**: `plugins/builtin/` (core plugins in submodule, organized by plugin_type: CloudBMC/iBMC/LxBMC)
- **Custom plugins**: `custom_plugins/` (user-defined plugins in main project)
- Each plugin implements `BasePlugin` with `analyze(log_content: Dict[str, str])` returning `AnalysisResult`
- `log_content` is a `{"文件名/相对路径": "文件内容"}` dictionary, prepared by `read_log_files_to_content(path)`
- Plugin types: CloudBMC, iBMC, LxBMC (used for categorization and selection)
- **HTML Renderer**: `plugins/renderer/` converts plugin results to static HTML
- **Standalone CLI**: `plugins/cli_main.py` for script integration

#### Section Types
Plugins can return multiple section types in `AnalysisResult.sections`:
- `stats` - Statistics overview with items (label, value, unit, severity)
- `table` - Data table with columns and rows
- `timeline` - Chronological events
- `cards` - Card-based display for grouped info
- `chart` - Bar/pie/line charts
- `search_box` - Searchable data list
- `raw` - Custom JSON data

#### Plugin Development

Create a new plugin in `custom_plugins/my_plugin/`:

```
custom_plugins/my_plugin/
├── plugin.py        # Required: implements BasePlugin
└── plugin.json      # Required: metadata
```

**plugin.json:**
```json
{
    "id": "my_plugin",
    "name": "My Plugin",
    "version": "1.0.0",
    "description": "插件中文描述",
    "plugin_type": "CloudBMC"
}
```

**plugin.py:**
```python
from plugins.base import BasePlugin, AnalysisResult, ResultMeta, StatsItem

class MyPlugin(BasePlugin):
    def analyze(self, log_content: Dict[str, str]) -> AnalysisResult:
        from datetime import datetime

        # log_content 是 {"相对路径": "文件内容"} 字典
        log_files = list(log_content.keys())

        meta = ResultMeta(
            plugin_id=self.id,
            plugin_name=self.name,
            version=self.get_version(),
            analysis_time=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            log_files=log_files,
            plugin_type=self.get_plugin_type()
        )
        result = AnalysisResult(meta=meta)
        result.add_stats("概览", [
            StatsItem(label="文件数", value=len(log_files), severity="info")
        ])
        return result

plugin_class = MyPlugin
```

See `plugins/README.md` for full documentation.

### Data Directories
- `data/uploads/` - Web-uploaded files
- `data/temp/` - Temporary processing (work directories with timestamp_filename format)
- `data/analysis_output/` - Analysis results (JSON + HTML)
- `data/sessions/` - 智能助手会话目录
- `document/` - Knowledge base storage
- `custom_plugins/` - User-defined plugins
- `data/app.db` - User database (SQLite)
- `data/users/` - User data directories (isolated by employee_id)

### User Authentication

用户认证系统基于 Flask-Login，使用 SQLite 存储用户数据。

#### 用户角色
- **普通用户**: 可使用日志分析、知识库等功能，受限存储配额
- **管理员**: 可管理用户、修改系统配置、查看全局统计

#### 默认账号
首次启动自动创建管理员账号：
- 工号: `Administrator`
- 密码: `Admin@9000`

#### 认证流程
- 用户通过工号+密码登录/注册
- 登录状态由 Flask-Login 管理（session）
- 所有页面需登录访问，管理员菜单仅管理员可见

#### 管理员功能
- 用户管理: 创建用户、启用/禁用、重置密码、修改配额
- 系统配置: 修改 AI API、Embedding、检索设置
- 全局统计: 用户数量、存储使用量

## Development Guidelines

### Naming Conventions
- Functions: `snake_case`
- **私有/内部函数**: `_single_leading_underscore` 前缀（遵循 PEP 8）
- Classes: `PascalCase`
- Variables: `snake_case`
- Constants: `UPPER_SNAKE_CASE`

**正确示例：**
```python
def load_config():
    """公共函数，不使用前缀"""
    pass

def _validate_path(path):
    """私有/内部辅助函数，使用单下划线前缀"""
    pass

class ConfigManager:
    pass

config_file = "config.json"

MAX_RETRY_COUNT = 3
```

**错误示例：**
```python
def loadConfig():  # 不要用驼峰命名
    pass

def __validate__(path):  # 不要用双下划线前后缀
    pass
```

### Code Style
- 代码需要简洁明了，避免冗余
- 不做太多的未来设计和防御性编程
- 只实现当前需求需要的功能
- 避免过度抽象和不必要的复杂性
- 使用4个空格缩进，不使用Tab
- 每行代码不超过100个字符
- 函数之间空一行，类之间空两行

**正确做法：**
```python
def read_json(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        return json.load(f)
```

**错误做法：**
```python
def read_json(file_path, encoding='utf-8', validate=False, backup=False, log_errors=True):
    # 过多的参数和选项，增加了不必要的复杂性
    if validate:
        # 未来可能需要但当前不需要的验证逻辑
        pass
    if backup:
        # 未来可能需要但当前不需要的备份逻辑
        pass
    # ...
```

### Comment Guidelines
- 代码注释必须使用中文
- 只在必要时添加注释
- 代码应尽量自解释
- 不写显而易见的注释
- 复杂逻辑添加简短说明

### Common Issues to Avoid
1. 过度的异常捕获和处理
2. 不必要的参数验证
3. 未来功能的预留代码
4. 过度的抽象和封装
5. 不必要的配置选项
6. 使用双下划线前后缀（如 `__validate__`）

### CSRF Protection

项目使用 Flask-WTF CSRF 保护，所有POST端点默认需要CSRF Token。

**前端POST请求规则：**
- 前端使用 `fetch()` 发送POST请求时无法携带CSRF Token
- 所有POST端点必须在 `src/web/app.py` 中添加 `csrf.exempt()` 配置

**新增POST API端点时：**
1. 在对应蓝图文件中定义路由（如 `routes/my_api.py`）
2. 在 `src/web/app.py` 的 CSRF豁免区块添加：
   ```python
   csrf.exempt(app.view_functions['蓝图名.端点函数名'])
   ```
3. 格式：`蓝图名.端点函数名`（如 `cache_api.clear_temp`）

**CSRF豁免安全前提：**
- 端点必须有其他保护机制：登录验证、管理员权限、限流等
- 端点不应处理敏感操作（如删除数据）时缺少二次确认

## Configuration

### System Settings (管理员配置)
File: `config/system_config.json`
- `web.*` - Web server settings (host, port, debug)
- `api.*` - LLM API settings (base_url, api_key, model, temperature, max_tokens)
- `orchestrator.*` - Orchestrator Agent settings (max_rounds, context_limit, etc.)
- `bm25.*` - BM25 parameters (k1, b)
- `embedding.*` - Vector embedding settings (enabled, provider, model, dimension)
- `retrieval.*` - Search mode (bm25/vector/hybrid), weights, RRF parameters

支持环境变量占位符：`${VAR_NAME}`

### User Config (用户配置)
File: `data/users/{employee_id}/user_config.json`
- `selected_plugins` - 用户选中的插件列表
- `selected_kb_id` - 用户选中的知识库ID
- `default_kb_id` - 默认知识库ID
- `enable_ai` - 是否启用AI分析
- 用户配置通过 Web 界面管理，CLI 不保存用户配置

### User Config Template
File: `config/user_config_template.json`
- 新用户初始化配置的模板

### Prompt files
- `config/default_prompt_template.txt` - Read-only template
- `config/default_prompt.txt` - User-customizable prompt (overrides template)
- `src/agent/prompts/subagent_log_analyze_prompt.txt` - Log Analyzer Subagent prompt
- `src/agent/prompts/orchestrator_prompt.txt` - Orchestrator Agent prompt
- `config/log_metadata_rules.json` - Log file description rulesets for AI selection

## Knowledge Base Retrieval

Three retrieval modes supported via `retrieval.mode` config:

1. **bm25**: Keyword-based search using jieba for Chinese text
2. **vector**: Semantic search using embedding API (requires `embedding.enabled=true`)
3. **hybrid**: Combines BM25 + vector using RRF (Reciprocal Rank Fusion) algorithm

RRF formula: `score(d) = bm25_weight * 1/(k+rank_bm25) + vector_weight * 1/(k+rank_vector)`

## 智能助手功能

聊天式交互界面，主Agent智能编排Skill/MCP/Tool，日志分析Agent作为Subagent执行具体分析任务。

### 核心模块

| 模块 | 位置 | 功能 |
|------|------|------|
| Orchestrator Agent | `src/agent/orchestrator_agent.py` | 主Agent，理解用户意图、调度Subagent/MCP工具 |
| Session Manager | `src/session_manager/` | 会话管理，最多2个活跃会话 |
| Subagent Registry | `src/agent/subagents/registry.py` | Subagent注册表 |
| Log Analyzer Subagent | `src/agent/subagents/log_analyzer.py` | 日志分析Subagent（核心分析引擎） |
| Skill Loader | `src/agent/skill_loader.py` | Skill扫描和加载 |

### Skill系统

Skill定义存放在`src/agent/skills/`目录，采用SKILL.md格式：

```markdown
---
name: skill-name
description: 功能说明
allowed-tools: tool1 tool2
---

# Skill标题

## 使用场景
...

## 执行步骤
...
```

### 会话目录结构

```
data/sessions/{user_id}/session_{timestamp}_{random}/
  work_dir/           # 工作目录
  outputs/            # 输出文件
  conversation.json   # 对话历史
  state.json          # 会话状态
```

### API配置

- `orchestrator_api`: 主Agent API配置（base_url, model, temperature, max_tokens, max_context）
- `subagent_api`: Subagent API配置
