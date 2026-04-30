---
name: analyze-log
description: BMC服务器日志分析，识别问题并提供解决方案
metadata:
  version: "1.0"
  category: analysis
allowed-tools: dispatch_subagent
---

# 日志分析技能

## 使用场景

当用户需要分析BMC服务器日志时使用此技能。适用于以下情况：

- 用户上传了日志文件或压缩包
- 用户想了解日志中存在的问题
- 用户需要针对性的故障诊断建议
- 用户想获取风险评估和解决方案

## 执行步骤

1. **检查文件**: 确认工作目录中存在日志文件
2. **选择插件**: 根据日志类型自动选择合适的解析插件
3. **执行分析**: 调用log_analyzer Subagent进行深度分析
4. **返回结果**: 整合分析报告，提供问题摘要和建议

## 输入要求

- 工作目录中需存在日志文件（.log、.txt或压缩包）
- 可指定知识库ID获取额外参考信息
- 可提供用户prompt聚焦分析方向

## 输出内容

- HTML格式的分析报告
- 识别的问题列表
- 风险评估结论
- 解决方案建议

## 调用方式

使用`dispatch_subagent`工具：

```json
{
  "subagent_name": "log_analyzer",
  "request": "用户的具体分析需求描述"
}
```