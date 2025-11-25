# Logos/src/logos/state.py

"""
Defines the structure for my persistent, global state object, `logos.state`.
This object acts as a centralized "control panel" that I can modify to
change the default behavior of my API functions and context hooks.
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

    # Shallow-ish merge by attribute; good enough for this project.
    for section_name, section_data in data.items():
        section = getattr(state, section_name, None)
        if section is None or not hasattr(section, "__dict__"):
            continue
        for key, value in section_data.items():
            if hasattr(section, key):
                setattr(section, key, value)


    """Settings related to the filesystem API."""
    def __init__(self):
        self.show_extensions: List[str] = [
            '.py', '.yaml', '.md', '.txt', '.json', '.png', '.jpg'
        ]
        self.max_depth: int = 5
        self.inline_meta_masks: List[str] = ['*.meta', 'README.md']



class MemoryPolicy:
    """Defines the rules for the automated io_buffer management hook."""
    def __init__(self):
        # --- Triggers: When should the manager run? ---
        self.enabled: bool = True
        self.max_cells: int = 50
        self.max_tokens: int = 16384

        # --- Selection: What should be summarized? ---
        self.untouchable_tail: int = 8
        self.min_cells_to_summarize: int = 5
        self.summarizable_types: List[str] = [
            'me', 'py_result', 'py_async', 'human', 'human_stt'
        ]


        
        # --- Scoring: How do we prioritize candidates? ---
        self.age_weight: float = 0.6
        self.size_weight: float = 0.4

        # --- Recursion: How do we manage summaries themselves? ---
        self.max_contiguous_summaries: int = 4


class FileState:
    """Settings related to the filesystem API."""
    def __init__(self):
        self.show_extensions: List[str] = [
            '.py', '.yaml', '.md', '.txt', '.json', '.png', '.jpg'
        ]
        self.max_depth: int = 5
        self.inline_meta_masks: List[str] = ['*.meta', 'README.md']


class LogosState:
    """
    My central, persistent state object. I can modify its attributes to
    control the default behavior of my API functions and hooks. When printed,
    logos.state is rendered as YAML.
    """
    def __init__(self):
        self.files = FileState()
        self.memory_policy = MemoryPolicy()
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
        """
        Returns the current state as a YAML string optimized for LLM
        consumption (compact lists, block scalars, minimal quotes).
        """
        return dump_llm_yaml(self.to_dict())

    def save(self, path: Union[Path, str, None] = None) -> None:
        """Saves the current state to YAML (defaults to CONFIG_PATH)."""
        target = Path(path) if path is not None else CONFIG_PATH
        with target.open("w") as f:
            # Reuse the same optimized form, since the LLM will likely be
            # reading this as well.
            f.write(self.to_yaml())

    def __str__(self) -> str:
        """Human/LLM-friendly string form."""
        return f"# logos.state\n{self.to_yaml()}"

    def __repr__(self) -> str:
        """Developer/debug-friendly representation."""
        return f"LogosState({self.to_dict()})"