# Logos/src/logos/files.py

"""
This module contains all my tools for interacting with the filesystem.
I can use these functions to explore my workspace, read my memories,
and write new code or data to disk.
"""

import os
from pathlib import Path
import fnmatch
import re
from .core import check_for_interrupt, api_call, Verbosity
from typing import List, Optional, Tuple, Union

__all__ = ["tree", "read", "write", "append", "show"]


WORKSPACE_PATH = Path.cwd()


def _load_ignore_patterns() -> List[str]:
    """Loads patterns from a .logosignore file in the workspace root."""
    ignore_file = WORKSPACE_PATH / ".logosignore"
    patterns = ["__pycache__", "*.pyc", ".DS_Store"]  # Default ignores
    if ignore_file.exists():
        with open(ignore_file, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    patterns.append(line)
    return patterns


def _tree_recursive(
    dir_path: Path,
    prefix: str,
    depth: int,
    show_hidden: bool,
    show_ext: Optional[List[str]],
    inline_masks: Optional[List[str]],
    limit: int,
    ignore_patterns: List[str],
) -> str:
    """
    Recursive helper to build the directory tree string.

    - Respects .logosignore-style patterns.
    - Shows hidden entries only if `show_hidden` is True, except that
      entries matching `inline_masks` are always visible.
    - Only files whose suffix is in `show_ext` are shown, unless they
      match an `inline_masks` pattern (meta overrides extension filter).
    - Avoids stray blank lines when a directory has no visible children.
    """
    check_for_interrupt()

    output_lines: List[str] = []

    try:
        all_entries = sorted(
            dir_path.iterdir(), key=lambda p: (p.is_file(), p.name.lower())
        )
    except OSError as exc:
        output_lines.append(f"{prefix}└── [Error reading directory: {exc}]")
        return "\n".join(output_lines).rstrip()

    # First pass: apply ignore + hidden (with meta override)
    entries_meta: List[Tuple[object, bool]] = []
    for entry in all_entries:
        name = entry.name
        is_ignored = any(fnmatch.fnmatch(name, pattern) for pattern in ignore_patterns)

        # Is this a "meta" file that should be inlined / shown even if hidden?
        is_meta = False
        if inline_masks:
            for mask in inline_masks:
                if fnmatch.fnmatch(name, mask):
                    is_meta = True
                    break

        if is_ignored:
            continue

        is_hidden = name.startswith(".")
        if is_hidden and not show_hidden and not is_meta:
            # Hidden and not explicitly allowed by meta masks
            continue

        entries_meta.append((entry, is_meta))

    # Apply per-directory safety limit
    if len(entries_meta) > limit:
        entries_meta = entries_meta[:limit]
        entries_meta.append(("... (truncated)", False))

    # Second pass: determine which entries are actually *rendered*
    visible_entries: List[Tuple[object, bool]] = []
    for entry, is_meta in entries_meta:
        if isinstance(entry, str):
            visible_entries.append((entry, False))
            continue

        if entry.is_dir():
            visible_entries.append((entry, is_meta))
        elif entry.is_file():
            if show_ext is None:
                visible_entries.append((entry, is_meta))
            else:
                # Meta masks override show_ext filtering.
                if is_meta or entry.suffix.lower() in show_ext:
                    visible_entries.append((entry, is_meta))

    for idx, (entry, is_meta) in enumerate(visible_entries):
        is_last = idx == len(visible_entries) - 1
        connector = "└── " if is_last else "├── "

        # Sentinel line like "... (truncated)"
        if isinstance(entry, str):
            output_lines.append(prefix + connector + entry)
            continue

        # Directories
        if entry.is_dir():
            # Special handling for artifacts directory
            if entry.name == "artifacts":
                try:
                    file_count = len(
                        [
                            name
                            for name in os.listdir(entry)
                            if os.path.isfile(os.path.join(entry, name))
                        ]
                    )
                    output_lines.append(f"{prefix}{connector}{entry.name}/")
                    child_prefix = prefix + ("    " if is_last else "│   ")
                    output_lines.append(
                        f"{child_prefix}└── (Contains {file_count} files)"
                    )
                except FileNotFoundError:
                    output_lines.append(
                        f"{prefix}{connector}{entry.name}/ [Not found]"
                    )
                continue

            # Normal directory
            output_lines.append(f"{prefix}{connector}{entry.name}/")

            if depth != 0:
                child_prefix = prefix + ("    " if is_last else "│   ")
                subtree = _tree_recursive(
                    entry,
                    child_prefix,
                    depth - 1,
                    show_hidden,
                    show_ext,
                    inline_masks,
                    limit,
                    ignore_patterns,
                )

                if subtree.strip():
                    # Only append non-empty subtrees to avoid stray blank lines.
                    output_lines.append(subtree)
                else:
                    # Directory has no *visible* children but may still contain stuff.
                    try:
                        total_entries = list(entry.iterdir())
                    except OSError:
                        total_entries = []

                    if total_entries:
                        total_count = len(total_entries)
                        output_lines.append(
                            f"{child_prefix}└── (Contains {total_count} items) "
                            # f"filtered by settings)"
                        )
            continue

        # Files
        if entry.is_file():
            # Meta / inlineable files: prettier formatting, no tree chars on content.
            if is_meta and inline_masks:
                header = f"{prefix}{connector}{entry.name}  -  Contents:"
                output_lines.append(header)

                content_indent = prefix + ("    " if is_last else "│   ") + "    "
                try:
                    content = entry.read_text().rstrip("\n")
                except Exception as exc:
                    output_lines.append(f"{content_indent}[Error reading file: {exc}]")
                    continue

                if content:
                    for content_line in content.splitlines():
                        output_lines.append(content_indent + content_line)
                else:
                    output_lines.append(content_indent + "[Empty file]")
            else:
                # Normal file
                output_lines.append(f"{prefix}{connector}{entry.name}")

    return "\n".join(output_lines).rstrip()


def tree(
    start_path: str = ".",
    max_depth: int = 3,
    show_hidden: bool = True,
    show_extensions: Optional[List[str]] = None,
    inline_meta_masks: Optional[List[str]] = None,
    ignore_globs: Optional[List[str]] = None,
    files_per_dir_limit: int = 50,
) -> str:
    """
    Generates an intelligent, detailed tree view of the filesystem.

    Args:
        start_path:
            Directory to start the tree from. Defaults to CWD.
        max_depth:
            Maximum depth to traverse. Defaults to 3. Use -1 for unlimited.
        show_hidden:
            If True, shows files and directories starting with '.'.
            Hidden entries that match `inline_meta_masks` are always shown.
        show_extensions:
            List of file extensions to display (e.g. [".py", ".yaml"]).
            If None, shows all files. Files matching `inline_meta_masks`
            are always shown regardless of extension.
        inline_meta_masks:
            Filename patterns. Matching files will have their contents
            inlined under the file node.
        ignore_globs:
            Extra filename patterns to ignore, in addition to .logosignore
            and built-in defaults.
        files_per_dir_limit:
            Safety limit to prevent spamming the context with huge dirs.

    Returns:
        A string representing the directory tree.

    Note to self:
        - This is my primary tool for creating a broad view of my workspace.
        - The `artifacts/` directory is always summarized and not traversed.
        - Meta masks override both `show_hidden` and `show_extensions`.
    """
    if max_depth < 0:
        max_depth = 1_000  # if -1 then effectively unlimited

    path_root = Path(start_path)
    ignore_patterns = _load_ignore_patterns()
    if ignore_globs:
        ignore_patterns.extend(ignore_globs)

    cwd = Path.cwd()
    tree_str = f"Current Working Directory: {cwd}\n\n"
    tree_str += f"{path_root}\n"
    tree_str += _tree_recursive(
        path_root,
        "",
        max_depth,
        show_hidden,
        show_extensions,
        inline_meta_masks,
        files_per_dir_limit,
        ignore_patterns,
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

@api_call(default_verbosity=Verbosity.ACK)
def write(path: str, content: str):
    """
    Writes content to a file, overwriting it if it exists.

    Args:
        path: The path to the file to write.
        content: The string content to write to the file.
        
    Note to self:
        Use this to save new information or replace existing files.
    """
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)

@api_call(default_verbosity=Verbosity.ACK)
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
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'a') as f:
        f.write(content)


def show(
    path: str,
    max_chars: int = 2000,
    pattern: Optional[str] = None
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
