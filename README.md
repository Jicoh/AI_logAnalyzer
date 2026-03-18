# AI Log Analyzer

BMC服务器日志AI分析工具，自动识别日志中的问题并提供可能的原因和解决方案。

## 功能特性

- **日志解析**：支持BMC日志格式，自动提取错误和警告信息
- **知识库管理**：支持多知识库创建、文档添加、版本管理
- **BM25检索**：基于BM25算法的文档相似度检索
- **AI分析**：整合日志分析结果和知识库内容，调用AI进行深度分析
- **命令行界面**：简洁的CLI操作方式

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

### 2. 创建知识库

```bash
# 创建新知识库
python main.py kb create --name "BMC知识库"

# 输出示例：
# 知识库创建成功: kb_327b57e4
```

### 3. 添加文档到知识库

```bash
# 支持txt、md、pdf、docx格式
python main.py kb add --kb-id kb_327b57e4 --file data/bmc_knowledge.md

# 输出示例：
# 文档添加成功: doc_30a2fa89
```

### 4. 分析日志

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

## 项目结构

```
AI_logAnalyzer/
├── main.py                    # 主入口
├── requirements.txt           # 依赖文件
├── config/                    # 配置目录
│   ├── ai_config.json        # AI配置
│   └── default_prompt.txt    # 默认提示词
├── data/                      # 数据目录
│   ├── test_log.txt          # 测试日志
│   ├── bmc_knowledge.md      # BMC知识文档
│   └── plugin_output/        # 插件分析输出
├── document/                  # 知识库存储
└── src/                       # 源代码
    ├── plugin_analyzer/       # 插件分析模块
    ├── ai_analyzer/           # AI分析模块
    ├── knowledge_base/        # 知识库模块
    ├── config_manager/        # 配置管理模块
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
    "knowledge_base": {
        "default_id": "",
        "version": "1.0"
    },
    "bm25": {
        "k1": 1.5,
        "b": 0.75
    }
}
```

## 支持的文档格式

| 格式 | 扩展名 |
|------|--------|
| 纯文本 | .txt |
| Markdown | .md |
| PDF | .pdf |
| Word | .docx |

## 技术栈

- Python 3.10+
- BM25 检索算法
- jieba 中文分词
- rank-bm25 文档检索

## 依赖

```
rank-bm25>=0.2.2
jieba>=0.42.1
pypdf>=3.0.0
python-docx>=0.8.11
requests>=2.28.0
```

## License

MIT