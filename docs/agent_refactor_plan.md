# Agent模块核心重构计划

## 实施进度

**第一阶段：核心重构 - 已完成 (2026-04-28)**

| 步骤 | 状态 | 备注 |
|-----|------|------|
| AI Client改造（支持tool_calls） | ✅ 完成 | 新增AIResponse类、chat_with_tools方法、count_tokens方法 |
| LogAnalyzerAgent实现 | ✅ 完成 | 创建log_analyzer_agent.py，实现多轮交互和工具执行器 |
| Prompt文件创建 | ✅ 完成 | 创建agent_prompt.txt和analysis_templates.json |
| 验证机制实现 | ✅ 完成 | 实现JSON验证、Schema验证、内容质量验证、降级HTML生成 |
| HTML模板调整 | ✅ 完成 | 新增分析摘要、潜在风险、分析覆盖范围区块 |
| 调用入口简化 | ✅ 完成 | 修改analyzer.py和analyze_api.py，使用analyze_with_agent函数 |
| Web API改为轮询 | ⏳ 待优化 | 当前保持SSE流式模式，后续优化为轮询模式 |
| 删除旧文件 | ✅ 完成 | 删除scout_agent.py、sage_agent.py、agent_coordinator.py及相关prompt、测试文件 |

**第一阶段验证状态 (2026-04-28)**

| 验证项 | 状态 | 备注 |
|-----|------|------|
| 模块导入测试 | ✅ 通过 | LogAnalyzerAgent、ToolExecutor、analyze_with_agent均可正常导入 |
| pytest单元测试 | ✅ 通过 | 66 passed，1 failed（API连接测试需服务运行） |
| HTML模板修复 | ✅ 完成 | 修复summary变量缺失问题，问题摘要统计可正常显示 |
| 清理遗留文件 | ✅ 完成 | 删除sage_html_prompt.txt、test_sage_raw_response.py |

**第二阶段：MCP/Skill扩展 - 待实施**

---

## Context

现有agent模块采用Scout+Sage双Agent架构，存在以下问题：
1. 两阶段分工边界模糊，Scout的search_context定位效果有限
2. 缺乏因果分析能力，只列问题不讲原因
3. 模型不敢输出潜在风险，过多免责声明
4. JSON验证不够严格，内容质量无检查

目标：合并为单一Agent，引入工具调用机制，改进prompt设计，加强输出验证，提升分析质量。

## 一、架构变更

### 1.1 合并Scout+Sage为LogAnalyzerAgent

**删除文件：**
- `src/ai_analyzer/scout_agent.py`
- `src/ai_analyzer/sage_agent.py`
- `src/ai_analyzer/agent_coordinator.py`

**新增文件：**
- `src/ai_analyzer/log_analyzer_agent.py` - 单一Agent实现

**保留文件：**
- `src/ai_analyzer/client.py` - AI客户端（需改造支持tool_calls）
- `config/sage_prompt.txt` - 改造为新Agent的prompt文件

### 1.2 新Agent架构

```
LogAnalyzerAgent
│
├── 输入（程序端预处理）
│   ├── plugin_result - 插件分析结果
│   ├── machine_info - 机器信息（从插件提取）
│   ├── knowledge_content - 知识库检索内容
│   ├── log_rules - 日志规则描述
│   ├── log_files - 日志文件路径列表
│   ├── analysis_templates - 常见问题分析模板（案例学习）
│   └── user_prompt - 用户提示词
│
├── 可用工具（模型自主调用）
│   ├── read_log_by_keyword(file, keyword, context_lines)
│   ├── read_log_by_range(file, start_line, end_line)
│   ├── get_log_file_info()
│   └── search_knowledge_base(query) - 可选
│
├── 多轮交互流程
│   ├── Round 1: 模型接收prompt，决定是否调用工具
│   ├── Round N: 模型自主分析，可多次调用工具
│   ├── Final: 模型输出JSON结果
│   └── 验证失败: 带错误反馈重试（最多1次）
│
├── 输出JSON结构
│   ├── machine_info - 机器核心信息
│   ├── analysis_summary - 分析摘要
│   ├── problems - 发现的问题（含analysis_logic）
│   ├── potential_risks - 潜在风险（含reasoning）
│   ├── solutions - 解决方案
│   ├── risk_assessment - 风险评估
│   └── analysis_coverage - 分析覆盖范围
│
└── 程序端处理
    ├── JSON格式验证
    ├── 内容质量验证（problems+potential_risks非空检查）
    ├── HTML渲染（模板不变）
    ├── ai_temp保存
    ├── 降级处理（验证失败后直接生成HTML）
```

