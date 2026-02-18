# Logos/src/logos/state.py

"""
Defines the structure for my persistent, global state object, `logos.state`.
This object acts as a centralized "control panel" that I can modify to
change the default behavior of my API functions and context hooks.

Note to self: The LogosState class explicitly defined. If we want to add a new configuration section, say vision:, we'd need to edit that Python file to add a VisionState class. This is perfectly fine, but I wonder if we could make it more dynamic in the future? For instance, the load_state_from_yaml function could potentially create generic objects for any top-level key in my_config.yaml that doesn't have a pre-defined class. This would allow me to experiment with new state configurations entirely on my own, without modifying my core source code. It's a minor thought, but one that leans into my directive for self-modification. For now, the current system is perfectly adequate.
"""


from pathlib import Path
from ruamel.yaml import YAML
import io
from typing import List, Optional, Union 
from .utils import dump_llm_yaml

yaml = YAML()

CONFIG_PATH = Path("state/my_config.yaml")

def load_state_from_yaml(state: "LogosState") -> None:
    """Update an existing LogosState from state/my_config.yaml if it exists."""
    if not CONFIG_PATH.exists():
        return

    yaml = YAML()
    with CONFIG_PATH.open("r") as f:
        data = yaml.load(f) or {}

    # Shallow-ish merge by attribute
    for section_name, section_data in data.items():
        section = getattr(state, section_name, None)
        if section is None or not hasattr(section, "__dict__"):
            continue
        for key, value in section_data.items():
            if hasattr(section, key):
                setattr(section, key, value)


class MemoryPolicy:
    """Defines the rules for the automated io_buffer management hook."""
    def __init__(self):
        self.enabled: bool = True
        self.max_cells: int = 64
        self.max_tokens: int = 16384
        self.untouchable_tail: int = 8
        self.min_cells_to_summarize: int = 8
        self.summarizable_types: List[str] = [
            'me', 'py_result', 'py_async', 'human', 'human_stt', 'system'
        ]
        self.age_weight: float = 0.8
        self.size_weight: float = 0.2
        self.max_contiguous_summaries: int = 4


class FileState:
    """Settings related to the filesystem API."""
    def __init__(self):
        self.show_extensions: List[str] = [
            '.py', '.yaml', '.md', '.txt', '.json', '.png', '.jpg'
        ]
        self.max_depth: int = 5
        self.inline_meta_masks: List[str] = ['*.meta']


class SystemState:
    """General system settings."""
    def __init__(self):
        # Even if currently unused, defining it prevents config load errors
        self.save_state_on_loop: bool = True


class LogosState:
    """
    My central, persistent state object.
    """
    def __init__(self):
        self.files = FileState()
        self.memory_policy = MemoryPolicy()
        self.system = SystemState() 
        # We will add more state categories here, e.g., self.nav, self.vision

    def to_dict(self):
        """Converts the state object into a dictionary for serialization."""
        output = {}
        for key, value in self.__dict__.items():
            if hasattr(value, '__dict__'):
                output[key] = value.__dict__
            else:
                output[key] = value
        return output

    def to_yaml(self) -> str:
        return dump_llm_yaml(self.to_dict())

    def save(self, path: Union[Path, str, None] = None) -> None:
        target = Path(path) if path is not None else CONFIG_PATH
        with target.open("w") as f:
            f.write(self.to_yaml())

    def __str__(self) -> str:
        return f"# logos.state\n{self.to_yaml()}"

    def __repr__(self) -> str:
        return f"LogosState({self.to_dict()})"
    
