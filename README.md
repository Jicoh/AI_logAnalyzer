# AI Log Analyzer

BMC服务器日志AI分析工具，自动识别日志中的问题并提供可能的原因和解决方案。

## 功能特性

- **日志解析**：支持BMC日志格式，自动提取错误和警告信息
- **插件系统**：可扩展的插件架构，支持自定义分析插件
- **知识库管理**：支持多知识库创建、文档添加、混合检索（BM25/向量/混合）
- **日志规则**：自定义日志文件描述规则，帮助AI智能识别日志类型
- **AI智能选择**：根据日志规则自动选择合适的插件和文件进行分析
- **历史记录**：查看过往分析记录，包括错误/警告统计、AI分析结果回顾
- **设置管理**：Web界面直接配置API参数、检索模式、提示词模板
- **Web界面**：图形化操作界面，支持日志上传、知识库管理、在线分析
- **CLI命令**：简洁的命令行操作方式

## 安装

```bash
pip install -r requirements.txt
```

## 快速开始

### 1. 配置API

```bash
python main.py config set api.base_url https://api.example.com/v1
python main.py config set api.api_key your_api_key
python main.py config set api.model gpt-4
```

### 2. 启动Web界面

```bash
# 默认启动 (http://127.0.0.1:18888)
python web_app.py

# 自定义端口和主机
python web_app.py --port 9000 --host 0.0.0.0

# 禁用调试模式
python web_app.py --no-debug
```

### 3. Web界面功能

| 页面 | 功能 |
|------|------|
| 分析器 | 上传日志文件进行分析，支持tar.gz/tar/zip/txt/log格式 |
| 知识库 | 创建、查看、删除知识库，添加/删除文档 |
| 日志规则 | 创建规则集，添加日志文件路径的描述规则 |
| 历史记录 | 查看过往分析结果，包括插件输出和AI分析 |
| 设置 | 配置API、BM25、向量检索参数，编辑提示词模板 |

### 4. CLI命令完整说明

#### 日志分析

```bash
python main.py analyze <path>                       # 插件分析（无AI）
python main.py analyze <path> --ai                  # 插件分析+AI分析
python main.py analyze <path> --ai --prompt <提示词>  # AI分析+提示词
python main.py analyze <path> --ai --ai-select --prompt <提示词>  # AI智能选择
```

#### 插件管理

```bash
python main.py plugin list          # 列出所有可用插件（显示类型、ID、描述）
python main.py plugin categories    # 按分类查看插件列表
python main.py plugin select        # 显示当前选择的插件
python main.py plugin select <category>              # 选择某类别全部插件
python main.py plugin select <category> <plugins>    # 选择某类别指定插件
python main.py plugin selected      # 显示已选择的插件（类型+名称）
```

#### 知识库管理

```bash
python main.py kb list                                    # 列出所有知识库
python main.py kb create --name <name> --description <desc>  # 创建知识库
python main.py kb info --kb-id <id>                       # 查看知识库详情
python main.py kb delete --kb-id <id>                     # 删除知识库
python main.py kb add --kb-id <id> --file <file>          # 添加文档
python main.py kb remove --kb-id <id> --doc-id <doc_id>   # 删除文档
python main.py kb search --kb-id <id> --query <query> --top <n>  # 搜索知识库
python main.py kb reindex --kb-id <id>                    # 重建索引
```

#### 配置管理

```bash
python main.py config list                   # 查看所有配置
python main.py config get --key <key>        # 获取单个配置项
python main.py config set --key <key> --value <value>  # 设置配置项

# 示例：配置API
python main.py config set api.base_url https://api.example.com/v1
python main.py config set api.api_key your_api_key
python main.py config set api.model gpt-4
```

#### 日志规则管理

```bash
python main.py log-rules list                                        # 列出所有规则集
python main.py log-rules create --name <name> --description <desc>   # 创建规则集
python main.py log-rules show --rules-id <id>                        # 查看规则集详情
python main.py log-rules delete --rules-id <id>                      # 删除规则集
python main.py log-rules add --rules-id <id> --file-path <path>      # 添加规则
python main.py log-rules remove --rules-id <id> --rule-id <rule_id>  # 删除规则
```

#### 缓存管理

```bash
python main.py cache stats           # 查看缓存大小统计
python main.py cache clear-results   # 清理分析结果缓存
python main.py cache clear-temp      # 清理临时文件缓存
```

## 项目结构

```
AI_logAnalyzer/
├── main.py                 # CLI入口
├── web_app.py              # Web应用入口
├── config/                 # 配置目录
├── data/                   # 数据目录
│   ├── uploads/            # 上传文件
│   ├── temp/               # 处理临时目录
│   ├── plugin_output/      # 插件分析输出
│   └── ai_output/          # AI分析输出
├── document/               # 知识库存储
├── plugins/                # 插件目录
│   ├── builtin/            # 内置插件
│   └── custom/             # 自定义插件
└── src/                    # 源代码
    ├── ai_analyzer/        # AI分析模块
    ├── knowledge_base/     # 知识库模块
    ├── log_metadata/       # 日志元数据模块
    ├── config_manager/     # 配置管理模块
    └── web/                # Web模块
```

## 配置说明

配置文件：`config/ai_config.json`

| 配置项 | 说明 |
|--------|------|
| api.base_url | API地址 |
| api.api_key | API密钥 |
| api.model | 模型名称 |
| api.temperature | 温度参数 (0-2) |
| api.max_tokens | 最大输出长度 |
| bm25.k1, bm25.b | BM25参数 |
| embedding.enabled | 是否启用向量检索 |
| embedding.model | 向量模型 |
| retrieval.mode | 检索模式：bm25/vector/hybrid |
| web.host, web.port | Web服务地址和端口 |

## 插件开发

在 `custom_plugins/` 下创建插件目录：

```
custom_plugins/my_plugin/
├── plugin.py       # 实现 analyze() 方法
└── plugin.json     # 元数据文件
```

**plugin.json 示例：**
```json
{
    "id": "my_plugin",
    "name": "My Plugin",
    "version": "1.0.0",
    "description": "插件描述",
    "plugin_type": "CloudBMC"
}
```

详见 `plugins/README.md`。

## 内置插件

| 插件 | 说明 |
|------|------|
| log_parser | 日志解析，提取错误、警告和统计信息 |
| log_statistics | 日志统计，分析条数分布和趋势 |

## 支持的文件格式

| 类型 | 格式 |
|------|------|
| 日志文件 | .txt, .log, .tar.gz, .tar, .zip |
| 知识库文档 | .txt, .md, .pdf, .docx |

## 技术栈

- Python 3.10+
- Flask + Alpine.js
- BM25 + 向量检索
- jieba 中文分词

## License

MIT