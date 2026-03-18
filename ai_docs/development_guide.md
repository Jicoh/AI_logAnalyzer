# AI日志分析项目开发要求文档

## 一、代码风格要求

### 1.1 命名规范
- 函数名使用小写字母和下划线分隔（snake_case），**不要在函数名前加下划线**
- 类名使用大驼峰命名（PascalCase）
- 变量名使用小写字母和下划线分隔
- 常量使用全大写字母和下划线分隔

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

### 1.2 代码简洁性
- 代码需要简洁明了，避免冗余
- 不做太多的未来设计和防御性编程
- 只实现当前需求需要的功能
- 避免过度抽象和不必要的复杂性

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

### 1.3 代码格式
- 使用4个空格缩进，不使用Tab
- 每行代码不超过100个字符
- 函数之间空一行
- 类之间空两行

### 1.4 注释规范
- 只在必要时添加注释
- 代码应尽量自解释
- 不写显而易见的注释
- 复杂逻辑添加简短说明

---

## 二、开发流程要求

### 2.1 开发前准备
每次开发任务开始前，必须完成以下步骤：

1. **阅读需求文档**（requirements.md）
   - 理解当前步骤的具体任务
   - 了解与其他模块的接口定义
   - 确认数据结构格式

2. **阅读开发进展文档**（progress.md）
   - 了解已完成的功能
   - 确认当前开发步骤
   - 查看是否有遗留问题

3. **对齐开发目标**
   - 明确本次开发的具体任务范围
   - 确认不超出当前步骤的边界
   - 记录可能的疑问点

### 2.2 开发过程
- 专注于当前任务，不做额外功能
- 保持代码简洁，避免过度设计
- 遇到问题及时记录到progress.md

### 2.3 开发完成后检查清单

每次开发任务完成后，必须进行以下检查：

#### 代码检查
- [ ] 语法检查：运行代码确保无语法错误
- [ ] 逻辑检查：确认逻辑正确，无遗漏
- [ ] 接口检查：确认接口与需求文档一致
- [ ] 命名检查：确认命名符合规范，无下划线前缀

#### 功能检查
- [ ] 功能完整性：实现当前步骤的所有任务
- [ ] 功能正确性：功能运行符合预期
- [ ] 边界情况：处理必要的边界情况（不做过度防御）

#### 文档更新
- [ ] 更新progress.md中的任务状态
- [ ] 记录开发日志
- [ ] 更新代码统计

---

## 三、模块设计原则

### 3.1 单一职责
- 每个模块只负责一个功能
- 每个函数只做一件事
- 避免功能耦合

### 3.2 模块解耦
- 模块之间通过明确定义的接口通信
- 避免循环依赖
- 数据通过JSON文件传递，不直接调用

### 3.3 接口清晰
- 函数参数明确，有默认值
- 返回值类型一致
- 错误处理统一

---

## 四、代码审查要点

### 4.1 每次提交前自检

```markdown
## 自检清单

### 基础检查
- [ ] 代码能够正常运行
- [ ] 无语法错误
- [ ] 无明显的逻辑错误

### 命名检查
- [ ] 函数名无下划线前缀
- [ ] 命名清晰易懂
- [ ] 遵循命名规范

### 设计检查
- [ ] 代码简洁，无冗余
- [ ] 无过度设计
- [ ] 无不必要的防御性编程
- [ ] 功能完整但不超出需求

### 接口检查
- [ ] 接口与需求文档一致
- [ ] 数据格式正确
- [ ] 参数和返回值符合预期
```

### 4.2 常见问题避免

**避免的问题：**
1. 函数名加下划线前缀（如 `_load_config`）
2. 过度的异常捕获和处理
3. 不必要的参数验证
4. 未来功能的预留代码
5. 过度的抽象和封装
6. 不必要的配置选项

**正确做法：**
```python
# 简洁直接
def load_document(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        return f.read()
```

**避免的做法：**
```python
# 过度设计
def load_document(file_path, encoding=None, validate=False, cache=True):
    encoding = encoding or 'utf-8'
    if validate:
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")
        if not os.access(file_path, os.R_OK):
            raise PermissionError(f"No read permission: {file_path}")
    if cache and file_path in _cache:
        return _cache[file_path]
    try:
        with open(file_path, 'r', encoding=encoding) as f:
            content = f.read()
        if cache:
            _cache[file_path] = content
        return content
    except Exception as e:
        logger.error(f"Failed to load document: {e}")
        raise
```

---

## 五、文档维护要求

### 5.1 进度文档更新
每次开发完成后必须更新：
- 任务状态（待开发 → 开发中 → 已完成）
- 完成日期
- 代码统计
- 开发日志

### 5.2 问题记录
发现问题后及时记录到progress.md的问题与风险表格

### 5.3 需求变更
如有需求变更，需更新requirements.md并记录变更

---

## 六、测试要求

### 6.1 基本测试
- 确保代码能够正常运行
- 测试主要功能路径
- 验证输出格式正确

### 6.2 测试无需过度
- 不需要100%测试覆盖
- 专注于核心功能
- 边界情况适度测试即可

---

## 七、版本控制要求

### 7.1 提交规范
- 每个步骤完成后提交一次
- 提交信息清晰说明做了什么

### 7.2 分支管理
- 主分支保持稳定
- 大改动可创建临时分支

---

## 附录：快速参考

### 函数命名
✅ 正确：`def load_config():`
❌ 错误：`def _load_config():`

### 代码简洁
✅ 正确：实现当前需求，代码简洁
❌ 错误：预留未来功能，过度防御

### 开发流程
1. 读需求文档 → 2. 读进度文档 → 3. 对齐目标 → 4. 开发 → 5. 自检 → 6. 更新文档

### 完成检查
1. 语法逻辑检查
2. 接口一致性检查
3. 更新进度文档