## 二、AI Client改造

### 2.1 支持tool_calls

当前client只支持纯文本对话，需改造为：

```python
class AIClient:
    def chat_with_tools(self, messages, tools, tool_choice="auto"):
        """
        支持工具调用的聊天请求

        Args:
            messages: 消息列表
            tools: 工具定义列表（OpenAI格式）
            tool_choice: "auto" / "required" / "none"

        Returns:
            response: 完整响应对象，包含content或tool_calls
        """
        # 请求时增加tools参数
        payload = {
            "model": self.model,
            "messages": messages,
            "tools": tools,
            "tool_choice": tool_choice,
            "stream": False  # 工具调用模式不支持流式
        }
```

### 2.2 多轮对话管理

```python
class LogAnalyzerAgent:
    def run_analysis(self, ...):
        messages = [system_prompt, user_prompt]

        round_count = 0
        max_rounds = 10
        total_tokens = 0
        max_tokens = 60000  # 可配置

        while round_count < max_rounds and total_tokens < max_tokens:
            response = self.client.chat_with_tools(messages, self.tools)

            if response.has_tool_calls():
                # 执行工具调用
                tool_results = self.execute_tools(response.tool_calls)
                # 将工具结果加入消息历史
                messages.append(response.to_message())
                messages.append(tool_results.to_message())
                total_tokens += count_tokens(messages)
            else:
                # 模型输出最终结果
                return self.validate_and_render(response.content)

            round_count += 1

        # 超限后强制输出
        return self.force_output(messages)
```

## 三、Prompt重新设计

### 3.1 Prompt文件结构

新建 `config/agent_prompt.txt`：

```markdown
# 系统角色

你是BMC服务器日志分析专家。你的专长是深入理解BMC日志的语义和关联，从日志中发现隐藏的问题和潜在风险，提供有理有据的分析结论和解决建议。

# 核心原则

1. 有理有据：每条结论必须引用具体日志内容
2. 因果分析：不只列现象，要分析根因和逻辑链
3. 潜在风险：发现任何可疑迹象都要输出，但要说明依据
4. 简洁精确：禁止emoji，禁止废话，禁止无依据的免责声明

# 分析方法指导

## 基础分析流程
1. 首先查看插件发现的问题，理解已知问题类型
2. 根据日志规则，理解各日志文件的用途和关键字段
3. 主动扫描日志，寻找插件未发现的问题
4. 分析时间序列上的事件关联（前后事件因果关系）
5. 分析同一组件/IP的多条日志关联
6. 输出分析结论，包含分析逻辑

## 注意事项
- 日志中的error不一定真的是error，要结合上下文判断
- 同一条日志在不同场景下可能有不同含义
- 关注时间戳，分析事件发生的时间顺序
- 如果猜测有问题，也要输出，但要标注为"潜在风险"

# 常见问题分析模板

{analysis_templates}

# 可用工具

{tools_description}

# 分析数据

## 插件分析结果
{plugin_result}

## 机器信息
{machine_info}

## 知识库相关内容
{knowledge_content}

## 日志文件规则
{log_rules}

## 日志文件列表
{log_files_overview}

# 用户请求

{user_prompt}

# 输出要求

输出合法JSON，结构如下：

{
  "machine_info": {
    "serial_number": "字符串",
    "product_name": "字符串",
    "board_id": "字符串",
    "board_type": "字符串",
    "bmc_version": "字符串",
    "bios_version": "字符串",
    "bme_version": "字符串",
    "bmc_ip_address": "字符串"
  },
  "analysis_summary": "一句话概括主要发现",
  "problems": [
    {
      "title": "问题标题",
      "severity": "error/warning/info",
      "description": "问题描述",
      "analysis_logic": "分析推理过程，说明为什么判断这是问题",
      "log_reference": "引用的具体日志内容片段",
      "source": "来源（插件发现/自主发现）"
    }
  ],
  "potential_risks": [
    {
      "title": "潜在风险标题",
      "severity": "warning/info",
      "reasoning": "为什么怀疑可能有问题，依据是什么",
      "log_reference": "引用的具体日志内容",
      "recommendation": "建议的检查或确认方式"
    }
  ],
  "solutions": [
    {
      "title": "解决方案标题",
      "description": "方案描述",
      "steps": ["步骤1", "步骤2"],
      "priority": "high/medium/low",
      "applies_to": "适用于哪些问题"
    }
  ],
  "risk_assessment": {
    "level": "高/中/低",
    "description": "整体风险评估"
  },
  "analysis_coverage": {
    "files_analyzed": ["已分析的文件列表"],
    "files_skipped": ["跳过的文件及原因"],
    "analysis_depth": "全面/部分/重点"
  }
}

# JSON格式要求

1. 输出必须是有效的JSON对象，不能包含任何JSON之外的文本
2. 所有字符串值必须用英文双引号包裹
3. 字符串中如需包含特殊字符，必须转义
4. 不能在JSON中插入注释或说明文本
5. 确保所有花括号和方括号正确配对
6. 数组和对象最后一项后不要加逗号

直接输出JSON对象，不要包裹在代码块中。
```

