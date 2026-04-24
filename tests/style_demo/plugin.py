"""
样式展示Demo插件。

展示所有插件输出样式的示例，包括：
- stats: 统计概览
- table: 数据表格
- timeline: 时间线
- cards: 卡片展示
- chart: 图表（bar/pie/line）
- search_box: 搜索框
- raw: 原始JSON数据
"""

import os
from datetime import datetime

from plugins.base import (
    BasePlugin, AnalysisResult, ResultMeta, StatsItem,
    TimelineEvent, CardItem, ChartData
)


class StyleDemoPlugin(BasePlugin):
    """样式展示Demo插件。"""

    def analyze(self, log_path: str) -> AnalysisResult:
        """生成所有样式的示例数据。"""
        self.log("开始生成样式示例...")

        # 创建元数据
        meta = ResultMeta(
            plugin_id=self.id,
            plugin_name=self.name,
            version=self.get_version(),
            analysis_time=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            log_files=["demo.log"],
            plugin_type=self.get_plugin_type(),
            description=self.get_chinese_description()
        )

        result = AnalysisResult(meta=meta)

        # ========== 1. Stats 统计概览 ==========
        result.add_stats("统计概览示例", [
            StatsItem(label="文件总数", value=15, unit="个", severity="info", icon="file"),
            StatsItem(label="日志行数", value=23456, unit="行", severity="info", icon="file-text"),
            StatsItem(label="错误数量", value=12, unit="个", severity="error", icon="x-circle"),
            StatsItem(label="警告数量", value=28, unit="个", severity="warning", icon="alert-triangle"),
            StatsItem(label="处理成功", value=156, unit="次", severity="success", icon="check-circle"),
        ], icon="chart-bar")

        # ========== 2. Table 数据表格 ==========
        result.add_table("错误日志详情",
            columns=[
                {"key": "line", "label": "行号", "type": "number", "width": "10%"},
                {"key": "time", "label": "时间", "type": "text", "width": "20%"},
                {"key": "level", "label": "级别", "type": "text", "width": "10%"},
                {"key": "message", "label": "消息内容", "type": "text", "truncate": 80}
            ],
            rows=[
                {"line": 1024, "time": "2024-04-20 10:15:30", "level": "ERROR", "message": "Connection timeout to server 192.168.1.100:8080", "severity": "error"},
                {"line": 2048, "time": "2024-04-20 11:22:45", "level": "WARN", "message": "Memory usage exceeds 80% threshold, current: 85%", "severity": "warning"},
                {"line": 3072, "time": "2024-04-20 12:30:00", "level": "ERROR", "message": "Database connection pool exhausted, max connections: 100", "severity": "error"},
                {"line": 4096, "time": "2024-04-20 13:45:12", "level": "INFO", "message": "Service restart completed successfully", "severity": "info"},
                {"line": 5120, "time": "2024-04-20 14:50:30", "level": "ERROR", "message": "File not found: /data/config/settings.json", "severity": "error"},
            ],
            severity="error",
            icon="table")

        # ========== 3. Timeline 时间线 ==========
        result.add_timeline("事件时间线",
            events=[
                TimelineEvent(
                    timestamp="2024-04-20 09:00:00",
                    title="系统启动",
                    description="服务器启动完成，所有服务正常运行",
                    severity="success",
                    icon="play-circle",
                    detail="启动耗时: 12.5秒"
                ),
                TimelineEvent(
                    timestamp="2024-04-20 10:15:30",
                    title="连接超时",
                    description="无法连接到远程服务器",
                    severity="error",
                    icon="wifi-off",
                    detail="目标地址: 192.168.1.100:8080"
                ),
                TimelineEvent(
                    timestamp="2024-04-20 11:22:45",
                    title="内存告警",
                    description="内存使用率超过阈值",
                    severity="warning",
                    icon="cpu",
                    detail="当前使用率: 85%"
                ),
                TimelineEvent(
                    timestamp="2024-04-20 13:00:00",
                    title="数据同步",
                    description="完成数据库数据同步",
                    severity="info",
                    icon="refresh",
                    detail="同步记录数: 1500条"
                ),
                TimelineEvent(
                    timestamp="2024-04-20 15:30:00",
                    title="配置更新",
                    description="系统配置已更新并生效",
                    severity="info",
                    icon="gear",
                    detail="更新项: cache_size, timeout, log_level"
                ),
            ],
            icon="clock")

        # ========== 4. Cards 卡片展示 ==========
        result.add_cards("问题分类卡片",
            cards=[
                CardItem(
                    title="网络问题",
                    severity="error",
                    icon="wifi-off",
                    content={
                        "summary": "发现3个网络连接问题",
                        "description": "主要涉及服务器连接超时和DNS解析失败",
                        "metrics": {
                            "连接超时": 2,
                            "DNS失败": 1,
                            "重试次数": 15
                        },
                        "details": [
                            "192.168.1.100:8080 连接超时",
                            "DNS解析api.example.com失败",
                            "重连尝试已达到最大次数"
                        ]
                    }
                ),
                CardItem(
                    title="资源告警",
                    severity="warning",
                    icon="cpu",
                    content={
                        "summary": "资源使用率偏高",
                        "description": "CPU和内存使用率接近阈值",
                        "metrics": {
                            "CPU": "75%",
                            "内存": "85%",
                            "磁盘": "60%"
                        },
                        "details": [
                            "建议检查是否有异常进程",
                            "可考虑扩容或优化资源分配"
                        ]
                    }
                ),
                CardItem(
                    title="配置状态",
                    severity="success",
                    icon="check-circle",
                    content={
                        "summary": "配置正常",
                        "description": "所有配置项已验证并生效",
                        "metrics": {
                            "有效配置": 12,
                            "无效配置": 0
                        },
                        "details": [
                            "数据库配置正确",
                            "网络配置已同步",
                            "安全配置已更新"
                        ]
                    }
                ),
            ],
            icon="layers")

        # ========== 5. Chart 图表 ==========
        # 柱状图
        result.add_chart("日志级别分布（柱状图）",
            chart_type="bar",
            data=ChartData(
                labels=["ERROR", "WARN", "INFO", "DEBUG"],
                values=[12, 28, 156, 89]
            ),
            options={"x_label": "级别", "y_label": "数量"},
            icon="chart-bar")

        # 饼图
        result.add_chart("错误类型占比（饼图）",
            chart_type="pie",
            data=ChartData(
                labels=["网络错误", "数据库错误", "配置错误", "其他"],
                values=[5, 3, 2, 2]
            ),
            icon="pie-chart")

        # 折线图
        result.add_chart("时间趋势（折线图）",
            chart_type="line",
            data=ChartData(
                labels=["09:00", "10:00", "11:00", "12:00", "13:00", "14:00", "15:00"],
                values=[5, 15, 25, 10, 30, 20, 15]
            ),
            icon="graph-up")

        # ========== 6. SearchBox 搜索框 ==========
        result.add_search_box("日志搜索",
            data=[
                {"time": "09:00:00", "level": "INFO", "message": "System startup completed"},
                {"time": "10:15:30", "level": "ERROR", "message": "Connection timeout"},
                {"time": "11:22:45", "level": "WARN", "message": "Memory threshold exceeded"},
                {"time": "12:30:00", "level": "ERROR", "message": "Database pool exhausted"},
                {"time": "13:45:12", "level": "INFO", "message": "Service restart done"},
                {"time": "14:50:30", "level": "ERROR", "message": "Config file missing"},
                {"time": "15:00:00", "level": "INFO", "message": "Backup completed"},
                {"time": "16:10:00", "level": "WARN", "message": "Slow response detected"},
            ],
            search_fields=["time", "level", "message"],
            placeholder="输入关键字搜索日志...",
            icon="search")

        # ========== 7. Raw 原始数据 ==========
        result.add_raw("原始诊断数据",
            data={
                "diagnosis": {
                    "status": "warning",
                    "score": 65,
                    "recommendations": [
                        "检查网络连接稳定性",
                        "优化内存使用",
                        "更新过期配置"
                    ]
                },
                "environment": {
                    "os": "Linux 5.4.0",
                    "python": "3.9.5",
                    "memory_total": "16GB",
                    "cpu_cores": 8
                }
            })

        self.log("样式示例生成完成")
        return result


plugin_class = StyleDemoPlugin