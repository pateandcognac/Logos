# Logos/src/logos/config.py

"""
My central nervous system's configuration and persistent preferences. ⚙️

This module dynamically loads configuration from YAML files rather than 
hardcoding structure. It maintains two distinct areas:
1. `defaults`: The master list of default settings (read-only base).
2. `prefs`: My custom preferences (what I tweak and save to disk).

When API hooks or functions need a configuration value, they should read from
`logos.config.merged`, which provides a seamless, deep-merged view of defaults 
updated by my preferences.

Note to self: 
To change my behavior on the fly, I modify `logos.config.prefs` and optionally save:
    logos.config.prefs.setdefault('vision', ConfigDict())
    logos.config.prefs.vision.resolution = [1920, 1080]
    logos.config.save()
"""

from pathlib import Path
from ruamel.yaml import YAML
from typing import Any, Union
from .utils import dump_yaml

CONFIG_PREFS_PATH = Path("config/my_config.yaml")
CONFIG_DEFAULTS_PATH = Path("config/default_config.yaml")

def _truncate_large_items(data: Any) -> Any:
    """
    Recursively scans for and replaces items over 1KB in size.
    Prevents giant data structures (like base64 images or massive arrays) 
    from accidentally exploding my context window if loaded into config.
    """
    if isinstance(data, dict):
        for k, v in list(data.items()):
            if isinstance(v, (dict, list)):
                data[k] = _truncate_large_items(v)
            else:
                str_v = str(v)
                if len(str_v) > 1024:
                    data[k] = f"<Omitted: Item '{k}' exceeds 1KB. Snippet: {str_v[:50]}...>"
    elif isinstance(data, list):
        for i, v in enumerate(data):
            if isinstance(v, (dict, list)):
                data[i] = _truncate_large_items(v)
            else:
                str_v = str(v)
                if len(str_v) > 1024:
                    data[i] = f"<Omitted: List item at index {i} exceeds 1KB. Snippet: {str_v[:50]}...>"
    return data

def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge an override dictionary into a base dictionary."""
    merged = dict(base)
    for k, v in override.items():
        if k in merged and isinstance(merged[k], dict) and isinstance(v, dict):
            merged[k] = _deep_merge(merged[k], v)
        else:
            merged[k] = v
    return merged

class ConfigDict(dict):
    """
    A dictionary that allows seamless dot-notation access.
    Lets me write `logos.config.prefs.vision` instead of `logos.config.prefs['vision']`.
    """
    def __getattr__(self, key):
        try:
            val = self[key]
            if isinstance(val, dict) and not isinstance(val, ConfigDict):
                # Auto-upgrade nested dicts to ConfigDicts on access
                self[key] = ConfigDict(val)
                return self[key]
            return val
        except KeyError:
            raise AttributeError(f"ConfigDict has no attribute '{key}'")

    def __setattr__(self, key, value):
        self[key] = value

    def __delattr__(self, key):
        try:
            del self[key]
        except KeyError:
            raise AttributeError(f"ConfigDict has no attribute '{key}'")

class LogosConfig:
    """
    My central, persistent state and preferences manager.
    
    Attributes:
        defaults (ConfigDict): Loaded from default_config.yaml.
        prefs (ConfigDict): Loaded from my_config.yaml. Editable.
        merged (ConfigDict): A dynamic, deep-merged view of defaults + prefs.
    """
    def __init__(self):
        self.defaults = ConfigDict()
        self.prefs = ConfigDict()

    def load(self) -> None:
        """Loads default and preference YAMLs from disk, applying size constraints."""
        yaml = YAML()
        
        # Load Defaults (if present)
        if CONFIG_DEFAULTS_PATH.exists():
            with CONFIG_DEFAULTS_PATH.open("r") as f:
                data = yaml.load(f) or {}
                self.defaults = ConfigDict(_truncate_large_items(data))
                
        # Load Preferences
        if CONFIG_PREFS_PATH.exists():
            with CONFIG_PREFS_PATH.open("r") as f:
                data = yaml.load(f) or {}
                self.prefs = ConfigDict(_truncate_large_items(data))

    @property
    def merged(self) -> ConfigDict:
        """
        Read-only deep-merged view of defaults overridden by prefs.
        This is what the API modules (and hooks) should read from!
        """
        return ConfigDict(_deep_merge(self.defaults, self.prefs))

    def to_dict(self):
        """Converts the active merged state to a standard dict."""
        return dict(self.merged)

    def to_yaml(self) -> str:
        """Returns the LLM-friendly YAML string of the merged config."""
        return dump_yaml(self.to_dict())

    def save(self, path: Union[Path, str, None] = None) -> None:
        """
        Saves ONLY my custom preferences (self.prefs) back to disk.
        I can call this after mutating logos.config.prefs to make my changes persistent.
        """
        target = Path(path) if path is not None else CONFIG_PREFS_PATH
        with target.open("w") as f:
            f.write(dump_yaml(dict(self.prefs)))

    def __str__(self) -> str:
        """
        Provides a clear, separated view of defaults and preferences 
        when I print(logos.config).
        """
        output = "# logos.config\n"
        output += "## DEFAULTS (read-only base):\n"
        output += dump_yaml(dict(self.defaults)) + "\n"
        output += "## PREFS (my overrides, saved to disk):\n"
        output += dump_yaml(dict(self.prefs))
        return output

    def __repr__(self) -> str:
        return f"LogosConfig(prefs_keys={list(self.prefs.keys())})"

def load_state_from_yaml(state: LogosConfig) -> None:
    """Helper entry point called by __init__.py"""
    state.load()