### 3.2 常见问题分析模板

**管理方式：JSON文件配置**

新建 `config/analysis_templates.json`，管理员可手动编辑添加新模板：

```json
{
  "templates": [
    {
      "problem_type": "BMC重启",
      "keywords": ["reboot", "restart", "reset", "重启"],
      "analysis_logic": [
        "1. 检查重启前的日志，寻找触发原因（温度/电源/固件/人为）",
        "2. 检查重启后的日志，确认系统恢复正常",
        "3. 分析重启间隔和频率，判断是否异常",
        "4. 关联其他组件日志，检查重启是否影响其他服务"
      ],
      "typical_causes": ["温度过高", "电源异常", "固件bug", "人为操作"],
      "check_points": ["温度日志", "电源状态", "用户操作记录"]
    },
    {
      "problem_type": "网络连接异常",
      "keywords": ["network", "connection", "timeout", "网络", "连接"],
      "analysis_logic": [
        "1. 检查IP配置日志，确认配置正确",
        "2. 检查网络服务状态日志",
        "3. 分析连通性测试结果",
        "4. 区分是配置问题还是物理连接问题",
        "5. 检查是否影响其他依赖网络的组件"
      ],
      "typical_causes": ["IP冲突", "网线松动", "交换机故障", "网卡故障"],
      "check_points": ["IP配置", "ping测试", "网口状态"]
    },
    {
      "problem_type": "存储异常",
      "keywords": ["disk", "storage", "raid", "存储", "硬盘"],
      "analysis_logic": [
        "1. 检查RAID状态日志",
        "2. 分析磁盘错误日志，判断是软错误还是硬错误",
        "3. 检查存储控制器日志",
        "4. 关联BMC存储监控数据"
      ],
      "typical_causes": ["磁盘故障", "RAID卡故障", "线缆问题", "配置错误"],
      "check_points": ["RAID状态", "磁盘SMART", "控制器日志"]
    }
  ]
}
```

模板字段说明：
- `problem_type`: 问题类型名称
- `keywords`: 触发关键词列表
- `analysis_logic`: 分析步骤列表（强调逻辑和关联）
- `typical_causes`: 典型原因列表
- `check_points`: 检查点列表

后续可扩展：在admin界面提供模板编辑入口。

## 四、工具定义

### 4.1 工具列表

```python
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "read_log_by_keyword",
            "description": "在指定日志文件中搜索关键词，返回匹配位置前后context_lines行的内容",
            "parameters": {
                "type": "object",
                "properties": {
                    "file": {"type": "string", "description": "日志文件名"},
                    "keyword": {"type": "string", "description": "搜索关键词"},
                    "context_lines": {"type": "integer", "description": "上下文行数，默认20"}
                },
                "required": ["file", "keyword"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_log_by_range",
            "description": "读取指定日志文件的指定行号范围",
            "parameters": {
                "type": "object",
                "properties": {
                    "file": {"type": "string", "description": "日志文件名"},
                    "start_line": {"type": "integer", "description": "起始行号"},
                    "end_line": {"type": "integer", "description": "结束行号"}
                },
                "required": ["file", "start_line", "end_line"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_log_file_info",
            "description": "获取所有日志文件的信息，包括文件名、大小、行数",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_knowledge_base",
            "description": "在知识库中搜索相关内容，用于深入了解特定问题",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜索查询词"}
                },
                "required": ["query"]
            }
        }
    }
]
```

