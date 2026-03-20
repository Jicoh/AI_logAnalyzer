"""
Plugin base classes and interfaces.

This module defines the abstract base class and data structures
that all plugins must implement.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
from enum import Enum
from datetime import datetime


class PluginCategory(Enum):
    """Plugin category enumeration."""
    PARSER = "parser"           # Log parsing plugins
    ANALYZER = "analyzer"       # Log analysis plugins
    DETECTOR = "detector"       # Problem detection plugins
    REPORTER = "reporter"       # Report generation plugins
    OTHER = "other"             # Other plugins


@dataclass
class PluginInfo:
    """Plugin information metadata."""
    id: str
    name: str
    version: str
    description: str
    category: PluginCategory = PluginCategory.OTHER
    author: str = ""
    enabled: bool = True
    tags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'id': self.id,
            'name': self.name,
            'version': self.version,
            'description': self.description,
            'category': self.category.value,
            'author': self.author,
            'enabled': self.enabled,
            'tags': self.tags
        }


@dataclass
class AnalysisResult:
    """Analysis result from a plugin."""
    plugin_id: str
    plugin_name: str
    analysis_time: str
    log_file: str
    error_count: int = 0
    warning_count: int = 0
    errors: List[Dict] = field(default_factory=list)
    warnings: List[Dict] = field(default_factory=list)
    statistics: Dict[str, Any] = field(default_factory=dict)
    raw_output: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'plugin_id': self.plugin_id,
            'plugin_name': self.plugin_name,
            'analysis_time': self.analysis_time,
            'log_file': self.log_file,
            'error_count': self.error_count,
            'warning_count': self.warning_count,
            'errors': self.errors,
            'warnings': self.warnings,
            'statistics': self.statistics,
            'raw_output': self.raw_output
        }


class BasePlugin(ABC):
    """
    Abstract base class for all plugins.

    All plugins must inherit from this class and implement the required
    abstract methods and properties.
    """

    @property
    @abstractmethod
    def id(self) -> str:
        """Unique plugin identifier."""
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable plugin name."""
        pass

    @property
    @abstractmethod
    def version(self) -> str:
        """Plugin version string."""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """Plugin description."""
        pass

    @property
    @abstractmethod
    def category(self) -> PluginCategory:
        """Plugin category."""
        pass

    @abstractmethod
    def analyze(self, log_file: str) -> AnalysisResult:
        """
        Analyze a log file.

        Args:
            log_file: Path to the log file to analyze.

        Returns:
            AnalysisResult containing the analysis results.
        """
        pass

    # Optional methods with default implementations

    @property
    def author(self) -> str:
        """Plugin author."""
        return ""

    @property
    def tags(self) -> List[str]:
        """Plugin tags for filtering/searching."""
        return []

    def validate_config(self) -> bool:
        """
        Validate plugin configuration.

        Returns:
            True if configuration is valid, False otherwise.
        """
        return True

    def initialize(self) -> None:
        """Initialize the plugin. Called once when plugin is loaded."""
        pass

    def cleanup(self) -> None:
        """Clean up plugin resources. Called when plugin is unloaded."""
        pass

    def get_info(self) -> PluginInfo:
        """Get plugin information as PluginInfo object."""
        return PluginInfo(
            id=self.id,
            name=self.name,
            version=self.version,
            description=self.description,
            category=self.category,
            author=self.author,
            enabled=True,
            tags=self.tags
        )