# preload_api/logos/config.py

"""
This module contains functions for me to introspect and modify my own
context routine configurations (`prelude_context_config.yaml` and
`live_context_config.yaml`). It is a core part of my self-modification ability.
"""

from pathlib import Path
from ruamel.yaml import YAML

# Initialize a YAML instance that preserves comments and formatting
yaml = YAML()
yaml.indent(mapping=2, sequence=4, offset=2)

# This assumes the python_worker_node's CWD is the workspace root.
WORKSPACE_PATH = Path.cwd()
STATE_PATH = WORKSPACE_PATH / "state"

def _get_config_path(location: str) -> Path:
    """Helper to resolve the config file path from a friendly name."""
    if location == 'prelude':
        return STATE_PATH / "prelude_context_config.yaml"
    elif location == 'live':
        return STATE_PATH / "live_context_config.yaml"
    else:
        raise ValueError(f"Invalid config location '{location}'. Must be 'prelude' or 'live'.")

def list_routines(location: str) -> str:
    """
    Provides a concise summary of all routines in a given config file.

    Args:
        location: The configuration to list. Must be 'prelude' or 'live'.

    Returns:
        A formatted string summarizing the routines, excluding their code.

    Note to self:
        This is my go-to for quickly checking what's in my header and footer.
        It's much more token-efficient than reading the whole YAML file.
    """
    config_path = _get_config_path(location)
    output = [f"# Routines in '{config_path.name}'"]
    if not config_path.exists():
        return f"{output[0]}\n- (File not found)"

    with open(config_path, 'r') as f:
        routines = yaml.load(f) or []

    if not routines:
        return f"{output[0]}\n- (No routines configured)"

    for r in routines:
        name = r.get('name', 'Unnamed')
        ttl = r.get('ttl', 'N/A')
        desc = r.get('description', 'No description.')
        output.append(f"- {name} (ttl: {ttl}): {desc}")

    return "\n".join(output)

def modify_routine(location: str, name: str, insert_before: str = None, **kwargs):
    """
    Modifies an existing routine or creates a new one if it doesn't exist.

    Args:
        location: The configuration to modify. Must be 'prelude' or 'live'.
        name: The unique name of the routine to modify or create.
        insert_before: If creating a new routine, the name of an existing routine
                       to insert before. If None, appends to the end.
        **kwargs: Keyword arguments corresponding to the routine's fields to
                  update (e.g., ttl=99, description="New desc.", code="print('hi')").

    Note to self:
        This is my primary tool for my "routine" configuration. If I provide a `name`
        that doesn't exist, a new routine is created. I must provide at least
        the `code` kwarg when creating a new routine.
    """
    config_path = _get_config_path(location)
    routines = []
    if config_path.exists():
        with open(config_path, 'r') as f:
            routines = yaml.load(f) or []

    target_routine = next((r for r in routines if r.get('name') == name), None)

    if target_routine:
        # Update existing routine
        target_routine.update(kwargs)
        print(f"Routine '{name}' in '{location}' updated.")
    else:
        # Create new routine
        if 'code' not in kwargs:
            raise ValueError("The 'code' keyword argument is required to create a new routine.")
        new_routine = {'name': name}
        new_routine.update(kwargs)

        if insert_before:
            try:
                # Find index of the routine to insert before
                target_index = next(i for i, r in enumerate(routines) if r.get('name') == insert_before)
                routines.insert(target_index, new_routine)
            except StopIteration:
                # If not found, just append
                routines.append(new_routine)
                print(f"Warning: Routine '{insert_before}' not found. Appending '{name}' to the end.")
        else:
            routines.append(new_routine)

        print(f"Routine '{name}' in '{location}' created.")

    with open(config_path, 'w') as f:
        yaml.dump(routines, f)

def remove_routine(location: str, name: str):
    """
    Removes a routine from a specified configuration.

    Args:
        location: The configuration to modify. Must be 'prelude' or 'live'.
        name: The unique name of the routine to remove.

    Note to self:
        Use this to clean up routines that are no longer needed. Be careful,
        as this is a permanent deletion from the config file.
    """
    config_path = _get_config_path(location)
    if not config_path.exists():
        print(f"Config file for '{location}' not found. No action taken.")
        return

    with open(config_path, 'r') as f:
        routines = yaml.load(f) or []

    original_count = len(routines)
    routines_after_removal = [r for r in routines if r.get('name') != name]

    if len(routines_after_removal) < original_count:
        with open(config_path, 'w') as f:
            yaml.dump(routines_after_removal, f)
        print(f"Routine '{name}' removed from '{location}'.")
    else:
        print(f"Routine '{name}' not found in '{location}'.")