### 4.2 工具执行器

```python
class ToolExecutor:
    def __init__(self, log_files: List[str], kb_manager=None):
        self.file_map = {os.path.basename(f): f for f in log_files}
        self.kb_manager = kb_manager

    def execute(self, tool_name: str, args: dict) -> dict:
        if tool_name == "read_log_by_keyword":
            return self._read_by_keyword(args)
        elif tool_name == "read_log_by_range":
            return self._read_by_range(args)
        elif tool_name == "get_log_file_info":
            return self._get_file_info()
        elif tool_name == "search_knowledge_base":
            return self._search_kb(args)
        else:
            return {"error": f"未知工具: {tool_name}"}

    def _read_by_keyword(self, args):
        # 查找文件，搜索关键词，返回上下文
        ...

    def _read_by_range(self, args):
        # 读取指定行范围
        ...

    def _get_file_info(self):
        # 返回所有文件信息
        ...

    def _search_kb(self, args):
        # 调用知识库检索
        ...
```

### 4.3 Token限制配置

新增配置项 `config/ai_config.json`：

```json
{
  "api": { ... },
  "agent": {
    "max_tokens": 60000,
    "max_rounds": 10,
    "tool_call_limit": 20
  }
}
```

## 五、验证机制

### 5.1 验证流程

```python
def validate_output(response_text: str) -> tuple:
    """
    验证AI输出

    Returns:
        (data, errors): 解析后的数据和错误列表
    """
    # 1. JSON格式验证
    try:
        data = json.loads(extract_json(response_text))
    except json.JSONDecodeError as e:
        return None, [f"JSON格式错误: {str(e)}"]

    # 2. Schema验证
    required_fields = ['machine_info', 'analysis_summary', 'problems',
                       'potential_risks', 'solutions', 'risk_assessment']
    errors = []
    for field in required_fields:
        if field not in data:
            errors.append(f"缺少必需字段: {field}")

    # 3. 内容质量验证（简化版）
    if not data.get('problems') and not data.get('potential_risks'):
        errors.append("未发现任何问题或风险，请确认是否真的无异常")

    if errors:
        return None, errors

    return data, []
```

### 5.2 重试策略

```python
def run_with_retry(prompt_data: dict, max_retries: int = 2):
    """
    执行分析，支持重试
    """
    for attempt in range(max_retries):
        response = agent.run_analysis(prompt_data)
        data, errors = validate_output(response)

        if not errors:
            return data

        # 构建重试prompt，告诉模型具体错误
        retry_prompt = build_retry_prompt(errors, response)
        prompt_data['retry_feedback'] = retry_prompt

    # 重试失败，降级为直接生成HTML（保留现有逻辑）
    return generate_html_fallback(response)
```

### 5.3 降级HTML生成优化

当JSON验证重试都失败时，启用降级方案，让模型直接生成HTML。

优化点：
- 降级prompt需强调"输出分析逻辑"，不能只列问题
- 模板中也要体现analysis_logic字段

```python
FALLBACK_HTML_PROMPT = """
由于JSON格式验证失败，请直接生成HTML报告。

## 分析数据
{analysis_data}

## 输出要求
1. 输出完整HTML，从<!DOCTYPE html>开始
2. 每个问题必须包含"分析逻辑"段落，说明推理过程
3. 潜在风险也要输出，说明怀疑依据
4. 简洁精确，禁止emoji，禁止废话

直接输出HTML代码，不要包裹在代码块中。
"""
```

## 六、ai_temp记录结构

```json
{
  "timestamp": "2026-04-28 10:30:00",
  "agent": {
    "system_prompt": "完整系统prompt...",
    "analysis_data": {
      "plugin_result_summary": "...",
      "machine_info": {...},
      "log_files": ["file1.log", "file2.log"],
      "knowledge_used": true
    },
    "interactions": [
      {
        "round": 1,
        "model_response": {
          "content": null,
          "tool_calls": [
            {
              "name": "read_log_by_keyword",
              "args": {"file": "system.log", "keyword": "error"},
              "result": {"matched_line": 120, "content": "..."}
            }
          ]
        },
        "token_count": 1500
      },
      {
        "round": 2,
        "model_response": {
          "content": "最终JSON输出...",
          "tool_calls": null
        },
        "token_count": 2000
      }
    ],
    "total_rounds": 2,
    "total_tokens": 3500,
    "final_output": "解析后的JSON数据",
    "validation": {
      "passed": true,
      "errors": []
    }
  },
  "fallback_used": false,
  "error": null
}
```

