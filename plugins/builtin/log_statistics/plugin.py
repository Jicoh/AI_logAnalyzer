"""
Log Statistics Plugin

A plugin that provides statistical analysis of log files,
including time distribution, component activity, and pattern detection.
"""

import re
import os
from datetime import datetime
from collections import Counter
from typing import Dict, Any, List

from plugins.base import BasePlugin, PluginCategory, AnalysisResult


class LogStatisticsPlugin(BasePlugin):
    """Log Statistics Analysis Plugin."""

    @property
    def id(self) -> str:
        return "log_statistics"

    @property
    def name(self) -> str:
        return "Log Statistics"

    @property
    def version(self) -> str:
        return "1.0.0"

    @property
    def description(self) -> str:
        return "Analyze log file statistics: time distribution, component activity, and patterns"

    @property
    def category(self) -> PluginCategory:
        return PluginCategory.ANALYZER

    @property
    def author(self) -> str:
        return "AI Log Analyzer Team"

    @property
    def tags(self) -> List[str]:
        return ["statistics", "analysis", "metrics", "patterns"]

    @property
    def capabilities(self) -> List[str]:
        return ["statistics_analysis", "time_distribution", "pattern_detection", "component_activity"]

    @property
    def target_keywords(self) -> List[str]:
        return ["statistics", "distribution", "pattern", "trend", "frequency",
                "count", "metrics", "performance", "activity"]

    def analyze(self, log_file: str) -> AnalysisResult:
        """
        Analyze log file statistics.

        Args:
            log_file: Path to the log file.

        Returns:
            AnalysisResult with statistical analysis.
        """
        analysis_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        log_filename = os.path.basename(log_file)

        # Read log file
        lines = self.read_log_file(log_file)

        # Analyze statistics
        time_distribution = self.analyze_time_distribution(lines)
        component_activity = self.analyze_component_activity(lines)
        log_size_info = self.analyze_log_size(lines, log_file)

        statistics = {
            'total_lines': len(lines),
            'total_size_bytes': log_size_info['size_bytes'],
            'total_size_human': log_size_info['size_human'],
            'avg_line_length': round(sum(len(l) for l in lines) / len(lines), 2) if lines else 0,
            'time_distribution': time_distribution,
            'component_activity': component_activity,
            'analysis_type': 'statistical'
        }

        return AnalysisResult(
            plugin_id=self.id,
            plugin_name=self.name,
            analysis_time=analysis_time,
            log_file=log_filename,
            error_count=0,
            warning_count=0,
            errors=[],
            warnings=[],
            statistics=statistics
        )

    def read_log_file(self, log_file: str) -> List[str]:
        """Read log file content."""
        with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
            return f.readlines()

    def analyze_time_distribution(self, lines: List[str]) -> Dict[str, int]:
        """Analyze time distribution of log entries."""
        hour_counter = Counter()

        # Time patterns
        time_patterns = [
            r'(\d{2}):\d{2}:\d{2}',  # HH:MM:SS
            r'\d{4}-\d{2}-\d{2}T(\d{2}):\d{2}:\d{2}',  # ISO format
        ]

        for line in lines:
            for pattern in time_patterns:
                match = re.search(pattern, line)
                if match:
                    hour = match.group(1)
                    hour_counter[f"{hour}:00-{hour}:59"] += 1
                    break

        return dict(hour_counter.most_common(24))

    def analyze_component_activity(self, lines: List[str]) -> Dict[str, int]:
        """Analyze component activity."""
        component_counter = Counter()

        for line in lines:
            # Match content in square brackets (component names)
            matches = re.findall(r'\[([^\]]+)\]', line)
            for match in matches:
                # Skip timestamp-like content
                if not re.match(r'^\d{4}-\d{2}-\d{2}', match):
                    component_counter[match] += 1

        return dict(component_counter.most_common(15))

    def analyze_log_size(self, lines: List[str], log_file: str) -> Dict[str, Any]:
        """Analyze log file size."""
        size_bytes = os.path.getsize(log_file)

        # Convert to human readable
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024:
                size_human = f"{size_bytes:.2f} {unit}"
                break
            size_bytes /= 1024
        else:
            size_human = f"{size_bytes:.2f} TB"

        return {
            'size_bytes': os.path.getsize(log_file),
            'size_human': size_human
        }


# Export plugin class for discovery
plugin_class = LogStatisticsPlugin