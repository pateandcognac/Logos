# preload_api/logos/state.py

"""
Defines the structure for my persistent, global state object, `logos.state`.
This object acts as a centralized "control panel" that I can modify to
change the default behavior of my API functions and context hooks.
"""


from ruamel.yaml import YAML
import io

yaml = YAML()

class SystemState:
    """Settings related to the framework and system behavior."""
    def __init__(self):
        self.save_state_on_loop: bool = True


class FileState:
    """Settings related to the filesystem API."""
    def __init__(self):
        self.show_extensions: list[str] = ['.py', '.yaml', '.md', '.txt', '.json', '.png', '.jpg']
        self.max_depth: int = 5
        self.inline_meta_masks: list[str] = ['*.meta', 'README.md']


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
        self.summarizable_types: list[str] = [
            'me', 'py_result', 'py_async', 'human', 'human_stt'
        ]
        
        # --- Scoring: How do we prioritize candidates? ---
        self.age_weight: float = 0.6
        self.size_weight: float = 0.4

        # --- Recursion: How do we manage summaries themselves? ---
        self.max_contiguous_summaries: int = 4



class LogosState:
    """
    My central, persistent state object. I can modify its attributes to
    control the default behavior of my API functions and hooks. When printed,
    logos.state is rendered as YAML.
    """
    def __init__(self):
        self.files = FileState()
        self.system = SystemState()
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
        """Returns the current state as a YAML string."""
        state_dict = self.to_dict()
        string_stream = io.StringIO()
        yaml.dump(state_dict, string_stream)
        return string_stream.getvalue()


    def __str__(self) -> str:
        """Human/LLM-friendly string form."""
        return f"# logos.state\n{self.to_yaml()}"

    def __repr__(self) -> str:
        """Developer/debug-friendly representation."""
        return f"LogosState({self.to_dict()})"