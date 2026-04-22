# Logos/src/skills/__init__.py

"""
My library of learned, complex behaviors. 🧠

This is my "userland" — a collection of higher-level functions composed from
the core `logos` API primitives. Each `.py` file in this directory represents
a category of skills (e.g., social, navigation, search).

This `__init__.py` file serves two critical purposes:
1. It auto-discovers and imports all skill modules in this directory, making
   them available under the `skills` namespace (e.g., `skills.social.wave`).
2. It provides `skills.skills_help()`, a dynamic, introspective tool for
   reviewing available skills without needing a vector database yet.
"""

from __future__ import annotations

import importlib
import inspect
import os
import pkgutil
import sys
from types import ModuleType
from typing import Callable, List, Optional, Tuple

# ----------------------------------------------------------------------------
# SECTION 1: AUTO-MAGIC SKILL LOADER
# ----------------------------------------------------------------------------

package_path = os.path.dirname(__file__)

for _, modname, _ in pkgutil.iter_modules([package_path]):
    if modname.startswith("_"):
        continue

    try:
        importlib.import_module(f".{modname}", __name__)
    except Exception as exc:
        print(f"WARN: Could not load skill module '{modname}': {exc}")


# ----------------------------------------------------------------------------
# SECTION 2: INTROSPECTIVE HELP SYSTEM
# ----------------------------------------------------------------------------

def _get_sig(func: object) -> str:
    """Safely extract and format the signature of a callable."""
    try:
        return str(inspect.signature(func))
    except (ValueError, TypeError):
        return "(...)"


def _get_doc_summary(obj: object) -> str:
    """Extract the first line of a docstring."""
    doc = inspect.getdoc(obj)
    if not doc:
        return "No description."
    return doc.strip().splitlines()[0]


def _get_full_doc(obj: object, indent: str = "") -> str:
    """Return a cleaned full docstring, optionally indented."""
    doc = inspect.getdoc(obj)
    if not doc:
        return f"{indent}No description."

    lines = doc.strip().splitlines()
    return "\n".join(f"{indent}{line}" for line in lines)


def _render_function_summary(
    name: str,
    func: Callable,
    prefix: str = "",
) -> str:
    """Format a function as a Python stub with an inline summary comment."""
    sig = _get_sig(func)
    summary = _get_doc_summary(func)
    return f"{prefix}def {name}{sig}:  # {summary}"


def _render_function_full(
    name: str,
    func: Callable,
    prefix: str = "",
) -> List[str]:
    """Render a function with signature and full docstring."""
    sig = _get_sig(func)
    doc = _get_full_doc(func, indent=f"{prefix}    ")

    return [
        f"{prefix}def {name}{sig}",
        f"{prefix}\"\"\"",
        doc,
        f"{prefix}\"\"\"",
    ]


def _get_loaded_skill_modules() -> List[ModuleType]:
    """Return all loaded submodules under the skills package."""
    modules: List[ModuleType] = []

    for name, mod in sorted(sys.modules.items()):
        if name.startswith(__name__ + ".") and isinstance(mod, ModuleType):
            modules.append(mod)

    return modules


def _get_public_functions_in_module(mod: ModuleType) -> List[Tuple[str, Callable]]:
    """
    Return public functions defined in the given module.

    Imported functions are excluded. Only functions whose __module__ matches
    the module's name are returned.
    """
    functions: List[Tuple[str, Callable]] = []

    for func_name, func_obj in inspect.getmembers(mod, inspect.isfunction):
        if func_name.startswith("_"):
            continue
        if func_obj.__module__ != mod.__name__:
            continue
        functions.append((func_name, func_obj))

    return functions


def _resolve_target(
    target: Optional[str],
) -> Tuple[str, Optional[ModuleType], Optional[Tuple[str, Callable]], List[str]]:
    """
    Resolve a target string into either:
    - package overview
    - specific module
    - specific function

    Returns:
        (kind, module, function_tuple, errors)
        kind is one of: 'package', 'module', 'function', 'error'
    """
    if target is None:
        return "package", None, None, []

    target = target.strip()
    if not target:
        return "package", None, None, []

    package_mod = sys.modules[__name__]
    skill_modules = _get_loaded_skill_modules()
    all_modules = [package_mod] + skill_modules

    # 1. Exact module match:
    #    "skills.social" or "social"
    for mod in all_modules:
        full_name = mod.__name__
        short_name = full_name.split(".")[-1]
        if target in {full_name, short_name}:
            return "module", mod, None, []

    # 2. Dotted function match:
    #    "social.wave" or "skills.social.wave"
    if "." in target:
        parts = target.split(".")
        func_name = parts[-1]
        module_name = ".".join(parts[:-1])

        candidate_module_names = {
            module_name,
            f"{__name__}.{module_name}",
        }

        for mod in all_modules:
            if mod.__name__ in candidate_module_names:
                for found_name, found_func in _get_public_functions_in_module(mod):
                    if found_name == func_name:
                        return "function", mod, (found_name, found_func), []

        return "error", None, None, [
            f"No function found for target '{target}'."
        ]

    # 3. Bare function match:
    #    "wave"
    matches: List[Tuple[ModuleType, Tuple[str, Callable]]] = []

    for mod in all_modules:
        for found_name, found_func in _get_public_functions_in_module(mod):
            if found_name == target:
                matches.append((mod, (found_name, found_func)))

    if len(matches) == 1:
        mod, func_info = matches[0]
        return "function", mod, func_info, []

    if len(matches) > 1:
        match_names = [f"{mod.__name__}.{name}" for mod, (name, _) in matches]
        return "error", None, None, [
            f"Ambiguous function name '{target}'.",
            "Matches found:",
            *[f"  - {name}" for name in match_names],
            "Use a fully-qualified name like 'social.wave'.",
        ]

    return "error", None, None, [
        f"No module or function found for target '{target}'."
    ]


