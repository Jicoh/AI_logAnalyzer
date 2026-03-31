# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Build/Run Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run web interface (http://127.0.0.1:18888)
python web_app.py

# CLI usage
python main.py config set api.base_url <url>
python main.py config set api.api_key <key>
python main.py config set api.model <model_name>
python main.py kb create --name "Knowledge Base Name"
python main.py kb add --kb-id <id> --file <document>
python main.py analyze --log <logfile> --kb <kb_id>
python main.py plugin list
```

## Architecture

This is a BMC server log analysis tool that uses AI to identify problems and suggest solutions.

### Core Flow
1. **Plugin Analysis**: Plugins (in `plugins/`) parse and analyze log files
2. **Knowledge Base Retrieval**: BM25/vector search retrieves relevant documents from `document/`
3. **AI Analysis**: Combines plugin results + knowledge base context, calls LLM API with streaming

### Key Modules

| Module | Location | Purpose |
|--------|----------|---------|
| Config Manager | `src/config_manager/` | AI config (API, BM25 params, embedding settings) |
| Knowledge Base | `src/knowledge_base/` | CRUD, BM25+Vector indexing, hybrid search |
| AI Analyzer | `src/ai_analyzer/` | Prompt building, API calls with streaming |
| Plugin System | `plugins/` | Dynamic plugin discovery and execution |
| Web Interface | `src/web/` | Flask routes, SSE streaming for analysis |

### Plugin System
- Plugins extend log analysis capabilities
- Located in `plugins/builtin/` (core) and `plugins/custom/` (user-defined)
- Each plugin implements `BasePlugin` with `analyze(log_file)` returning `AnalysisResult`
- Plugin categories: PARSER, ANALYZER, DETECTOR, REPORTER, OTHER

### Data Directories
- `data/uploads/` - Web-uploaded files
- `data/temp/` - Temporary processing (work directories with timestamp_filename format)
- `data/ai_output/` - AI analysis results
- `document/` - Knowledge base storage

## Development Guidelines

From `ai_docs/development_guide.md`:

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