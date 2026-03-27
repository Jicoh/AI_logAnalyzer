# AI Log Analyzer

BMC服务器日志AI分析工具，自动识别日志中的问题并提供可能的原因和解决方案。

## 功能特性

- **日志解析**：支持BMC日志格式，自动提取错误和警告信息
- **插件系统**：可扩展的插件架构，支持自定义分析插件
- **知识库管理**：支持多知识库创建、文档添加、版本管理
- **日志规则管理**：自定义日志文件描述规则，帮助AI智能识别日志类型
- **混合检索**：支持BM25检索、向量检索、混合检索三种模式
- **AI智能选择**：根据日志规则自动选择合适的插件和文件进行分析
- **AI分析**：整合日志分析结果和知识库内容，调用AI进行深度分析
- **命令行界面**：简洁的CLI操作方式
- **Web界面**：图形化操作界面，支持日志上传、知识库管理、日志规则管理、在线分析

## 安装

```bash
# 克隆项目
git clone <repository_url>
cd AI_logAnalyzer

# 安装依赖
pip install -r requirements.txt
```

## 快速开始

### 1. 配置AI API

```bash
# 设置API地址
python main.py config set api.base_url https://api.example.com/v1

# 设置API密钥
python main.py config set api.api_key your_api_key

# 设置模型名称
python main.py config set api.model gpt-4
```

### 2. Web界面使用

启动Web服务：

```bash
python web_app.py
```

启动后访问 http://127.0.0.1:18888 即可使用Web界面。

Web界面功能：
- **日志上传**：上传日志文件进行分析，支持 tar.gz、tar、zip、txt、log 格式
- **知识库管理**：创建、查看、删除知识库，添加/删除文档
- **日志规则管理**：创建规则集，添加日志文件路径的描述规则
- **在线分析**：选择知识库和日志规则后分析上传的日志，结果流式输出
- **AI智能选择**：开启后自动根据日志规则选择合适的插件和文件

### 3. 创建知识库（CLI）

```bash
# 创建新知识库
python main.py kb create --name "BMC知识库"

# 输出示例：
# 知识库创建成功: kb_327b57e4
```

### 4. 添加文档到知识库（CLI）

```bash
# 支持txt、md、pdf、docx格式
python main.py kb add --kb-id kb_327b57e4 --file data/bmc_knowledge.md

# 输出示例：
# 文档添加成功: doc_30a2fa89
```

### 5. 分析日志（CLI）

```bash
# 分析日志文件
python main.py analyze --log data/test_log.txt --kb kb_327b57e4

# 使用自定义提示词
python main.py analyze --log data/test_log.txt --kb kb_327b57e4 --prompt config/custom_prompt.txt
```

## 命令参考

### analyze - 分析日志

```bash
python main.py analyze --log <logfile> --kb <kb_id> [--prompt <prompt_file>]
```

| 参数 | 说明 |
|------|------|
| --log | 日志文件路径 |
| --plugins | 指定使用的插件ID，多个用逗号分隔（可选） |
| --kb | 知识库ID |
| --prompt | 自定义提示词文件（可选） |

### kb - 知识库管理

```bash
# 创建知识库
python main.py kb create --name <name>

# 添加文档
python main.py kb add --kb-id <id> --file <file>

# 删除文档
python main.py kb remove-doc --kb-id <id> --doc-id <doc_id>

# 删除知识库
python main.py kb delete --kb-id <id>

# 列出所有知识库
python main.py kb list

# 查看知识库详情
python main.py kb info --kb-id <id>
```

### config - 配置管理

```bash
# 获取配置值
python main.py config get --key api.base_url

# 设置配置值
python main.py config set --key api.model --value gpt-4
```

### plugin - 插件管理

```bash
# 列出所有可用插件
python main.py plugin list
```

## 项目结构

```
AI_logAnalyzer/
├── main.py                    # CLI主入口
├── web_app.py                 # Web应用入口
├── requirements.txt           # 依赖文件
├── config/                    # 配置目录
│   ├── ai_config.json        # AI配置
│   ├── default_prompt.txt    # 默认提示词
│   └── log_metadata_rules.json # 日志规则配置
├── data/                      # 数据目录
│   ├── test_log.txt          # 测试日志
│   ├── bmc_knowledge.md      # BMC知识文档
│   ├── uploads/              # Web上传文件存储
│   ├── temp/                 # 分析处理临时目录
│   ├── ai_output/            # AI分析输出
│   └── plugin_output/        # 插件分析输出
├── document/                  # 知识库存储
├── plugins/                   # 插件目录
│   ├── base.py               # 插件基类
│   ├── manager.py            # 插件管理器
│   ├── builtin/              # 内置插件
│   │   ├── log_parser/       # 日志解析插件
│   │   └── log_statistics/   # 日志统计插件
│   └── custom/               # 自定义插件目录
└── src/                       # 源代码
    ├── ai_analyzer/           # AI分析模块
    │   ├── analyzer.py       # AI分析器
    │   └── selection_agent.py # AI智能选择Agent
    ├── knowledge_base/        # 知识库模块
    ├── log_metadata/          # 日志元数据管理模块
    ├── config_manager/        # 配置管理模块
    ├── web/                   # Web模块
    │   ├── routes/           # 路由定义
    │   ├── templates/        # HTML模板
    │   └── static/           # 静态资源
    └── utils/                 # 工具模块
```

