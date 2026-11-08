"""Local configuration contracts and semantic validation."""

from .loader import ConfigError, LoadedConfig, load_scenario

__all__ = ["ConfigError", "LoadedConfig", "load_scenario"]
