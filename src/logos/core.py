# src/logos/core.py

"""
Core functionality for the Logos API, including verbosity management, cooperative interrupt handling, and dynamic help generation.
"""
import textwrap
import contextlib
from enum import Enum
import inspect
import pkgutil
import importlib
import functools
from .exceptions import Interrupt
from typing import List, Optional, Callable, Any, Union, Tuple
import time

# This is a global defined by the python_worker_node before my code runs.
# It will contain the interrupt payload (dict) or be None.
__logos_interrupt_request__ = None

# This will be set by the verbosity context manager.
__logos_verbosity_level__ = None 

# Modules under the `logos` namespace that should be hidden from logos.api_help()
_HIDDEN_MODULES = {"_llm_helper"}

# Sentinel used to request a full doc dump from logos.api_help()
_ALL_SENTINEL = object()


class Verbosity(Enum):
    """Enumeration for setting API verbosity levels."""
    SILENT = 0  # No output unless it's a critical error.
    ACK = 1     # Acknowledge success/failure. e.g., "Action complete."
    BRIEF = 2   # Provide key details. e.g., "Moving to (1.2, 3.4)..."
    DEBUG = 3   # Provide rich, detailed output for troubleshooting.




def api_call(default_verbosity: Verbosity = Verbosity.ACK): 
    """
    Decorator for public API functions that have side effects or are "actions" from Logos' POV (movement, I/O, memory changes, etc.). Adds `verbosity` kwarg to decorated functions.

    Injects a universal `verbosity` keyword argument into every decorated
    function, which Logos can pass explicitly or let inherit from the
    `logos.verbosity(...)` context manager. This is why I can always write
    something like:

        logos.pantilt.move(30, 0, verbosity=Verbosity.SILENT)
        logos.base.velocity(0.1, 0.0, verbosity=Verbosity.DEBUG)

    ...even though `verbosity` does not appear in the wrapped function's
    own signature. `help()` output hides this parameter intentionally to keep
    signatures readable — just know it's always there on any @api_call.

    Args:
        default_verbosity: The verbosity level used when neither the caller
            nor an active `logos.verbosity(...)` context specifies one.
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            check_for_interrupt()

            level_override = kwargs.pop("verbosity", None)
            effective_verbosity = (
                level_override
                or __logos_verbosity_level__
                or default_verbosity
            )

            func_name = func.__name__

            # --- PRE-EXECUTION LOGGING ---
            if effective_verbosity is Verbosity.ACK:
                print(f"Executing: {func_name}")
            
            elif effective_verbosity is Verbosity.BRIEF:
                # Use _smart_repr for cleaner logs
                arg_summary = [_smart_repr(a) for a in args]
                kwarg_summary = [f"{k}={_smart_repr(v)}" for k, v in kwargs.items()]
                print(f"Executing: {func_name}({', '.join(arg_summary + kwarg_summary)})")
            
            elif effective_verbosity is Verbosity.DEBUG:
                # Even in DEBUG, smart_repr prevents context window blowouts
                arg_summary = [_smart_repr(a, max_str_len=500) for a in args]
                kwarg_summary = [f"{k}={_smart_repr(v, max_str_len=1000)}" for k, v in kwargs.items()]
                print(f"DEBUG: {func_name}({', '.join(arg_summary + kwarg_summary)})")

            try:
                result = func(*args, **kwargs)

                # --- POST-EXECUTION LOGGING ---
                if effective_verbosity in (Verbosity.ACK, Verbosity.BRIEF, Verbosity.DEBUG):
                    print(f"Success: {func_name}")
                
                if effective_verbosity is Verbosity.DEBUG and result is not None:
                    # Format the return value too!
                    print(f"DEBUG: {func_name} returned: {_smart_repr(result)}")

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



def api_help(
    obj: Optional[object] = None, 
    search: Optional[str] = None, 
    print_output: bool = True
) -> str:
    """
    Provides a dynamic, auto-generated help dashboard for my API.

    Args:
        obj: The API object to get help for (module, class, or function).
             If None, provides a comprehensive dashboard of the entire API.
        search: A string to search for across function/class names and docstrings.
        print_output: If True, prints to stdout. If False, just returns the string.

    Returns:
        A formatted string containing the help information.

    Note to self:
        - `logos.api_help()` gives me the full dashboard (Signatures + 1-liners).
        - `logos.api_help(logos.vision.capture)` gives me the deep-dive docstring.
        - `logos.api_help(search="crop")` helps me find tools when I forget where they live.
    """
    import inspect
    import pkgutil
    import importlib
    import logos

    # secret logos.everything sentinel for dumping all docstrings in one go
    dump_all = obj is getattr(logos, "everything", None) or obj is _ALL_SENTINEL
    output: List[str] = []

    # --- HELPER FUNCTIONS FOR FORMATTING ---
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

    def _render_class(name: str, cls: object, prefix: str = "") -> List[str]:
        """Format a class and its public methods."""
        lines = [f"{prefix}class {name}: # {_get_doc_summary(cls)}"]
        for m_name, m_func in inspect.getmembers(cls, inspect.isroutine):
            if not m_name.startswith("_"):
                lines.append(_render_function(m_name, m_func, prefix + "    "))
        if len(lines) == 1:
            lines.append(f"{prefix}    pass")
        return lines

    def _logos_module_name(mod: object) -> str:
        name = getattr(mod, "__name__", "")
        if name == "logos":
            return "logos"
        if name.startswith("logos."):
            return name
        return f"logos.{name}"

    def _render_module(mod_name: str, mod: object) -> List[str]:
        """Render a full module's constants, classes, and functions."""
        lines = [f"### Module: logos.{mod_name}", f"# {_get_doc_summary(mod)}"]
        
        public_names = getattr(mod, "__all__", None)
        members = inspect.getmembers(mod)

        constants = []
        classes = []
        functions = []

        for name, val in members:
            # Filter by __all__ if defined, otherwise skip private/imported
            if public_names is not None:
                if name not in public_names:
                    continue
            else:
                if name.startswith("_"):
                    continue
                # Skip things imported from other modules unless they are core to this one
                if inspect.getmodule(val) is not None and inspect.getmodule(val).__name__ != mod.__name__:
                    continue

            if inspect.isclass(val):
                classes.append((name, val))
            elif inspect.isroutine(val):
                functions.append((name, val))
            elif name.isupper(): # Convention for constants
                constants.append((name, val))

        if constants:
            lines.append("Constants:")
            for n, v in constants:
                lines.append(f"    {n} = {v!r}")
            lines.append("")  # <--- Add spacer after constants
        
        if classes:
            lines.append("Classes:")
            for n, c in classes:
                lines.extend(_render_class(n, c, "    "))
            lines.append("")  # <--- Add spacer after classes
                
        if functions:
            lines.append("Functions:")
            for n, f in functions:
                lines.append(_render_function(n, f, "    "))
            
                
        lines.append("") # Spacer
        return lines

    def _iter_public_modules() -> List[Tuple[str, Optional[object], Optional[Exception]]]:
        """
        Discover public logos modules, including one level of public submodules.

        Package modules like logos.memory can have their own files with public
        APIs. I include those child modules so api_help() shows the real tools
        instead of only the package __init__.py facade.
        """
        discovered = []

        for _importer, modname, ispkg in pkgutil.iter_modules(logos.__path__):
            if modname.startswith("_") or modname in _HIDDEN_MODULES:
                continue

            try:
                mod = importlib.import_module(f".{modname}", "logos")
            except Exception as exc:
                discovered.append((modname, None, exc))
                continue

            discovered.append((modname, mod, None))

            if ispkg:
                pkg_path = getattr(mod, "__path__", [])
                for _sub_importer, subname, _sub_ispkg in pkgutil.iter_modules(pkg_path):
                    if subname.startswith("_") or subname in _HIDDEN_MODULES:
                        continue
                    child_name = f"{modname}.{subname}"
                    try:
                        child_mod = importlib.import_module(f".{child_name}", "logos")
                    except Exception as exc:
                        discovered.append((child_name, None, exc))
                        continue
                    discovered.append((child_name, child_mod, None))

        return discovered


    def _indent(text: str, spaces: int) -> str:
        pad = " " * spaces
        return "\n".join(pad + line if line else line for line in text.splitlines())

    def _safe_doc(o: object) -> str:
        # inspect.getdoc() cleans indentation and ignores non-string __doc__
        return inspect.getdoc(o) or ""

    def _render_doc_block(title: str, doc: str, indent_spaces: int = 0) -> List[str]:
        if not doc.strip():
            return [(" " * indent_spaces) + f"{title}: (no docstring)"]
        lines = [(" " * indent_spaces) + title + ":"]
        lines.append(_indent(doc, indent_spaces + 4))
        return lines

    def _render_function_dump(qualname: str, func: object, indent_spaces: int = 0) -> List[str]:
        sig = _get_sig(func)
        lines = [(" " * indent_spaces) + f"{qualname}{sig}"]
        doc = _safe_doc(func)
        if doc:
            lines.extend(_render_doc_block("Docstring", doc, indent_spaces + 2))
        else:
            lines.append((" " * (indent_spaces + 2)) + "Docstring: (none)")
        return lines

    def _render_class_dump(qualname: str, cls: object, indent_spaces: int = 0) -> List[str]:
        lines = [(" " * indent_spaces) + f"class {qualname}:"]
        class_doc = _safe_doc(cls)
        if class_doc:
            lines.extend(_render_doc_block("Docstring", class_doc, indent_spaces + 2))
        else:
            lines.append((" " * (indent_spaces + 2)) + "Docstring: (none)")

        # Public routines (methods, classmethods, staticmethods)
        members = inspect.getmembers(cls)
        routines = []
        for name, val in members:
            if name.startswith("_"):
                continue
            # Include callables (functions/descriptor-wrapped methods). isroutine catches functions + builtins.
            if inspect.isroutine(val):
                routines.append((name, val))

        if routines:
            lines.append((" " * (indent_spaces + 2)) + "Methods:")
            for name, val in routines:
                # Add a tiny visual break before every method to make them distinct
                lines.append("") 
                lines.extend(_render_function_dump(f"{qualname}.{name}", val, indent_spaces + 4))
        else:
            lines.append((" " * (indent_spaces + 2)) + "Methods: (none)")

        return lines

    def _render_module_dump(mod_name: str, mod: object) -> List[str]:
        lines = [f"### Module: logos.{mod_name}"]
        mod_doc = _safe_doc(mod)
        if mod_doc:
            lines.extend(_render_doc_block("Docstring", mod_doc, 0))
        else:
            lines.append("Docstring: (none)")

        public_names = getattr(mod, "__all__", None)
        members = inspect.getmembers(mod)

        constants = []
        classes = []
        functions = []

        for name, val in members:
            if public_names is not None:
                if name not in public_names:
                    continue
            else:
                if name.startswith("_"):
                    continue
                # Keep your existing “skip imported stuff” filter
                if inspect.getmodule(val) is not None and inspect.getmodule(val).__name__ != mod.__name__:
                    continue

            if inspect.isclass(val):
                classes.append((name, val))
            elif inspect.isroutine(val):
                functions.append((name, val))
            elif name.isupper():
                constants.append((name, val))

        if constants:
            lines.append("Constants:")
            for n, v in constants:
                lines.append(f"    {n} = {v!r}")
            lines.append("") 

        if classes:
            lines.append("Classes:")
            for n, c in classes:
                lines.extend(_render_class_dump(n, c, indent_spaces=4))
                lines.append("")
            lines.append("")

        if functions:
            lines.append("Functions:")
            for n, f in functions:
                lines.extend(_render_function_dump(n, f, indent_spaces=4))
                lines.append("") 

        lines.append("")
        return lines


