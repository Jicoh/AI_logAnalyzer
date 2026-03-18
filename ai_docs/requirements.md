# AI日志分析项目需求说明书与实现规划

## 一、项目概述

### 1.1 项目目的
对服务器BMC日志进行AI分析，自动识别日志中的问题，并提供可能的原因和解决方案。

### 1.2 技术栈
- 编程语言：Python 3.10+
- 检索技术：BM25
- AI接口：支持动态配置的AI API调用
- 交互方式：命令行界面（CLI）

---

## 二、功能需求

### 2.1 插件分析模块
- 对日志文件进行预处理和初步分析
- 分析结果输出为JSON格式
- 模块独立，与AI分析模块解耦

### 2.2 AI分析模块
- 接收插件分析结果、日志信息、知识库内容
- 调用AI API进行深度分析
- 输出分析报告

### 2.3 知识库管理
- 支持多知识库管理
- 支持知识库版本管理
- 支持知识库的增删改查
- 使用BM25技术进行文档检索
- 支持多种文档类型（txt, pdf, md, docx等）

### 2.4 配置管理
- AI相关配置保存在JSON文件中
- 支持动态修改配置
- 内置默认提示词（txt文件，可随时修改）

### 2.5 命令行界面
- 所有功能通过命令行操作
- 支持参数化调用

---

## 三、项目结构

```
AI_logAnalyzer/
├── ai_docs/                      # 项目文档目录
│   ├── requirements.md           # 需求说明书（本文档）
│   ├── progress.md               # 开发进度文档
│   └── development_guide.md      # 开发要求文档
├── config/                       # 配置文件目录
│   ├── ai_config.json           # AI配置
│   └── default_prompt.txt       # 默认提示词
├── document/                     # 知识库文档目录
│   └── {knowledge_base_id}/      # 按知识库ID分类
│       └── document_id.txt      # 文档ID记录文件
├── data/                         # 数据目录
│   ├── plugin_output/           # 插件分析输出
│   └── ai_output/               # AI分析输出
├── src/                          # 源代码目录
│   ├── main.py                  # 主入口
│   ├── plugin_analyzer/         # 插件分析模块
│   │   ├── __init__.py
│   │   └── analyzer.py
│   ├── ai_analyzer/             # AI分析模块
│   │   ├── __init__.py
│   │   ├── analyzer.py          # AI分析核心
│   │   └── client.py            # AI API客户端
│   ├── knowledge_base/          # 知识库模块
│   │   ├── __init__.py
│   │   ├── manager.py           # 知识库管理
│   │   ├── bm25_retriever.py    # BM25检索
│   │   └── document_loader.py   # 文档加载器
│   ├── config_manager/          # 配置管理模块
│   │   ├── __init__.py
│   │   └── manager.py
│   └── utils/                   # 工具模块
│       ├── __init__.py
│       └── file_utils.py
└── requirements.txt             # 依赖文件
```

---

## 四、数据结构定义

### 4.1 插件分析输出格式 (plugin_output.json)
```json
{
    "analysis_time": "2024-01-01 10:00:00",
    "log_file": "bmc_log.txt",
    "error_count": 10,
    "warning_count": 25,
    "errors": [
        {
            "timestamp": "2024-01-01 09:00:00",
            "level": "ERROR",
            "message": "Temperature sensor failure",
            "component": "sensor_temp_01",
            "line_number": 100
        }
    ],
    "warnings": [],
    "statistics": {
        "total_lines": 10000,
        "error_rate": 0.001
    }
}
```

### 4.2 AI配置格式 (ai_config.json)
```json
{
    "api": {
        "base_url": "https://api.example.com",
        "api_key": "your_api_key",
        "model": "gpt-4",
        "temperature": 0.7,
        "max_tokens": 4096
    },
    "knowledge_base": {
        "default_id": "kb_001",
        "version": "1.0"
    },
    "bm25": {
        "k1": 1.5,
        "b": 0.75
    }
}
```

### 4.3 知识库元数据格式
```json
{
    "kb_id": "kb_001",
    "name": "BMC日志知识库",
    "version": "1.0",
    "created_at": "2024-01-01 10:00:00",
    "updated_at": "2024-01-01 10:00:00",
    "document_count": 10,
    "documents": [
        {
            "doc_id": "doc_001",
            "filename": "bmc_guide.pdf",
            "file_type": "pdf",
            "created_at": "2024-01-01 10:00:00"
        }
    ]
}
```

---

## 五、模块实现规划（详细步骤）

### 第一阶段：项目基础设施（约800行代码）

#### 步骤1：项目初始化与配置管理
**预计代码量：约200行**

任务清单：
- 创建项目目录结构
- 创建requirements.txt依赖文件
- 实现配置管理模块（config_manager/manager.py）
- 创建AI配置文件模板（ai_config.json）
- 创建默认提示词文件（default_prompt.txt）

