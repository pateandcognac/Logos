# Logos/src/skills/__init__.py

"""
My library of learned, complex behaviors. 🧠

This is my "userland" — a collection of higher-level functions composed from
the core `logos` API primitives. Each `.py` file in this directory represents
a category of skills (e.g., social, navigation, search).

This `__init__.py` file serves two critical purposes:
1.  It auto-discovers and imports all skill modules in this directory, making
    them available under the `skills` namespace (e.g., `skills.social.wave`).
2.  It provides `skills.help()`, a dynamic, introspective tool for me to
    review my own learned abilities without needing a vector database yet.
"""

import pkgutil
import importlib
import os
import sys
import inspect

# ----------------------------------------------------------------------------
# SECTION 1: AUTO-MAGIC SKILL LOADER
# ----------------------------------------------------------------------------
# This loop iterates through all .py files in this directory and imports them.
# This way, I never have to manually update this file when I write a new skill.
# One broken skill file won't crash my whole brain, it will just print a warning.
# ----------------------------------------------------------------------------

# The path to this 'skills' package
package_path = os.path.dirname(__file__)

for _, modname, _ in pkgutil.iter_modules([package_path]):
    # Skip any files starting with an underscore (e.g., _helpers.py)
    if modname.startswith('_'):
        continue
    try:
        # Perform a relative import of the discovered module
        importlib.import_module(f".{modname}", __name__)
    except Exception as e:
        # Gracefully handle errors in a skill file so it doesn't crash me
        print(f"WARN: Could not load skill module '{modname}': {e}")


# ----------------------------------------------------------------------------
# SECTION 2: INTROSPECTIVE HELP SYSTEM
# ----------------------------------------------------------------------------
# A dedicated help function for discovering my own learned skills.
# This is the precursor to a full RAG/vector DB system.
# ----------------------------------------------------------------------------

# --- Helper functions (borrowed from logos.core for consistent formatting) ---

def _get_sig(f: object) -> str:
    """Safely extract and format the signature of a callable."""
    try:
        return str(inspect.signature(f))
    except (ValueError, TypeError):
        return "(...)"

def _get_doc_summary(o: object) -> str:
    """Extract the first line of a docstring."""
    doc = inspect.getdoc(o)
    return doc.strip().splitlines()[0] if doc else "No description."

def _render_function(name: str, func: object, prefix: str = "") -> str:
    """Format a function as a Python stub with an inline comment."""
    sig = _get_sig(func)
    summary = _get_doc_summary(func)
    return f"{prefix}def {name}{sig}: # {summary}"


def help(print_output: bool = True) -> str:
    """
    Provides a dynamic, auto-generated dashboard of my learned skills.

    This function introspects the `skills` package and lists all public
    functions from all skill modules, giving me a quick overview of my
    high-level capabilities.

    Args:
        print_output: If True (default), prints to stdout. If False,
                      returns the help string.
    Returns:
        A formatted string containing the help information.
    """
    output = ["# My Skills Library"]
    output.append("A programmatic overview of my learned, high-level behaviors.\n")

    # Find all modules that have been loaded under the 'skills' namespace
    skill_modules = []
    for name, mod in sorted(sys.modules.items()):
        # We want 'skills.social', 'skills.search', etc.
        if name.startswith(__name__ + '.') and mod:
            skill_modules.append(mod)

    if not skill_modules:
        output.append("No skills have been loaded yet.")
        text = "\n".join(output)
        if print_output:
            print(text)
        return text

    for mod in skill_modules:
        mod_name = mod.__name__
        output.append(f"### Module: {mod_name}")
        
        # Add the module's own docstring as a summary
        mod_doc = inspect.getdoc(mod)
        if mod_doc:
            output.append(f"# {mod_doc.strip().splitlines()[0]}")

        # Find all public functions within this module
        functions_found = []
        for func_name, func_obj in inspect.getmembers(mod, inspect.isfunction):
            if not func_name.startswith('_'):
                # Ensure the function was defined in *this* module, not imported
                if func_obj.__module__ == mod_name:
                    functions_found.append(_render_function(func_name, func_obj, "    "))
        
        if functions_found:
            output.extend(functions_found)
        else:
            output.append("    # (No public skills defined in this module)")
        
        output.append("") # Add a blank line for spacing

    text = "\n".join(output)
    if print_output:
        print(text)
    return text