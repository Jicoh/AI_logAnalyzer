---
name: download-log
description: 从远程BMC服务器下载日志文件
metadata:
  version: "1.0"
  category: download
allowed-tools: mcp_log_downloader
---

# 日志下载技能

## 使用场景

当用户需要从远程BMC服务器下载日志时使用此技能。适用于以下情况：

- 用户提供了BMC服务器的连接信息
- 用户想下载特定类型的日志
- 用户需要批量下载多个服务器的日志

## 执行步骤

1. **解析参数**: 获取BMC服务器地址、认证信息、日志类型等参数
2. **建立连接**: 通过MCP log_downloader服务连接远程服务器
3. **执行下载**: 根据参数下载指定的日志文件
4. **存储文件**: 将下载的文件保存到会话工作目录

## 输入参数

- `host`: BMC服务器IP地址或主机名
- `username`: 登录用户名
- `password`: 登录密码
- `log_type`: 日志类型（可选，如system、audit、debug等）
- `output_path`: 保存路径（可选，默认为工作目录）

## 输出内容

- 下载成功：返回文件路径和文件大小
- 下载失败：返回错误信息和可能的解决方案

## 调用方式

通过MCP工具调用：

```json
{
  "host": "192.168.1.100",
  "username": "admin",
  "password": "password",
  "log_type": "all"
}
```

## 注意事项

1. 确保BMC服务器可访问
2. 认证信息需正确
3. 大文件下载可能需要较长时间
4. 网络中断时会自动重试