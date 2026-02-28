# Logos/src/logos/hooks.py

"""
This module contains functions for me to introspect and modify my own cognitive hook configurations. Does *not* contain the hook code itself.
"""

from pathlib import Path
from ruamel.yaml import YAML
from .core import Verbosity, api_call
from typing import Union
import time

__all__ = ["show", "upsert", "remove"]


# Initialize a YAML instance that preserves comments and formatting
yaml = YAML()
yaml.indent(mapping=2, sequence=4, offset=2)

# This assumes the python_worker_node's CWD is the workspace root.
WORKSPACE_PATH = Path.cwd()
STATE_PATH = WORKSPACE_PATH / "state"

def _get_config_path(location: str) -> Path:
    """Helper to resolve the config file path from a friendly name."""
    # if location is 'arche' or 'ephemera', return the corresponding path
    if location == 'arche':
        return STATE_PATH / "arche_config.yaml"
    elif location == 'ephemera':
        return STATE_PATH / "ephemera_config.yaml"
    else:
        raise ValueError(f"Invalid config location '{location}'. Must be 'arche' or 'ephemera'.")

def show(location: str) -> str:
    """
    Provides a concise summary of all hooks in a given [location]_hooks_config.yaml file.

    Args:
        location: The configuration to list. Must be 'arche' or 'ephemera'.

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
def upsert(location: str, name: str, *, description: Union[str, None] = None, ttl: Union[int, None] = None, code: Union[str, None] = None, insert_before: Union[str, None] = None,) -> None:
    """
    Update an existing hook or create a new one in the requested configuration.

    Args:
        location: Which config file to edit ('arche' or 'ephemera').
        name: Unique hook name to update or create.
        description: Human-friendly summary to store with the hook.
        ttl: Number of cycles the hook should persist (e.g., 99 to pin, -99 to run once).
        code: Python source for the hook. Required when creating a new hook.
        insert_before: Optional hook name to insert before when creating.
    """
    config_path = _get_config_path(location)
    hooks = []
    if config_path.exists():
        with open(config_path, 'r') as f:
            hooks = yaml.load(f) or []

    updates = {
        "description": description,
        "ttl": ttl,
        "code": code,
    }
    provided_updates = {k: v for k, v in updates.items() if v is not None}

    target_hook = next((r for r in hooks if r.get('name') == name), None)

    if target_hook:
        if not provided_updates:
            print(f"No updates supplied for hook '{name}' in '{location}'.")
            return
        target_hook.update(provided_updates)
        print(f"Hook '{name}' in '{location}' updated.")
    else:
        if code is None:
            raise ValueError("The 'code' argument is required to create a new hook.")

        new_hook = {"name": name, **provided_updates}

        if insert_before:
            try:
                target_index = next(i for i, r in enumerate(hooks) if r.get('name') == insert_before)
                hooks.insert(target_index, new_hook)
            except StopIteration:
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
        location: The configuration to modify. Must be 'arche' or 'ephemera'.
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