## 七、HTML渲染

保持现有模板 `plugins/renderer/ai_report_template.html`，调整渲染逻辑：

```python
def render_html(data: dict) -> str:
    """
    渲染HTML报告
    """
    return template.render(
        machine_info=data.get('machine_info', {}),
        analysis_summary=data.get('analysis_summary', ''),
        problems=data.get('problems', []),
        potential_risks=data.get('potential_risks', []),
        solutions=data.get('solutions', []),
        risk_assessment=data.get('risk_assessment', {}),
        analysis_coverage=data.get('analysis_coverage', {}),
        analysis_time=datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    )
```

模板需新增区块：
- 潜在风险区块（区别于确认问题）
- 分析覆盖范围区块
- 每个问题显示analysis_logic

## 八、调用入口变更

### 8.1 Coordinator简化

删除`agent_coordinator.py`，在`analyze_with_ai.py`中直接调用：

```python
def analyze_with_ai(plugin_result, log_files, kb_id, user_prompt, log_rules_id):
    """
    AI分析入口（简化版）
    """
    # 1. 程序端预处理
    machine_info = extract_machine_info(plugin_result)
    knowledge_content = retrieve_knowledge(kb_id, plugin_result) if kb_id else ""
    log_rules = get_log_rules(log_rules_id) if log_rules_id else ""
    analysis_templates = load_analysis_templates()
    log_file_info = get_log_file_info(log_files)

    # 2. 构建prompt数据
    prompt_data = {
        'plugin_result': format_plugin_result(plugin_result),
        'machine_info': machine_info,
        'knowledge_content': knowledge_content,
        'log_rules': log_rules,
        'log_files_overview': log_file_info,
        'analysis_templates': format_templates(analysis_templates),
        'user_prompt': user_prompt
    }

    # 3. 调用Agent
    agent = LogAnalyzerAgent(config_manager, kb_manager)
    result = agent.run_analysis(prompt_data, log_files)

    # 4. 保存ai_temp
    save_ai_temp(result['interaction_record'])

    # 5. 返回HTML
    return result['html']
```

### 8.2 Web API调整

`src/web/routes/analyze_api.py`调整：

**统一改为轮询模式：**
- 工具调用不支持流式，统一使用非流式模式
- 前端轮询进度或WebSocket推送状态更新
- 后台完成后返回最终HTML

```python
# analyze_api.py
@router.post('/analyze')
def analyze(request):
    task_id = create_task()
    # 后台执行分析
    executor.submit(run_analysis_task, task_id, request.data)
    return {'task_id': task_id}

@router.get('/analyze/status/<task_id>')
def get_status(task_id):
    task = get_task(task_id)
    return {
        'status': task.status,
        'progress': task.progress,
        'html': task.html if task.status == 'completed'
    }
```

## 九、第一阶段实施步骤

### Step 1: AI Client改造 ✅ 已完成
1. `client.py`增加`AIResponse`类封装响应
2. 新增`chat_with_tools`方法支持工具调用
3. 新增`count_tokens`方法估算token数量

### Step 2: 新Agent实现 ✅ 已完成
1. 创建`src/ai_analyzer/log_analyzer_agent.py`
2. 实现`LogAnalyzerAgent`类，多轮交互逻辑
3. 实现`ToolExecutor`类，包含4个工具：read_log_by_keyword、read_log_by_range、get_log_file_info、search_knowledge_base

### Step 3: Prompt文件 ✅ 已完成
1. 创建`config/agent_prompt.txt`（完整的系统prompt）
2. 创建`config/analysis_templates.json`（8种常见问题分析模板）

### Step 4: 验证机制 ✅ 已完成
1. 实现JSON格式验证（`_extract_json`方法）
2. 实现Schema验证（检查必需字段）
3. 实现内容质量验证（problems+potential_risks非空检查）
4. 实现重试逻辑（验证失败后带错误反馈重试）
5. 实现降级HTML生成（`_generate_html_fallback`方法）

