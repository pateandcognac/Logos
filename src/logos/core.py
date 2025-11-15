# preload_api/logos/core.py

import sys
import contextlib
from enum import Enum
import inspect
import types
import pkgutil
import importlib
import textwrap
import os
import json
from google import genai
from google.genai import types
from pathlib import Path
import functools
from .exceptions import Interrupt


# This is a global defined by the python_worker_node before my code runs.
# It will contain the interrupt payload (dict) or be None.
__logos_interrupt_request__ = None

# This will be set by the verbosity context manager.
__logos_verbosity_level__ = None 

class Verbosity(Enum):
    """Enumeration for setting API verbosity levels."""
    SILENT = 0  # No output unless it's a critical error.
    ACK = 1     # Acknowledge success/failure. e.g., "Action complete."
    BRIEF = 2   # Provide key details. e.g., "Moving to (1.2, 3.4)..."
    DEBUG = 3   # Provide rich, detailed output for troubleshooting.


def api_call(default_verbosity: Verbosity = Verbosity.ACK):
    """
    Decorator for public API functions that have side effects or are
    “actions” from Logos’ POV (movement, IO, memory changes, etc.).
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # 0. Cooperative interrupt check
            check_for_interrupt()

            # 1. Optional per-call override: func(..., verbosity=Verbosity.SILENT)
            level_override = kwargs.pop("verbosity", None)

            # 2. Determine effective verbosity
            effective_verbosity = (
                level_override
                or __logos_verbosity_level__
                or default_verbosity
            )

            func_name = func.__name__

            # 3. Pre-execution logging
            if effective_verbosity is Verbosity.ACK:
                print(f"Executing: {func_name}")
            elif effective_verbosity is Verbosity.BRIEF:
                arg_summary = [repr(a) for a in args]
                kwarg_summary = [f"{k}={v!r}" for k, v in kwargs.items()]
                print(f"Executing: {func_name}({', '.join(arg_summary + kwarg_summary)})")
            elif effective_verbosity is Verbosity.DEBUG:
                print(f"DEBUG: Calling {func_name} with args={args!r}, kwargs={kwargs!r}")

            # 4. Execute
            try:
                result = func(*args, **kwargs)

                # 5. Post-execution logging
                if effective_verbosity in (Verbosity.ACK, Verbosity.BRIEF, Verbosity.DEBUG):
                    print(f"Success: {func_name}")
                if effective_verbosity is Verbosity.DEBUG and result is not None:
                    print(f"DEBUG: {func_name} returned: {result!r}")

                return result
            except Exception as exc:
                print(f"ERROR in {func_name}: {type(exc).__name__} - {exc}")
                raise

        return wrapper

    return decorator


def check_for_interrupt():
    """
    Checks if an external interrupt has been requested.

    If an interrupt is pending, this function will raise a `logos.Interrupt`
    exception, which halts the current execution and returns control to the
    framework. This is a 'cooperative' check; code will not be stopped
    unless this function is called.

    Note to self:
        I must call this periodically in any long-running loops I write.
        Most built-in `logos` API functions will call this for me.
    """
    if __logos_interrupt_request__ is not None:
        raise Interrupt()

@contextlib.contextmanager
def verbosity(level: Verbosity):
    """
    A context manager to temporarily set the verbosity level for API calls.

    Note to self:
        I can use this to control the output of my API calls within a `with` block.
        This is very useful for silencing noisy loops or enabling debug output.
    
    Example:
        # This call will use its default verbosity.
        logos.nav.go_to_coords(...)

        # These calls will be silent.
        with logos.verbosity(Verbosity.SILENT):
            for waypoint in path:
                logos.nav.go_to_coords(waypoint)
    """
    global __logos_verbosity_level__
    original_level = __logos_verbosity_level__
    __logos_verbosity_level__ = level
    try:
        yield
    finally:
        __logos_verbosity_level__ = original_level



def help(obj=None):
    """
    Provides a dynamic, auto-generated help summary for my API.

    Args:
        obj: The API object to get help for. Can be a module or a function.
             If None, provides a summary of the entire `logos` API.

    Returns:
        A formatted string containing the help information.

    Note to self:
        This is my primary tool for understanding my own capabilities.
        - `logos.help()` gives me a high-level overview.
        - `logos.help(logos.files)` shows me all file-related commands.
        - `logos.help(logos.files.tree)` gives me the full details for the tree command.
    """
    # Case 1: No argument provided. Summarize the entire logos package.
    if obj is None:
        import logos
        output = ["# Logos API Summary", "A dynamically generated overview of my capabilities.", ""]
        output.append("## Modules:")

        for importer, modname, ispkg in pkgutil.iter_modules(logos.__path__):
            try:
                module = importlib.import_module(f'.{modname}', 'logos')
                doc = inspect.getdoc(module) or "No description."
                output.append(f"- logos.{modname}: {doc.splitlines()[0]}")
            except Exception as e:
                output.append(f"- logos.{modname}: (Could not import: {e})")
        
        output.append("\n## Core Functions (available directly):")
        
        core_functions = []
        for name, func in inspect.getmembers(logos, inspect.isfunction):
            if func.__module__.startswith('logos.'):
                 core_functions.append(func)
        
        if not core_functions:
            output.append("- None found.")
        else:
            for func in sorted(core_functions, key=lambda f: f.__name__):
                sig = inspect.signature(func)
                doc = inspect.getdoc(func) or "No description."
                output.append(f"- logos.{func.__name__}{sig}: {doc.splitlines()[0]}")

        output.append("\nNote to self: Use `logos.help(logos.module_name)` or `logos.help(logos.function_name)` for more details.")
        return "\n".join(output)

    # Case 2: A module is provided. Summarize the functions within it.
    if inspect.ismodule(obj):
        output = [f"# Help for module: {obj.__name__}", inspect.getdoc(obj) or "", ""]
        output.append("## Functions:")

        # If the module defines __all__, respect it as the public surface.
        public_names = getattr(obj, "__all__", None)

        for name, func in inspect.getmembers(obj, inspect.isfunction):
            # Skip functions not defined in this module
            if func.__module__ != obj.__name__:
                continue
            # Skip private helpers
            if name.startswith("_"):
                continue
            # If __all__ is defined, skip anything not in it
            if public_names is not None and name not in public_names:
                continue

            sig = inspect.signature(func)
            doc = inspect.getdoc(func) or "No description."
            output.append(f"- {name}{sig}: {doc.splitlines()[0]}")

        output.append(f"\nNote to self: Use `logos.help({obj.__name__}.function_name)` for full details.")
        return "\n".join(output)


    # Case 3: A function is provided. Show its full docstring.
    if inspect.isfunction(obj):
        sig = inspect.signature(obj)
        header = f"# Help for function: {obj.__name__}{sig}"
        doc = inspect.getdoc(obj)
        if not doc:
            return f"{header}\n\nNo documentation found."

        lines = [line.rstrip() for line in doc.strip().splitlines()]
        output = [header, ""]

        # Description: everything up to the first section header.
        section_headers = ("Args:", "Arguments:", "Parameters:", "Returns:", "Note to self:", "Raises:")
        desc_lines = []
        i = 0
        while i < len(lines) and not any(lines[i].strip().startswith(h) for h in section_headers):
            desc_lines.append(lines[i])
            i += 1

        if desc_lines:
            output.append("## Description")
            output.append("\n".join(desc_lines).strip())
            output.append("")

        # Now render sections
        current_section = None
        while i < len(lines):
            line = lines[i].strip()
            if any(line.startswith(h) for h in section_headers):
                current_section = line.rstrip(":")
                output.append(f"## {current_section}")
            else:
                output.append(f"  {line}")
            i += 1

        return "\n".join(output)


    return f"Cannot provide help for object of type '{type(obj).__name__}'. Please provide a module or function."