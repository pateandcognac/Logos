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


def exec_feedback(default_verbosity: Verbosity = Verbosity.ACK):
    """
    A decorator for all public API functions.
    It handles standardized verbosity, logging, and interrupt checking.
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # 1. Always check for interrupts before doing anything.
            check_for_interrupt()

            # 2. Determine the effective verbosity level.
            effective_verbosity = __logos_verbosity_level__
            if effective_verbosity is None:
                effective_verbosity = default_verbosity

            if effective_verbosity.value >= Verbosity.SILENT.value:
                func_name = func.__name__
                
                # 3. Print pre-execution message based on verbosity.
                if effective_verbosity.value == Verbosity.ACK.value:
                    print(f"Executing: {func_name}")
                elif effective_verbosity.value == Verbosity.BRIEF.value:
                    # Create a summary of args
                    arg_summary = [str(a) for a in args]
                    kwarg_summary = [f"{k}={v}" for k, v in kwargs.items()]
                    print(f"Executing: {func_name}({', '.join(arg_summary + kwarg_summary)})")
                elif effective_verbosity.value >= Verbosity.DEBUG.value:
                    print(f"DEBUG: Calling {func_name} with args={args}, kwargs={kwargs}")

            # 4. Execute the actual function.
            try:
                result = func(*args, **kwargs)
                
                # 5. Print post-execution message.
                if effective_verbosity.value >= Verbosity.ACK.value:
                    print(f"Success: {func_name}")
                if effective_verbosity.value >= Verbosity.DEBUG.value and result is not None:
                    print(f"DEBUG: {func_name} returned: {result}")
                    
                return result
            except Exception as e:
                # 6. Log exceptions and re-raise them.
                print(f"ERROR in {func_name}: {type(e).__name__} - {e}")
                raise # Re-raise the exception so it's not swallowed

        return wrapper
    return decorator

class Verbosity(Enum):
    """Enumeration for setting API verbosity levels."""
    SILENT = 0  # No output unless it's a critical error.
    ACK = 1     # Acknowledge success/failure. e.g., "Action complete."
    BRIEF = 2   # Provide key details. e.g., "Moving to (1.2, 3.4)..."
    DEBUG = 3   # Provide rich, detailed output for troubleshooting.

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

        # Dynamically discover all modules within the 'logos' package
        for importer, modname, ispkg in pkgutil.iter_modules(logos.__path__):
            try:
                module = importlib.import_module(f'.{modname}', 'logos')
                doc = inspect.getdoc(module) or "No description."
                output.append(f"- logos.{modname}: {doc.splitlines()[0]}")
            except Exception as e:
                output.append(f"- logos.{modname}: (Could not import: {e})")

        output.append("\nNote to self: Use `logos.help(logos.module_name)` for more details.")
        return "\n".join(output)

    # Case 2: A module is provided. Summarize the functions within it.
    if inspect.ismodule(obj):
        output = [f"# Help for module: {obj.__name__}", inspect.getdoc(obj) or "", ""]
        output.append("## Functions:")
        for name, func in inspect.getmembers(obj, inspect.isfunction):
            if func.__module__ == obj.__name__: # Only show functions defined in this module
                doc = inspect.getdoc(func) or "No description."
                output.append(f"- {name}(): {doc.splitlines()[0]}")
        output.append(f"\nNote to self: Use `logos.help({obj.__name__}.function_name)` for full details.")
        return "\n".join(output)

    # Case 3: A function is provided. Show its full docstring.
    if inspect.isfunction(obj):
        output = [f"# Help for function: {obj.__name__}", ""]
        doc = inspect.getdoc(obj)
        if not doc:
            return f"No documentation found for function '{obj.__name__}'."

        # A bit of formatting to make it look nice
        lines = doc.strip().splitlines()
        output.append(f"## Description")
        desc_lines = []
        i = 0
        while i < len(lines) and lines[i].strip() != "Args:":
            desc_lines.append(lines[i].strip())
            i += 1
        output.append("\n".join(desc_lines).strip())

        # Find and format other sections like Args, Returns, Note to self
        while i < len(lines):
            line = lines[i].strip()
            if line.endswith(':'):
                output.append(f"\n## {line.replace(':', '')}")
            else:
                output.append(f"  {line}")
            i += 1
        return "\n".join(output)

    return f"Cannot provide help for object of type '{type(obj).__name__}'. Please provide a module or function."