### Step 5: HTML模板调整 ✅ 已完成
1. 新增分析摘要区块
2. 新增潜在风险区块（区别于确认问题）
3. 问题详情显示analysis_logic和log_reference
4. 新增分析覆盖范围区块
5. 更新footer标识为"AI Log Analyzer Agent"

### Step 6: 调用入口调整 ✅ 已完成
1. `src/ai_analyzer/analyzer.py`新增`analyze_with_agent`函数
2. 新增`extract_machine_info_from_plugins`函数
3. 新增`load_analysis_templates`函数
4. `src/web/routes/analyze_api.py`替换所有AgentCoordinator调用
5. 更新`src/ai_analyzer/__init__.py`导出

### Step 7: Web API改造 ⏳ 待优化
1. 当前保持SSE流式模式（工具调用时可能不流畅）
2. 后续优化为轮询模式或WebSocket推送

### Step 8: 配置更新 ✅ 已完成
1. `config/ai_config.json`新增`agent`配置项：
   - max_tokens: 60000
   - max_rounds: 10
   - tool_call_limit: 20

### Step 9: 删除旧文件 ✅ 已完成
1. 删除`src/ai_analyzer/scout_agent.py`
2. 删除`src/ai_analyzer/sage_agent.py`
3. 删除`src/ai_analyzer/agent_coordinator.py`
4. 删除`config/scout_prompt.txt`
5. 删除`config/sage_prompt.txt`

### Step 10: 测试验证
1. 模块导入测试：已通过
2. 需进行实际日志分析测试验证功能

## 十、第一阶段风险点

1. **多轮交互API兼容性**：部分API可能不支持tool_calls格式，需测试
2. **Token消耗增加**：多轮交互会消耗更多token，需监控
3. **模型自主性**：模型可能滥用工具或不调用工具，需引导
4. **降级兼容性**：降级HTML生成需确保可用

## 十一、第二阶段：MCP/Skill扩展

### 11.1 目标

为Agent引入MCP（Model Context Protocol）和Skill调用能力，扩展Agent的工具范围，支持：
- 通过MCP下载日志
- 调用外部工具和服务
- 适配支持MCP的模型（minimax、glm系列）

### 11.2 MCP客户端框架

引入MCP客户端，管理MCP Server连接：

```python
# src/ai_analyzer/mcp_client.py

class MCPClient:
    """MCP协议客户端"""

    def __init__(self, config_manager):
        self.servers = {}  # server_name -> connection
        self.load_servers_from_config()

    def load_servers_from_config(self):
        """从配置加载MCP Server列表"""
        mcp_config = self.config_manager.get('mcp_servers', {})
        for name, server_config in mcp_config.items():
            self.connect_server(name, server_config)

    def connect_server(self, name, config):
        """连接MCP Server"""
        # 根据config中的transport类型连接
        # stdio / websocket / http
        ...

    def list_tools(self):
        """获取所有MCP Server提供的工具列表"""
        tools = []
        for name, server in self.servers.items():
            server_tools = server.list_tools()
            tools.extend(server_tools)
        return tools

    def call_tool(self, tool_name, args):
        """调用MCP工具"""
        # 查找工具所属的server
        server = self.find_tool_server(tool_name)
        return server.call_tool(tool_name, args)

    def list_resources(self):
        """获取MCP资源列表"""
        ...

    def read_resource(self, uri):
        """读取MCP资源"""
        ...
```

### 11.3 配置管理

在 `config/ai_config.json` 增加 MCP Server 配置：

```json
{
  "api": { ... },
  "agent": { ... },
  "mcp_servers": {
    "log_downloader": {
      "transport": "stdio",
      "command": "python",
      "args": ["mcp_servers/log_downloader/server.py"],
      "description": "日志下载服务，支持从远程服务器下载BMC日志"
    },
    "bmc_tools": {
      "transport": "websocket",
      "url": "ws://bmc-tools-server:8080/mcp",
      "description": "BMC工具集，支持IPMI命令、日志解析等"
    }
  }
}
```

### 11.4 Admin界面MCP配置

在管理员设置界面新增MCP Server配置入口：