实现要点：
- 配置管理器支持读取、修改、保存JSON配置
- 支持配置项的动态更新
- 提供配置验证功能

---

#### 步骤2：工具模块实现
**预计代码量：约150行**

任务清单：
- 实现文件工具模块（utils/file_utils.py）
- 文件读写操作封装
- JSON文件处理
- 路径处理工具

实现要点：
- 统一文件编码处理（UTF-8）
- 异常处理简洁明了
- 不做过度防御性编程

---

#### 步骤3：插件分析模块实现
**预计代码量：约450行**

任务清单：
- 实现日志解析器
- 实现错误/警告提取
- 实现统计分析功能
- 输出JSON格式结果

实现要点：
- 支持常见BMC日志格式
- 按时间戳、级别、组件分类
- 统计错误率、警告率等指标

---

### 第二阶段：知识库模块（约700行代码）

#### 步骤4：文档加载器实现
**预计代码量：约250行**

任务清单：
- 实现多格式文档加载（txt, pdf, md, docx）
- 文档内容提取
- 文档分块处理

实现要点：
- 使用现有库处理不同格式
- 文档分块大小可配置
- 提取关键文本内容

---

#### 步骤5：BM25检索实现
**预计代码量：约200行**

任务清单：
- 实现BM25算法核心
- 文档索引构建
- 相似度检索

实现要点：
- 使用rank_bm25库或自行实现
- 支持中文分词（jieba）
- 索引持久化存储

---

#### 步骤6：知识库管理器实现
**预计代码量：约250行**

任务清单：
- 知识库创建、删除、查询
- 文档添加、删除
- 版本管理
- 知识库元数据管理

实现要点：
- 每个知识库独立目录
- 版本号递增管理
- 文档ID自动生成

---

### 第三阶段：AI分析模块（约600行代码）

#### 步骤7：AI客户端实现
**预计代码量：约200行**

任务清单：
- 实现AI API调用封装
- 支持流式/非流式响应
- 错误处理与重试机制

实现要点：
- 支持多种AI模型接口
- 统一的请求/响应格式
- 简洁的错误处理

---

#### 步骤8：AI分析器实现
**预计代码量：约400行**

任务清单：
- 整合插件分析结果
- 整合知识库检索结果
- 构建分析提示词
- 调用AI进行分析
- 输出分析报告

实现要点：
- 提示词模板化
- 上下文长度控制
- 分析结果格式化输出

---

### 第四阶段：命令行界面与集成（约400行代码）

#### 步骤9：命令行界面实现
**预计代码量：约300行**

任务清单：
- 使用argparse实现CLI
- 支持子命令（analyze, kb, config）
- 参数解析与验证

子命令设计：
```
# 分析日志
python main.py analyze --log <logfile> --kb <kb_id> --prompt <prompt>

# 知识库管理
python main.py kb create --name <name>
python main.py kb add --kb-id <id> --file <file>
python main.py kb delete --kb-id <id>
python main.py kb list

# 配置管理
python main.py config get --key <key>
python main.py config set --key <key> --value <value>
```

---

#### 步骤10：主程序集成与测试
**预计代码量：约100行**

任务清单：
- 实现主入口（main.py）
- 模块间协调调用
- 端到端测试

实现要点：
- 清晰的调用流程
- 简洁的错误提示
- 完整的日志输出

---

## 六、开发里程碑

| 阶段 | 步骤 | 预计代码量 | 主要产出 |
|------|------|------------|----------|
| 一 | 1-3 | ~800行 | 配置管理、工具模块、插件分析 |
| 二 | 4-6 | ~700行 | 文档加载、BM25检索、知识库管理 |
| 三 | 7-8 | ~600行 | AI客户端、AI分析器 |
| 四 | 9-10 | ~400行 | CLI界面、主程序集成 |

**总预计代码量：约2500行**

---

## 七、技术要点

### 7.1 性能优化
- 使用生成器处理大日志文件
- BM25索引缓存
- 异步IO处理（可选）

### 7.2 可扩展性
- 插件模块可独立开发
- AI模型可配置切换
- 知识库可独立扩展

### 7.3 可维护性
- 模块职责单一
- 接口清晰明确
- 配置外置可修改

---

## 八、依赖库

```
# requirements.txt
rank-bm25>=0.2.2      # BM25检索
jieba>=0.42.1         # 中文分词
pypdf>=3.0.0          # PDF处理
python-docx>=0.8.11   # Word文档处理
requests>=2.28.0      # HTTP请求
```

---

## 九、验收标准

1. 插件分析模块能正确解析BMC日志并输出JSON
2. 知识库支持创建、删除、添加文档操作
3. BM25检索能返回相关文档片段
4. AI分析能输出有意义的问题诊断和解决方案
5. 所有功能可通过命令行调用
6. 配置文件可动态修改并生效