# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Build/Run Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run web interface
python web_app.py                    # Default: http://127.0.0.1:18888
python web_app.py --port 9000 --host 0.0.0.0  # Custom port/host
python web_app.py --no-debug         # Disable debug mode

# Run tests
pytest tests/

# CLI usage
python main.py config set api.base_url <url>
python main.py config set api.api_key <key>
python main.py config set api.model <model_name>
python main.py kb create --name "Knowledge Base Name"
python main.py kb add --kb-id <id> --file <document>
python main.py analyze <path>                       # 插件分析（无AI）
python main.py analyze <path> --ai                  # 插件分析+AI分析
python main.py analyze <path> --ai --ai-select --prompt <提示词>  # AI智能选择
python main.py plugin list
python main.py plugin select <category>  # CloudBMC/iBMC/LxBMC
python main.py log-rules list  # 日志规则管理
python main.py cache stats  # 缓存统计
```

## Architecture

This is a BMC server log analysis tool that uses AI to identify problems and suggest solutions.

### Core Flow
1. **Plugin Analysis**: Plugins (in `plugins/`) parse and analyze log files
2. **Knowledge Base Retrieval**: BM25/vector search retrieves relevant documents from `document/`
3. **AI Analysis**: Combines plugin results + knowledge base context, calls LLM API with streaming

### Dual-Agent Architecture (Scout + Sage)
The AI analysis uses a two-stage agent system:
- **Scout Agent** (`scout_agent.py`): Reconnaissance - extracts machine info, selects relevant log files, identifies key events
- **Sage Agent** (`sage_agent.py`): Deep analysis - generates comprehensive HTML report with problem analysis and solutions
- **Agent Coordinator** (`agent_coordinator.py`): Orchestrates Scout → Sage flow, extracts plugin summary, manages knowledge retrieval

### Key Modules

| Module | Location | Purpose |
|--------|----------|---------|
| Config Manager | `src/config_manager/` | AI config (API, BM25 params, embedding settings) |
| Knowledge Base | `src/knowledge_base/` | CRUD, BM25+Vector indexing, hybrid search (RRF fusion) |
| AI Analyzer | `src/ai_analyzer/` | Prompt building, API calls with streaming |
| Selection Agent | `src/ai_analyzer/selection_agent.py` | AI-powered plugin/file selection based on user prompt |
| Scout Agent | `src/ai_analyzer/scout_agent.py` | Log reconnaissance, machine info extraction, file selection |
| Sage Agent | `src/ai_analyzer/sage_agent.py` | Deep analysis, HTML report generation |
| Agent Coordinator | `src/ai_analyzer/agent_coordinator.py` | Orchestrates Scout → Sage flow |
| Log Metadata | `src/log_metadata/` | Log file description rules for AI selection |
| Plugin Selection | `src/plugin_selection/` | Web UI state: selected plugins, KB, AI settings |
| Plugin System | `plugins/` (submodule) | Dynamic plugin discovery and execution |
| Custom Plugins | `custom_plugins/` | User-defined plugins |
| Web Interface | `src/web/` | Flask routes, SSE streaming for analysis |

### Plugin System
- Plugins extend log analysis capabilities
- **Submodule**: `plugins/` is a git submodule (`log-analyzer-plugins` repo)
- **Builtin plugins**: `plugins/builtin/` (core plugins in submodule, organized by plugin_type: CloudBMC/iBMC/LxBMC)
- **Custom plugins**: `custom_plugins/` (user-defined plugins in main project)
- Each plugin implements `BasePlugin` with `analyze(log_path)` returning `AnalysisResult`
- `log_path` can be a file path or a directory path (for archives)
- Plugin types: CloudBMC, iBMC, LxBMC (used for categorization and selection)
- **HTML Renderer**: `plugins/renderer/` converts plugin results to static HTML

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
    def analyze(self, log_path: str) -> AnalysisResult:
        import os
        from datetime import datetime

        # 场景1：分析目录中的所有日志文件
        log_files = []
        for root, dirs, files in os.walk(log_path):
            for f in files:
                if f.endswith('.log') or f.endswith('.txt'):
                    log_files.append(os.path.join(root, f))

        # 场景2：分析特定文件名（如果插件只分析特定文件）
        # target_file = os.path.join(log_path, "system.log")
        # if os.path.exists(target_file):
        #     log_files = [target_file]

        meta = ResultMeta(
            plugin_id=self.id,
            plugin_name=self.name,
            version=self.get_version(),
            analysis_time=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            log_files=[os.path.basename(f) for f in log_files],
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
- `data/plugin_output/` - Plugin analysis results (JSON + HTML)
- `data/ai_output/` - AI analysis results
- `document/` - Knowledge base storage
- `custom_plugins/` - User-defined plugins

## Development Guidelines

### Naming Conventions
- Functions: `snake_case` (**不要在函数名前加下划线**)
- Classes: `PascalCase`
- Variables: `snake_case`
- Constants: `UPPER_SNAKE_CASE`

**正确示例：**
```python
def load_config():
    pass

class ConfigManager:
    pass

config_file = "config.json"

MAX_RETRY_COUNT = 3
```

**错误示例：**
```python
def _load_config():  # 不要加下划线前缀
    pass

def loadConfig():  # 不要用驼峰命名
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
1. 函数名加下划线前缀（如 `_load_config`）
2. 过度的异常捕获和处理
3. 不必要的参数验证
4. 未来功能的预留代码
5. 过度的抽象和封装
6. 不必要的配置选项

## Configuration

Config file: `config/ai_config.json`
- `api.*` - LLM API settings (base_url, api_key, model, temperature, max_tokens)
- `bm25.*` - BM25 parameters (k1, b)
- `embedding.*` - Vector embedding settings (enabled, provider, model, dimension)
- `retrieval.*` - Search mode (bm25/vector/hybrid), weights, RRF parameters

Prompt files:
- `config/default_prompt_template.txt` - Read-only template
- `config/default_prompt.txt` - User-customizable prompt (overrides template)
- `config/scout_prompt.txt` - Scout Agent prompt for log reconnaissance
- `config/sage_prompt.txt` - Sage Agent prompt for deep analysis
- `config/log_metadata_rules.json` - Log file description rulesets for AI selection

## Knowledge Base Retrieval

Three retrieval modes supported via `retrieval.mode` config:

1. **bm25**: Keyword-based search using jieba for Chinese text
2. **vector**: Semantic search using embedding API (requires `embedding.enabled=true`)
3. **hybrid**: Combines BM25 + vector using RRF (Reciprocal Rank Fusion) algorithm

RRF formula: `score(d) = bm25_weight * 1/(k+rank_bm25) + vector_weight * 1/(k+rank_vector)`
