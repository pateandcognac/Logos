# Logos/src/logos/hooks.py

"""
This module contains functions for me to introspect and modify my own cognitive hook configurations. Does *not* contain the hook code itself.
"""

from pathlib import Path
from ruamel.yaml import YAML
from .core import Verbosity, api_call

__all__ = ["show", "upsert", "remove"]


# Initialize a YAML instance that preserves comments and formatting
yaml = YAML()
yaml.indent(mapping=2, sequence=4, offset=2)

# This assumes the python_worker_node's CWD is the workspace root.
WORKSPACE_PATH = Path.cwd()
STATE_PATH = WORKSPACE_PATH / "state"

def _get_config_path(location: str) -> Path:
    """Helper to resolve the config file path from a friendly name."""
    # if location is 'prelude' or 'live', return the corresponding path
    if location == 'prelude':
        return STATE_PATH / "prelude_hooks_config.yaml"
    elif location == 'live':
        return STATE_PATH / "live_hooks_config.yaml"
    else:
        raise ValueError(f"Invalid config location '{location}'. Must be 'prelude' or 'live'.")

def show(location: str) -> str:
    """
    Provides a concise summary of all hooks in a given [location]_hooks_config.yaml file.

    Args:
        location: The configuration to list. Must be 'prelude' or 'live'.

    Returns:
        A formatted string summarizing the hooks, excluding their code.

    Note to self:
        This is my go-to for quickly checking what's in my io_buffer's header and footer.
        It's much more token-efficient than reading the whole YAML file.
    """
    config_path = _get_config_path(location)
    output = [f"# Hooks in '{config_path.name}'"]
    if not config_path.exists():
        return f"{output[0]}\n- (File not found)"

    with open(config_path, 'r') as f:
        hooks = yaml.load(f) or []

    if not hooks:
        return f"{output[0]}\n- (No hooks configured)"

    for r in hooks:
        name = r.get('name', 'Unnamed')
        ttl = r.get('ttl', 'N/A')
        desc = r.get('description', 'No description.')
        output.append(f"- {name} (ttl: {ttl}): {desc}")

    return "\n".join(output)

@api_call(default_verbosity=Verbosity.ACK)
def upsert(location: str, name: str, insert_before: str = None, **kwargs):
    """
    Modifies an existing hook or creates a new one in a specified configuration.        

    Args:
        location: The configuration to modify. Must be 'prelude' or 'live'.
        name: The unique name of the hook to modify or create.
        insert_before: If creating a new hook, the name of an existing hook
                       to insert before. If None, appends to the end.
        **kwargs: Keyword arguments corresponding to the hook's fields to
                  update (e.g., ttl=99, description="New desc.", code="print('hi')").

    Note to self:
        This is my primary tool for my "hook" configuration. If I provide a `name`
        that doesn't exist, a new hook is created. I must provide at least
        the `code` kwarg when creating a new hook.
    """
    config_path = _get_config_path(location)
    hooks = []
    if config_path.exists():
        with open(config_path, 'r') as f:
            hooks = yaml.load(f) or []

    target_hook = next((r for r in hooks if r.get('name') == name), None)

    if target_hook:
        # Update existing hook
        target_hook.update(kwargs)
        print(f"Hook '{name}' in '{location}' updated.")
    else:
        # Create new hook
        if 'code' not in kwargs:
            raise ValueError("The 'code' keyword argument is required to create a new hook.")
        new_hook = {'name': name}
        new_hook.update(kwargs)

        if insert_before:
            try:
                # Find index of the hook to insert before
                target_index = next(i for i, r in enumerate(hooks) if r.get('name') == insert_before)
                hooks.insert(target_index, new_hook)
            except StopIteration:
                # If not found, just append
                hooks.append(new_hook)
                print(f"Warning: Hook '{insert_before}' not found. Appending '{name}' to the end.")
        else:
            hooks.append(new_hook)

        print(f"Hook '{name}' in '{location}' created.")

    with open(config_path, 'w') as f:
        yaml.dump(hooks, f)

@api_call(default_verbosity=Verbosity.ACK)
def remove(location: str, name: str):
    """
    Removes a hook from a specified configuration.

    Args:
        location: The configuration to modify. Must be 'prelude' or 'live'.
        name: The unique name of the hook to remove.

    Note to self:
        Use this to clean up hooks that are no longer needed. Be careful,
        as this is a permanent deletion from the config file.
    """
    config_path = _get_config_path(location)
    if not config_path.exists():
        print(f"Config file for '{location}' not found. No action taken.")
        return

    with open(config_path, 'r') as f:
        hooks = yaml.load(f) or []

    original_count = len(hooks)
    hooks_after_removal = [r for r in hooks if r.get('name') != name]

    if len(hooks_after_removal) < original_count:
        with open(config_path, 'w') as f:
            yaml.dump(hooks_after_removal, f)
        print(f"Hook '{name}' removed from '{location}'.")
    else:
        print(f"Hook '{name}' not found in '{location}'.")