```
/admin/settings/mcp
├── MCP Server列表
│   ├── 名称、类型、状态
│   ├── 启用/禁用开关
│   ├── 编辑/删除按钮
├── 新增MCP Server
│   ├── 名称输入
│   ├── Transport类型选择（stdio/websocket/http）
│   ├── 参数配置（command/args 或 url）
│   ├── 测试连接按钮
├── 工具列表预览
│   ├── 显示每个Server提供的工具
```

### 11.5 Agent集成MCP工具

LogAnalyzerAgent改造，支持MCP工具：

```python
class LogAnalyzerAgent:
    def __init__(self, config_manager, kb_manager=None, mcp_client=None):
        self.config_manager = config_manager
        self.kb_manager = kb_manager
        self.mcp_client = mcp_client

        # 工具列表 = 内置工具 + MCP工具
        self.tools = self.build_tools()

    def build_tools(self):
        """构建完整工具列表"""
        tools = BUILTIN_TOOLS.copy()
        if self.mcp_client:
            mcp_tools = self.mcp_client.list_tools()
            tools.extend(mcp_tools)
        return tools

    def execute_tool(self, tool_name, args):
        """执行工具调用"""
        # 区分内置工具和MCP工具
        if tool_name in BUILTIN_TOOL_NAMES:
            return self.builtin_executor.execute(tool_name, args)
        elif self.mcp_client:
            return self.mcp_client.call_tool(tool_name, args)
        else:
            return {"error": f"未知工具: {tool_name}"}
```

### 11.6 日志下载入口

Agent入口参数增加 `log_source`：

```python
def run_analysis(
    log_source: dict,  # 日志来源配置
    ...
):
    """
    log_source格式：
    {
        "type": "local_file",  # 或 "mcp_download"
        "paths": ["path1", "path2"],  # local_file模式
        "mcp_config": {  # mcp_download模式
            "server": "log_downloader",
            "target": {"ip": "192.168.1.100", "credentials": {...}}
        }
    }
    """

    if log_source['type'] == 'mcp_download':
        # Agent先调用MCP工具下载日志
        download_result = self.execute_tool('download_log', log_source['mcp_config'])
        log_files = download_result['files']
    else:
        log_files = log_source['paths']

    # 继续分析流程
    ...
```

用户可以通过prompt告诉Agent要下载什么日志：
- "帮我分析192.168.1.100这台BMC的日志"
- Agent识别到需要下载，调用download_log工具

### 11.7 AI Client适配多API格式

不同模型API格式不同，需适配：

```python
# src/ai_analyzer/client.py

class AIClient:
    def __init__(self, config):
        self.provider = self.detect_provider(config['base_url'])
        ...

    def detect_provider(self, base_url):
        """检测API提供商"""
        if 'openai' in base_url or 'api.openai.com' in base_url:
            return 'openai'
        elif 'minimax' in base_url:
            return 'minimax'
        elif 'glm' in base_url or 'zhipu' in base_url:
            return 'zhipu'
        else:
            return 'openai_compatible'  # 默认兼容OpenAI格式

    def chat_with_tools(self, messages, tools, tool_choice="auto"):
        """根据provider格式化请求"""
        if self.provider == 'openai':
            return self._chat_openai(messages, tools, tool_choice)
        elif self.provider == 'minimax':
            return self._chat_minimax(messages, tools, tool_choice)
        elif self.provider == 'zhipu':
            return self._chat_zhipu(messages, tools, tool_choice)
        else:
            return self._chat_openai_compatible(messages, tools, tool_choice)

    def _chat_minimax(self, messages, tools, tool_choice):
        """minimax API格式"""
        # minimax的tool_calls格式可能与OpenAI略有不同
        ...

    def _chat_zhipu(self, messages, tools, tool_choice):
        """智谱GLM API格式"""
        # GLM的tool_calls格式
        ...
```

### 11.8 第二阶段实施步骤

**Phase 2.1: MCP基础设施**
1. 创建 `src/ai_analyzer/mcp_client.py`
2. 实现stdio/websocket transport
3. 配置文件支持MCP Server定义

**Phase 2.2: Agent改造**
1. LogAnalyzerAgent集成MCP工具
2. 工具执行器支持MCP调用
3. 多源日志入口（local/mcp）

**Phase 2.3: Admin界面**
1. MCP Server配置页面
2. Server连接测试
3. 工具列表预览

