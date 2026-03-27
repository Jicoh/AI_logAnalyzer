"""
Plugin Manager for discovering, loading, and managing plugins.

This module provides the PluginManager class that handles:
- Plugin discovery in builtin and custom directories
- Dynamic plugin loading
- Plugin execution and result aggregation
"""

import os
import sys
import json
import importlib.util
from typing import Dict, List, Optional, Any
from datetime import datetime

from plugins.base import BasePlugin, PluginCategory, PluginInfo, AnalysisResult, MultiPluginAnalysisResult


class PluginManager:
    """
    Manages plugin discovery, loading, and execution.

    The PluginManager scans configured directories for plugins,
    loads them dynamically, and provides methods to query and
    execute plugins.
    """

    def __init__(self, plugin_dirs: Optional[List[str]] = None):
        """
        Initialize the PluginManager.

        Args:
            plugin_dirs: Optional list of directories to scan for plugins.
                        If None, uses default directories (builtin and custom).
        """
        self._plugins: Dict[str, BasePlugin] = {}
        self._plugin_dirs = plugin_dirs

        if self._plugin_dirs is None:
            # Default plugin directories
            root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            self._plugin_dirs = [
                os.path.join(root_dir, 'plugins', 'builtin'),
                os.path.join(root_dir, 'plugins', 'custom')
            ]

    def load_plugins(self) -> int:
        """
        Scan plugin directories and load all valid plugins.

        Returns:
            Number of plugins successfully loaded.
        """
        loaded_count = 0

        for plugin_dir in self._plugin_dirs:
            if not os.path.exists(plugin_dir):
                continue

            loaded_count += self._scan_directory(plugin_dir)

        return loaded_count

    def _scan_directory(self, directory: str) -> int:
        """
        Scan a directory for plugins.

        Args:
            directory: Directory to scan.

        Returns:
            Number of plugins loaded from this directory.
        """
        loaded_count = 0

        for item in os.listdir(directory):
            item_path = os.path.join(directory, item)

            # Check if it's a potential plugin directory
            if os.path.isdir(item_path):
                plugin = self._load_plugin(item_path)
                if plugin:
                    self._plugins[plugin.id] = plugin
                    loaded_count += 1

        return loaded_count

    def _load_plugin(self, plugin_path: str) -> Optional[BasePlugin]:
        """
        Load a plugin from a directory.

        Args:
            plugin_path: Path to the plugin directory.

        Returns:
            Loaded plugin instance or None if loading failed.
        """
        plugin_file = os.path.join(plugin_path, 'plugin.py')
        metadata_file = os.path.join(plugin_path, 'plugin.json')

        # Check for required plugin.py file
        if not os.path.exists(plugin_file):
            return None

        try:
            # Load the plugin module
            spec = importlib.util.spec_from_file_location(
                f"plugin_{os.path.basename(plugin_path)}",
                plugin_file
            )
            if spec is None or spec.loader is None:
                return None

            module = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = module
            spec.loader.exec_module(module)

            # Look for a plugin class
            plugin_class = None
            for name in dir(module):
                obj = getattr(module, name)
                if (isinstance(obj, type) and
                    issubclass(obj, BasePlugin) and
                    obj is not BasePlugin):
                    plugin_class = obj
                    break

            if plugin_class is None:
                return None

            # Instantiate the plugin
            plugin = plugin_class()

            # Load metadata if available
            if os.path.exists(metadata_file):
                try:
                    with open(metadata_file, 'r', encoding='utf-8') as f:
                        metadata = json.load(f)
                    # Metadata can override plugin attributes if needed
                    plugin._metadata = metadata
                except (json.JSONDecodeError, IOError):
                    pass

            # Initialize the plugin
            plugin.initialize()

            return plugin

        except Exception as e:
            print(f"Error loading plugin from {plugin_path}: {e}")
            return None

    def get_plugin(self, plugin_id: str) -> Optional[BasePlugin]:
        """
        Get a plugin by its ID.

        Args:
            plugin_id: The unique identifier of the plugin.

        Returns:
            The plugin instance or None if not found.
        """
        return self._plugins.get(plugin_id)

    def get_all_plugins(self) -> List[BasePlugin]:
        """
        Get all loaded plugins.

        Returns:
            List of all loaded plugin instances.
        """
        return list(self._plugins.values())

    def get_plugins_info(self) -> List[PluginInfo]:
        """
        Get information about all loaded plugins.

        Returns:
            List of PluginInfo objects.
        """
        return [plugin.get_info() for plugin in self._plugins.values()]

    def get_plugins_by_category(self, category: PluginCategory) -> List[BasePlugin]:
        """
        Get plugins filtered by category.

        Args:
            category: The category to filter by.

        Returns:
            List of plugins in the specified category.
        """
        return [p for p in self._plugins.values() if p.category == category]

    def get_plugins_by_category_dict(self) -> Dict[str, Dict[str, Any]]:
        """
        Get plugins grouped by category.

        Returns:
            Dictionary mapping category names to plugin lists.
        """
        categories = {}
        for plugin in self._plugins.values():
            cat_value = plugin.category.value
            if cat_value not in categories:
                categories[cat_value] = {
                    'label': plugin.category.name,
                    'plugins': []
                }
            categories[cat_value]['plugins'].append(plugin.get_info().to_dict())
        return categories

    def run_analysis(self, plugin_ids: List[str], log_file: str) -> MultiPluginAnalysisResult:
        """
        Run analysis using specified plugins.

        Args:
            plugin_ids: List of plugin IDs to run.
            log_file: Path to the log file to analyze.

        Returns:
            MultiPluginAnalysisResult containing per-plugin results.
        """
        if not plugin_ids:
            raise ValueError("No plugins specified for analysis")

        results = []
        for plugin_id in plugin_ids:
            plugin = self.get_plugin(plugin_id)
            if plugin:
                try:
                    result = plugin.analyze(log_file)
                    results.append(result)
                except Exception as e:
                    print(f"Error running plugin {plugin_id}: {e}")

        if not results:
            raise RuntimeError("No plugins successfully executed")

        # Combine results into multi-plugin structure
        return self._combine_results(results)

    def run_analysis_multiple_files(
        self,
        plugin_ids: List[str],
        log_files: List[str]
    ) -> MultiPluginAnalysisResult:
        """
        Run analysis on multiple log files using specified plugins.

        Args:
            plugin_ids: List of plugin IDs to run.
            log_files: List of log file paths to analyze.

        Returns:
            MultiPluginAnalysisResult containing per-plugin results.
        """
        all_results = []

        for log_file in log_files:
            for plugin_id in plugin_ids:
                plugin = self.get_plugin(plugin_id)
                if plugin:
                    try:
                        result = plugin.analyze(log_file)
                        all_results.append(result)
                    except Exception as e:
                        print(f"Error running plugin {plugin_id} on {log_file}: {e}")

        if not all_results:
            raise RuntimeError("No plugins successfully executed")

        return self._combine_results(all_results)

    def _combine_results(self, results: List[AnalysisResult]) -> MultiPluginAnalysisResult:
        """
        Combine multiple analysis results into MultiPluginAnalysisResult.

        Results are stored by plugin ID, preserving per-plugin structure.
        When the same plugin runs on multiple files, its results are merged.

        Args:
            results: List of AnalysisResult objects to combine.

        Returns:
            MultiPluginAnalysisResult with per-plugin structure.
        """
        if not results:
            return MultiPluginAnalysisResult(
                analysis_time=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                log_file='none'
            )

        multi_result = MultiPluginAnalysisResult(
            analysis_time=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            log_file=', '.join(set(r.log_file for r in results))
        )

        # Group results by plugin_id
        for result in results:
            plugin_id = result.plugin_id
            if plugin_id in multi_result.plugins:
                # Merge with existing result for same plugin
                existing = multi_result.plugins[plugin_id]
                existing.error_count += result.error_count
                existing.warning_count += result.warning_count
                existing.errors.extend(result.errors)
                existing.warnings.extend(result.warnings)
                # Merge statistics
                for key, value in result.statistics.items():
                    if key in existing.statistics:
                        if isinstance(value, (int, float)) and isinstance(existing.statistics[key], (int, float)):
                            existing.statistics[key] += value
                        elif isinstance(value, dict) and isinstance(existing.statistics[key], dict):
                            existing.statistics[key].update(value)
                    else:
                        existing.statistics[key] = value
                # Merge raw_output if both are dicts
                if isinstance(result.raw_output, dict) and isinstance(existing.raw_output, dict):
                    existing.raw_output.update(result.raw_output)
            else:
                # Create new entry for this plugin
                multi_result.plugins[plugin_id] = result

        return multi_result

    def cleanup(self) -> None:
        """Clean up all loaded plugins."""
        for plugin in self._plugins.values():
            try:
                plugin.cleanup()
            except Exception as e:
                print(f"Error cleaning up plugin {plugin.id}: {e}")
        self._plugins.clear()


# Global plugin manager instance
_plugin_manager: Optional[PluginManager] = None


def get_plugin_manager() -> PluginManager:
    """
    Get the global plugin manager instance.

    Creates the manager if it doesn't exist and loads plugins.

    Returns:
        The global PluginManager instance.
    """
    global _plugin_manager
    if _plugin_manager is None:
        _plugin_manager = PluginManager()
        count = _plugin_manager.load_plugins()
        print(f"Loaded {count} plugin(s)")
    return _plugin_manager


def reset_plugin_manager() -> None:
    """
    Reset the global plugin manager.

    Useful for testing or reloading plugins.
    """
    global _plugin_manager
    if _plugin_manager:
        _plugin_manager.cleanup()
    _plugin_manager = None