# preload_api/logos/files.py

"""
This module contains all my tools for interacting with the filesystem.
I can use these functions to explore my workspace, read my memories,
and write new code or data to disk.
"""

import os
from pathlib import Path
import fnmatch
from .core import Verbosity, api_call   
import re
from .core import check_for_interrupt

__all__ = ["tree", "read", "write", "append", "show"]

WORKSPACE_PATH = Path.cwd()

def _load_ignore_patterns():
    """Loads patterns from a .logosignore file in the workspace root."""
    ignore_file = WORKSPACE_PATH / ".logosignore"
    patterns = ['__pycache__', '*.pyc', '.DS_Store'] # Default ignores
    if ignore_file.exists():
        with open(ignore_file, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    patterns.append(line)
    return patterns

def _tree_recursive(
    dir_path: Path,
    prefix: str,
    depth: int,
    show_hidden: bool,
    show_ext: list[str] | None,
    inline_masks: list[str] | None,
    limit: int,
    ignore_patterns: list[str]
) -> str:
    """Recursive helper function to build the tree string."""
    try:
        entries = sorted(list(dir_path.iterdir()), key=lambda p: (p.is_file(), p.name.lower()))
    except OSError as e:
        return f"{prefix}└── [Error: {e.strerror}]\n"

    # Filter entries based on hidden status and ignore patterns
    if not show_hidden:
        entries = [e for e in entries if not e.name.startswith('.')]
    
    filtered_entries = []
    for e in entries:
        if not any(fnmatch.fnmatch(e.name, pattern) for pattern in ignore_patterns):
            filtered_entries.append(e)
    entries = filtered_entries

    # Apply limit and add truncation message if needed
    if len(entries) > limit:
        entries = entries[:limit]
        entries.append('... (truncated)')

    output_lines = []
    for i, entry in enumerate(entries):
        is_last = (i == len(entries) - 1)
        connector = "└── " if is_last else "├── "
        
        # Handle the special truncation string
        if isinstance(entry, str):
            output_lines.append(prefix + connector + entry)
            continue

        # Special handling for artifacts directory
        if entry.is_dir() and entry.name == 'artifacts':
            try:
                file_count = len([name for name in os.listdir(entry) if os.path.isfile(os.path.join(entry, name))])
                output_lines.append(f"{prefix}{connector}{entry.name}/")
                output_lines.append(f"{prefix}{'    ' if is_last else '│   '}└── (Contains {file_count} files)")
            except FileNotFoundError:
                output_lines.append(f"{prefix}{connector}{entry.name}/ [Not found]")
            continue # Skip normal processing for this directory

        # Handle Files
        if entry.is_file():
            if show_ext and entry.suffix.lower() not in show_ext:
                continue # Skip this file if extension doesn't match
            
            line = prefix + connector + entry.name
            output_lines.append(line)
            
            # Check for inline meta content
            if inline_masks and any(fnmatch.fnmatch(entry.name, mask) for mask in inline_masks):
                try:
                    content = entry.read_text().strip()
                    content_prefix = prefix + ("    " if is_last else "│   ")
                    for content_line in content.splitlines():
                        output_lines.append(f"{content_prefix}└── {content_line}")
                except Exception as e:
                    output_lines.append(f"{content_prefix}└── [Error reading file: {e}]")
        
        # Handle Directories
        elif entry.is_dir():
            line = prefix + connector + entry.name + "/"
            output_lines.append(line)
            if depth != 0:
                new_prefix = prefix + ("    " if is_last else "│   ")
                # Get the subtree as a single string and append it
                subtree = _tree_recursive(entry, new_prefix, depth - 1, show_hidden, show_ext, inline_masks, limit, ignore_patterns)
                output_lines.append(subtree)

    # Join all lines, ensuring there's a newline between them.
    # The rstrip() handles any trailing newline from the last recursive call.
    return "\n".join(output_lines).rstrip()


def tree(
    start_path: str = '.',
    max_depth: int = 3,
    show_hidden: bool = True,
    show_extensions: list[str] | None = None,
    inline_meta_masks: list[str] | None = None,
    ignore_globs: list[str] | None = None,
    files_per_dir_limit: int = 50
) -> str:
    """
    Generates an intelligent, detailed tree view of the filesystem.

    Args:
        start_path: The directory to start the tree from. Defaults to CWD.
        max_depth: The maximum depth to traverse. Defaults to 3. -1 for unlimited.
        show_hidden: If True, shows files and directories starting with '.'.
        show_extensions: A list of file extensions to display. If None, shows all.
        inline_meta_masks: A list of filename patterns (e.g., "*.meta", "README.*").
                           The content of matching files will be displayed inline.
        ignore_globs: A list of filename patterns to ignore, in addition to .logosignore.
        files_per_dir_limit: A safety limit to prevent spamming the context.

    Returns:
        A string representing the directory tree.

    Note to self:
        This is my primary tool for exploring my workspace. I can use
        `logos.state.files` to configure its default behavior. The `artifacts/`
        directory is always summarized and not traversed.
    """
    path_root = Path(start_path)
    ignore_patterns = _load_ignore_patterns()
    if ignore_globs:
        ignore_patterns.extend(ignore_globs)

    tree_str = f"{path_root}\n"
    tree_str += _tree_recursive(
        path_root,
        "",
        max_depth,
        show_hidden,
        show_extensions,
        inline_meta_masks,
        files_per_dir_limit,
        ignore_patterns
    )
    return tree_str.strip()


def read(path: str) -> str:
    """
    Reads the entire content of a file.

    Args:
        path: The path to the file to read.

    Returns:
        The content of the file as a string.
        
    Note to self:
        This is my primary way of recalling information I've saved.
    """
    return Path(path).read_text()

def write(path: str, content: str):
    """
    Writes content to a file, overwriting it if it exists.

    Args:
        path: The path to the file to write.
        content: The string content to write to the file.
        
    Note to self:
        Use this to save new information or replace existing files.
    """
    Path(path).write_text(content)

def append(path: str, content: str):
    """
    Appends content to the end of a file.

    Args:
        path: The path to the file to append to.
        content: The string content to append.

    Note to self:
        Useful for logging or adding to existing notes without reading the
        whole file first.
    """
    with open(path, 'a') as f:
        f.write(content)

def show(
    path: str,
    max_chars: int = 2000,
    pattern: str | None = None
) -> str:
    """
    Prints (and returns) a possibly filtered, truncated view of a file.

    Args:
        path:
            Path to the file.
        max_chars:
            Maximum number of characters to print into my io_buffer.
        pattern:
            Optional regular expression. If provided, only lines matching
            this pattern are included before truncation.

    Returns:
        The string that was printed (after filtering and truncation).

    Note to self:
        Use this when I want to review a file's contents directly in my
        context. For more complex processing, use logos.files.read() and
        handle filtering in Python.
    """
    check_for_interrupt()

    content = read(path)

    if pattern is not None:
        regex = re.compile(pattern)
        lines = content.splitlines()
        filtered_lines = [line for line in lines if regex.search(line)]
        content = "\n".join(filtered_lines)

    snippet = content[:max_chars]
    print(snippet)

    if len(content) > max_chars:
        truncated = len(content) - max_chars
        print(f"\n[... truncated {truncated} characters ...]")

    return snippet
