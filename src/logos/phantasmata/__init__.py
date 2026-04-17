# src/logos/phantasmata/__init__.py
"""
My phantasmata — dynamic, scriptable objects that populate my mind palace.

This module provides the infrastructure for loading and managing phantasma
plugins. Each phantasma is a Python module that defines 3D geometry and/or
HUD overlays to render in my Map3d virtual environment.

Phantasmata turn abstract concepts (waypoints, furniture, debug visualizations,
alerts) into tangible 3D objects I can see and reason about spatially. They're
how my inner world becomes populated with meaning.

Usage:
    # Phantasmata are loaded via mind_palace.yaml configuration
    # or created programmatically through map3d.place()

    # Each phantasma module must define:
    # - SCHEMA: dict of parameter definitions
    # - DYNAMIC: bool (whether to rebuild each render)
    # - build(params, ctx) -> SceneObject | List[SceneObject] | None

    # Optional:
    # - hud(params, ctx) -> List[HudElement] | None
    # - should_rebuild(params, ctx) -> bool
    # - cleanup(ctx) -> None

See Also:
    phantasma_convention.py - PhantasmaContext and schema validation
    self_model.py - My own self-representation, which is a special kind of phantasma. MVP WIP
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, TYPE_CHECKING
import importlib
import importlib.util
import os
import sys

if TYPE_CHECKING:
    from .phantasma_convention import PhantasmaContext

__all__ = [
    "discover_phantasmata",
    "load_phantasma_module",
    "get_phantasma_schema",
    "validate_params",
]


def discover_phantasmata(phantasmata_dir: str) -> List[str]:
    """
    Discover available phantasma modules in the given directory.

    I scan for .py files that look like phantasmata (have SCHEMA defined)
    and return their names (without .py extension).

    Args:
        phantasmata_dir: Path to the phantasmata directory

    Returns:
        List of phantasma module names (e.g., ['grid_overlay', 'waypoints'])
    """
    phantasma_names: List[str] = []

    if not os.path.isdir(phantasmata_dir):
        return phantasma_names

    for filename in os.listdir(phantasmata_dir):
        if not filename.endswith('.py'):
            continue
        if filename.startswith('_'):
            continue
        if filename == 'phantasma_convention.py':
            continue

        name = filename[:-3]  # Remove .py
        phantasma_names.append(name)

    return sorted(phantasma_names)


def load_phantasma_module(
    module_name: str,
    phantasmata_dir: str,
) -> Any:
    """
    Import a phantasma module by name from the phantasmata directory.

    This uses importlib to dynamically load the module, allowing phantasmata
    to be added/modified without restarting the system.

    Args:
        module_name: Name of the phantasma (without .py extension)
        phantasmata_dir: Path to the phantasmata directory

    Returns:
        The imported module object

    Raises:
        FileNotFoundError: If the module file doesn't exist
        ImportError: If the module fails to import
        ValueError: If the module doesn't have required interface (SCHEMA, build)
    """
    module_path = os.path.join(phantasmata_dir, f"{module_name}.py")

    if not os.path.exists(module_path):
        raise FileNotFoundError(
            f"Phantasma module not found: {module_path}"
        )

    # Generate a unique module name to avoid conflicts
    full_module_name = f"logos.phantasmata.{module_name}"

    # Load the module using importlib
    spec = importlib.util.spec_from_file_location(full_module_name, module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load phantasma module spec: {module_path}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[full_module_name] = module
    spec.loader.exec_module(module)

    # Validate required interface
    if not hasattr(module, 'SCHEMA'):
        raise ValueError(
            f"Phantasma {module_name} missing required SCHEMA dict"
        )
    if not hasattr(module, 'build'):
        raise ValueError(
            f"Phantasma {module_name} missing required build() function"
        )

    return module


def get_phantasma_schema(module: Any) -> Dict[str, Any]:
    """
    Extract the SCHEMA from a loaded phantasma module.

    Args:
        module: A loaded phantasma module

    Returns:
        The SCHEMA dict, or empty dict if not present
    """
    return getattr(module, 'SCHEMA', {})


def validate_params(
    params: Dict[str, Any],
    schema: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Validate and merge params against a phantasma's SCHEMA.

    Missing params are filled with defaults from the schema.
    Type checking is lenient — I trust the AI knows what they're doing.

    Args:
        params: User-provided parameters
        schema: The phantasma's SCHEMA dict

    Returns:
        Merged parameters with defaults filled in
    """
    merged = {}

    # Start with schema defaults
    for key, spec in schema.items():
        if isinstance(spec, dict):
            merged[key] = spec.get('default')
        else:
            # Handle simple key: default_value format
            merged[key] = spec

    # Override with user params
    merged.update(params)

    return merged


def is_dynamic(module: Any) -> bool:
    """
    Check if a phantasma module is dynamic (rebuilt every render).

    Args:
        module: A loaded phantasma module

    Returns:
        True if DYNAMIC is True, False otherwise
    """
    return bool(getattr(module, 'DYNAMIC', False))


def has_hud(module: Any) -> bool:
    """
    Check if a phantasma module provides HUD contributions.

    Args:
        module: A loaded phantasma module

    Returns:
        True if module has a hud() function
    """
    return hasattr(module, 'hud') and callable(module.hud)


def has_should_rebuild(module: Any) -> bool:
    """
    Check if a phantasma has a should_rebuild() gate function.

    Args:
        module: A loaded phantasma module

    Returns:
        True if module has a should_rebuild() function
    """
    return hasattr(module, 'should_rebuild') and callable(module.should_rebuild)


def has_cleanup(module: Any) -> bool:
    """
    Check if a phantasma has a cleanup() function.

    Args:
        module: A loaded phantasma module

    Returns:
        True if module has a cleanup() function
    """
    return hasattr(module, 'cleanup') and callable(module.cleanup)