## 配置说明

配置文件位于 `config/ai_config.json`：

```json
{
    "api": {
        "base_url": "https://api.example.com/v1",
        "api_key": "your_api_key",
        "model": "gpt-4",
        "temperature": 0.7,
        "max_tokens": 4096
    },
    "bm25": {
        "k1": 1.5,
        "b": 0.75
    },
    "embedding": {
        "enabled": true,
        "provider": "openai",
        "base_url": "",
        "api_key": "",
        "model": "text-embedding-3-small",
        "dimension": 1536,
        "batch_size": 100
    },
    "retrieval": {
        "mode": "hybrid",
        "bm25_weight": 0.5,
        "vector_weight": 0.5,
        "rrf_k": 60
    }
}
```

### 检索模式说明

| 模式 | 说明 |
|------|------|
| bm25 | 仅使用BM25关键词检索 |
| vector | 仅使用向量语义检索 |
| hybrid | 混合检索，结合BM25和向量检索结果 |

## 日志规则管理

日志规则用于描述特定日志文件的类型信息，帮助AI智能选择合适的分析插件。

### 规则结构

每条规则包含：
- **file_path**：日志文件的完整路径（如 `/var/log/sel.log`）
- **description**：日志类型描述
- **keywords**：关键词列表，帮助AI识别日志内容
- **suggested_plugins**：建议使用的分析插件

### Web界面管理

1. 访问"日志规则"页面
2. 创建规则集或使用默认规则集
3. 添加日志文件规则
4. 在分析页面选择要使用的规则集
5. 开启"AI智能选择"模式进行分析

## 插件系统

### 插件架构

插件系统支持动态加载和执行分析插件，方便扩展日志分析能力。

#### 插件分类

| 分类 | 说明 |
|------|------|
| parser | 日志解析类插件 |
| analyzer | 日志分析类插件 |
| detector | 问题检测类插件 |
| reporter | 报告生成类插件 |
| other | 其他类型插件 |

### 开发自定义插件

#### 1. 创建插件目录

在 `plugins/custom/` 下创建插件目录：

```
plugins/custom/my_plugin/
├── __init__.py
├── plugin.py       # 插件实现
└── plugin.json     # 插件元数据
```

#### 2. 实现插件类

`plugin.py` 示例：

```python
from plugins.base import BasePlugin, PluginCategory, AnalysisResult
from datetime import datetime

class MyPlugin(BasePlugin):
    @property
    def id(self) -> str:
        return "my_plugin"

    @property
    def name(self) -> str:
        return "My Custom Plugin"

    @property
    def version(self) -> str:
        return "1.0.0"

    @property
    def description(self) -> str:
        return "A custom analysis plugin"

    @property
    def category(self) -> PluginCategory:
        return PluginCategory.ANALYZER

    def analyze(self, log_file: str) -> AnalysisResult:
        # 实现分析逻辑
        return AnalysisResult(
            plugin_id=self.id,
            plugin_name=self.name,
            analysis_time=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            log_file=log_file,
            error_count=0,
            warning_count=0,
            errors=[],
            warnings=[],
            statistics={}
        )

# 必须导出 plugin_class
plugin_class = MyPlugin
```

#### 3. 创建元数据文件

`plugin.json` 示例：

```json
{
    "id": "my_plugin",
    "name": "My Custom Plugin",
    "version": "1.0.0",
    "description": "A custom analysis plugin",
    "category": "analyzer",
    "author": "Your Name",
    "tags": ["custom", "analysis"],
    "enabled": true
}
```

#### 4. 使用插件

```bash
# CLI方式
python main.py analyze --log data/test_log.txt --plugins my_plugin

# Web界面
# 在插件选择区域勾选对应的插件
```

### 内置插件

| 插件ID | 名称 | 分类 | 说明 |
|--------|------|------|------|
| log_parser | Log Parser | parser | 日志解析，提取错误、警告和统计信息 |
| log_statistics | Log Statistics | analyzer | 日志统计，分析日志条数分布和趋势 |

## 支持的文件格式

### 日志文件格式

| 格式 | 扩展名 | 说明 |
|------|--------|------|
| 纯文本日志 | .txt, .log | 直接上传分析 |
| tar.gz压缩包 | .tar.gz, .tgz | 自动解压后分析内部日志文件 |
| tar压缩包 | .tar | 自动解压后分析内部日志文件 |
| zip压缩包 | .zip | 自动解压后分析内部日志文件 |

### 知识库文档格式

| 格式 | 扩展名 |
|------|--------|
| 纯文本 | .txt |
| Markdown | .md |
| PDF | .pdf |
| Word | .docx |

## 技术栈

- Python 3.10+
- Flask Web框架
- BM25 检索算法
- 向量嵌入检索
- jieba 中文分词
- rank-bm25 文档检索
- Alpine.js 前端交互

## 依赖

```
flask>=2.0.0
rank-bm25>=0.2.2
jieba>=0.42.1
pypdf>=3.0.0
python-docx>=0.8.11
requests>=2.28.0
numpy>=1.20.0
```

## License

MIT