def _render_module(
    mod: ModuleType,
    full: bool = False,
) -> List[str]:
    """Render a module and its public functions."""
    lines: List[str] = []

    lines.append(f"### Module: {mod.__name__}")

    mod_doc = inspect.getdoc(mod)
    if mod_doc:
        if full:
            lines.append(_get_full_doc(mod))
        else:
            lines.append(f"# {_get_doc_summary(mod)}")

    functions = _get_public_functions_in_module(mod)

    if functions:
        for func_name, func_obj in functions:
            if full:
                lines.extend(_render_function_full(func_name, func_obj, prefix="    "))
            else:
                lines.append(_render_function_summary(func_name, func_obj, prefix="    "))
            lines.append("")
    else:
        lines.append("    # (No public skills defined in this module)")
        lines.append("")

    return lines


def _render_single_function(
    mod: ModuleType,
    func_name: str,
    func_obj: Callable,
    full: bool = True,
) -> List[str]:
    """Render help for a single function."""
    lines: List[str] = []

    lines.append(f"# Function: {mod.__name__}.{func_name}")

    if full:
        lines.extend(_render_function_full(func_name, func_obj))
    else:
        lines.append(_render_function_summary(func_name, func_obj))

    return lines


def skills_help(
    target: Optional[str] = None,
    *,
    full: bool = False,
    print_output: bool = True,
) -> str:
    """
    Provides a dynamic, auto-generated dashboard of available skills.

    By default, this returns a compact overview of all loaded skill modules
    and their public functions.

    You can also target a specific module or function.

    Examples:
        skills_help()
        skills_help(full=True)
        skills_help("social")
        skills_help("wave")
        skills_help("social.wave")
        skills_help("skills.social.wave", full=True)

    Args:
        target: Optional module or function target.
            Examples:
                "social"
                "social.wave"
                "wave"
                "skills_help"
        full: If True, include full docstrings instead of one-line summaries.
        print_output: If True, print the result to stdout.

    Returns:
        A formatted help string.
    """
    kind, mod, func_info, errors = _resolve_target(target)

    output: List[str] = []

    if kind == "error":
        output.append("# Skills Help")
        output.extend(errors)
        text = "\n".join(output)
        if print_output:
            print(text)
        return text

    if kind == "function" and mod is not None and func_info is not None:
        func_name, func_obj = func_info
        output.extend(_render_single_function(mod, func_name, func_obj, full=full))
        text = "\n".join(output)
        if print_output:
            print(text)
        return text

    if kind == "module" and mod is not None:
        output.append("# Skills Help")
        output.extend(_render_module(mod, full=full))
        text = "\n".join(output)
        if print_output:
            print(text)
        return text

    # Package overview
    output.append("# My Skills Library")
    output.append("An overview of my self-crafted, high-level behaviors.")
    output.append("")

    package_mod = sys.modules[__name__]
    skill_modules = _get_loaded_skill_modules()

    # Include package-level helpers like skills_help() itself
    output.append("## Package-Level Functions")
    package_functions = _get_public_functions_in_module(package_mod)

    if package_functions:
        for func_name, func_obj in package_functions:
            if full:
                output.extend(_render_function_full(func_name, func_obj, prefix="    "))
            else:
                output.append(_render_function_summary(func_name, func_obj, prefix="    "))
            output.append("")
    else:
        output.append("    # (No public package-level functions)")
        output.append("")

    output.append("## Skill Modules")
    output.append("")

    if not skill_modules:
        output.append("No skills have been loaded yet.")
    else:
        for skill_mod in skill_modules:
            output.extend(_render_module(skill_mod, full=full))

    text = "\n".join(output)
    if print_output:
        print(text)
    return text