# --- EXECUTION MODES ---

    # MODE 0: Comprehensive dump (full docstrings for everything)
    if dump_all:
        output.append("# Logos API Full Dump (docstrings + signatures)")
        output.append("Everything inspectable without showing raw source.\n")

        for modname, mod, exc in _iter_public_modules():
            if exc is not None:
                output.append(f"### Module: logos.{modname} (Failed to load: {exc})\n")
                continue
            try:
                output.extend(_render_module_dump(modname, mod))
            except Exception as exc:
                output.append(f"### Module: logos.{modname} (Failed to load: {exc})\n")

        text = "\n".join(output)
        if print_output:
            print(text)
        return text



    # MODE 1: Search Query
    if search:
        search_lower = search.lower()
        output.append(f"# Search Results for: '{search}'\n")
        found_something = False
        
        for modname, mod, exc in _iter_public_modules():
            if exc is not None:
                continue
            try:
                for name, val in inspect.getmembers(mod):
                    if name.startswith("_"): continue
                    
                    doc = inspect.getdoc(val) or ""
                    if search_lower in name.lower() or search_lower in doc.lower():
                        found_something = True
                        if inspect.isroutine(val):
                            output.append(f"logos.{modname}.{_render_function(name, val).strip()}")
                        elif inspect.isclass(val):
                            output.append(f"logos.{modname}.class {name}: # {_get_doc_summary(val)}")
            except Exception:
                pass
                
        if not found_something:
            output.append("No matches found.")

    # MODE 2: Detailed help for a specific function/class
    elif obj is not None:
        if inspect.ismodule(obj):
            mod_name = _logos_module_name(obj)
            display_name = mod_name[len("logos."):] if mod_name.startswith("logos.") else mod_name
            output.extend(_render_module(display_name, obj))
        elif inspect.isclass(obj):
            output.extend(_render_class(obj.__name__, obj))
        elif inspect.isfunction(obj) or inspect.ismethod(obj):
            sig = _get_sig(obj)
            output.append(f"# Help for: {obj.__name__}{sig}")
            output.append("-" * 40)
            doc = inspect.getdoc(obj)
            if doc:
                output.append(doc)
            else:
                output.append("No detailed documentation available.")
        else:
            output.append(f"Cannot provide detailed help for type '{type(obj).__name__}'.")

    # MODE 3: Full API Dashboard (The default)
    else:
        output.append("# Logos API Quick Ref")
        output.append("A programmatic overview of my capabilities. Use `logos.api_help(obj)` for deep-dives.\n")

        # Global State
        output.append("### Global State")
        output.append("    logos.config: Persistent configuration (print it to view as YAML)")
        output.append("    logos.verbosity(level): Context manager to mute/debug output")
        output.append("")

        for modname, mod, exc in _iter_public_modules():
            if exc is not None:
                output.append(f"### Module: logos.{modname} (Failed to load: {exc})\n")
                continue
            try:
                output.extend(_render_module(modname, mod))
            except Exception as exc:
                output.append(f"### Module: logos.{modname} (Failed to load: {exc})\n")

    text = "\n".join(output)
    if print_output:
        print(text)
    return text


def _smart_repr(val: Any, max_str_len: int = 100) -> str:
    """
    A context-aware repr that rounds floats, truncates long strings, 
    and handles collections recursively. Optimized for LLM readability.
    """
    if isinstance(val, float):
        # 3 decimal places is the 'sweet spot' for ROS (millimeter precision)
        return f"{val:.3f}"
    
    if isinstance(val, str):
        if len(val) > max_str_len:
            half = max_str_len // 2
            return f"'{val[:half]}...{val[-half:]}'"
        return repr(val)

    if isinstance(val, list):
        return "[" + ", ".join(_smart_repr(x) for x in val) + "]"

    if isinstance(val, tuple):
        return "(" + ", ".join(_smart_repr(x) for x in val) + ")"

    if isinstance(val, dict):
        return "{" + ", ".join(f"{_smart_repr(k)}: {_smart_repr(v)}" for k, v in val.items()) + "}"

    # Fallback for objects, ints, bools, etc.
    return repr(val)