**Phase 2.4: API适配**
1. minimax格式适配
2. GLM格式适配
3. 测试不同模型

**Phase 2.5: 示例MCP Server**
1. 实现示例：log_downloader MCP Server
2. 测试日志下载流程

### 11.9 依赖项

可能需要引入的依赖：
- `mcp` - MCP协议Python SDK（如果有官方SDK）
- 或自行实现transport层

### 11.10 第二阶段风险点

1. **MCP协议版本**：需确认minimax/GLM支持的MCP版本
2. **连接稳定性**：MCP Server连接可能不稳定，需重试机制
3. **权限控制**：MCP工具可能有风险操作，需权限控制
4. **日志下载安全**：远程下载需处理认证和加密

---

## 完整实施顺序

| 阶段 | 步骤 | 优先级 | 状态 |
|-----|------|-------|------|
| 一 | AI Client改造（支持tool_calls） | P0 | ✅ 完成 |
| 一 | LogAnalyzerAgent实现（多轮交互） | P0 | ✅ 完成 |
| 一 | Prompt文件创建 | P0 | ✅ 完成 |
| 一 | 分析模板JSON配置 | P1 | ✅ 完成 |
| 一 | 验证机制实现 | P0 | ✅ 完成 |
| 一 | HTML模板调整 | P1 | ✅ 完成 |
| 一 | 调用入口简化 | P0 | ✅ 完成 |
| 一 | Web API改为轮询 | P1 | ⏳ 待优化 |
| 一 | 删除旧文件 | P2 | ✅ 完成 |
| 二 | MCP客户端框架 | P1 | 待实施 |
| 二 | Agent集成MCP工具 | P1 | 待实施 |
| 二 | Admin MCP配置界面 | P2 | 待实施 |
| 二 | 多API格式适配 | P1 | 待实施 |
| 二 | 示例MCP Server | P2 | 待实施 |
| 二 | 日志下载入口 | P2 | 待实施 |

---

## 验证方式

**第一阶段验证：**
1. ✅ 模块导入测试：LogAnalyzerAgent、analyze_with_agent、analyze_api均已通过导入测试
2. ✅ pytest单元测试：66 passed，1 failed（API连接测试需服务运行）
3. ✅ HTML模板修复：修复summary变量缺失，问题摘要统计可正常显示
4. ⏳ Web界面测试：需上传日志执行AI分析，检查输出HTML
5. ⏳ ai_temp检查：需确认记录结构正确，可追溯分析过程
6. ⏳ 边界测试：需测试空日志、大量日志、异常日志

**第二阶段验证：**
1. MCP连接测试：连接示例Server，调用工具
2. 日志下载测试：通过MCP下载日志并分析
3. 多模型测试：minimax/GLM的tool_calls兼容性
4. Admin界面测试：MCP配置、工具预览功能

---

## 已完成的文件变更清单

### 新增文件
- `src/ai_analyzer/log_analyzer_agent.py` - LogAnalyzerAgent和ToolExecutor实现
- `config/agent_prompt.txt` - Agent系统prompt
- `config/analysis_templates.json` - 分析模板配置

### 修改文件
- `src/ai_analyzer/client.py` - 新增AIResponse类、chat_with_tools方法、count_tokens方法
- `src/ai_analyzer/analyzer.py` - 新增analyze_with_agent、extract_machine_info_from_plugins、load_analysis_templates函数
- `src/ai_analyzer/__init__.py` - 更新导出列表
- `src/web/routes/analyze_api.py` - 替换AgentCoordinator为analyze_with_agent调用
- `plugins/renderer/ai_report_template.html` - 新增分析摘要、潜在风险、分析覆盖范围区块
- `config/ai_config.json` - 新增agent配置项

### 删除文件
- `src/ai_analyzer/scout_agent.py`
- `src/ai_analyzer/sage_agent.py`
- `src/ai_analyzer/agent_coordinator.py`
- `config/scout_prompt.txt`
- `config/sage_prompt.txt`
- `config/sage_html_prompt.txt` - 旧降级HTML生成prompt
- `tests/test_sage_raw_response.py` - 旧Sage Agent测试文件

### 本次修复 (2026-04-28)
- `src/ai_analyzer/log_analyzer_agent.py` - _render_html方法添加summary变量计算，修复问题摘要统计显示
- `docs/agent_refactor_plan.md` - 更新验证状态记录