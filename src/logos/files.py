# Logos/src/logos/files.py

"""
This module contains all my tools for interacting with the filesystem.
I can use these functions to explore my workspace, read my memories,
and write new code or data to disk.

Note to self:
    My primary audience is *me* (an LLM), not a human. So I prefer output
    formats that are:
      - predictable
      - token-efficient
      - unambiguous to parse
    Pretty tree glyphs are for humans. Indentation + clear tags are for me.
"""

import fnmatch
import os
import re
from pathlib import Path
from typing import List, Optional, Set, Tuple

from .core import Verbosity, api_call, check_for_interrupt

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


def _matches_any(name: str, patterns: Optional[List[str]]) -> bool:
    """Returns True if `name` matches any glob in `patterns`."""
    if not patterns:
        return False
    return any(fnmatch.fnmatch(name, pat) for pat in patterns)


def _normalize_extensions(show_extensions: Optional[List[str]]) -> Optional[Set[str]]:
    """
    Normalizes extension filters into a lowercase set like {".py", ".md"}.
    If None, no extension filtering is applied.
    """
    if show_extensions is None:
        return None

    out: Set[str] = set()
    for ext in show_extensions:
        ext = ext.strip().lower()
        if not ext:
            continue
        if not ext.startswith("."):
            ext = "." + ext
        out.add(ext)
    return out


def _safe_count_dir_entries(dir_path: Path) -> Optional[int]:
    """Counts directory entries, returning None if it can't be read."""
    try:
        return sum(1 for _ in dir_path.iterdir())
    except OSError:
        return None


def _wrap_words(prefix: str, words: List[str], max_width: int = 110) -> List[str]:
    """
    Wraps a list of words into multiple lines, each starting with `prefix`.
    This is my "ls-ish" compact file listing. It stays readable without
    exploding into one file per line.
    """
    if not words:
        return []

    lines: List[str] = []
    current = prefix

    for w in words:
        if current == prefix:
            candidate = current + w
        else:
            candidate = current + " " + w

        if len(candidate) <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = prefix + w

    if current != prefix:
        lines.append(current)

    return lines


def _relpath_for_display(path: Path, root: Path) -> str:
    """Best-effort relative path (nice for inline blocks)."""
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def _clean_inline_text(raw: str) -> List[str]:
    """
    Cleans file text for inline display.

    - Normalize newlines.
    - Remove leading/trailing *blank* lines.
    - Strip trailing whitespace per line.
    - Preserve indentation inside multi-line content.
    """
    text = raw.replace("\r\n", "\n").replace("\r", "\n")
    text = text.strip("\n")
    lines = [ln.rstrip() for ln in text.splitlines()]

    # Drop leading/trailing blank lines
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()

    return lines


def _render_meta_file(meta_path: Path, indent: str, root: Path) -> List[str]:
    """
    Renders a "meta" file (matched by inline_meta_masks).

    If it's a single line after cleaning: compress it into one line:
        filename [inline] <text>

    If multi-line: emit a fenced block:
        filename
        ```file:relative/path
        ...
        ```
    """
    try:
        raw = meta_path.read_text()
    except Exception as exc:
        return [f"{indent}{meta_path.name} [error {exc}]"]

    lines = _clean_inline_text(raw)

    if not lines:
        return [f"{indent}{meta_path.name} [inline] [empty]"]

    if len(lines) == 1:
        one = lines[0].strip()
        if not one:
            return [f"{indent}{meta_path.name} [inline] [empty]"]
        return [f"{indent}{meta_path.name} [inline] {one}"]

    rel = _relpath_for_display(meta_path, root)
    out: List[str] = []
    out.append(f"{indent}{meta_path.name}")
    out.append(f"{indent}```file:{rel}")
    out.extend(f"{indent}{ln}" for ln in lines)
    out.append(f"{indent}```")
    return out


def _list_visible_entries(
    dir_path: Path,
    show_hidden: bool,
    show_ext: Optional[Set[str]],
    inline_masks: Optional[List[str]],
    ignore_patterns: List[str],
    limit: int,
) -> Tuple[List[Path], List[Path], List[Path], Optional[Tuple[int, int]]]:
    """
    Returns (meta_files, subdirs, normal_files, trunc_info).

    trunc_info is (total_visible_entries_before_trunc, shown_after_trunc) or None.
    """
    try:
        all_entries = list(dir_path.iterdir())
    except OSError:
        return ([], [], [], None)

    candidates: List[Tuple[Path, bool]] = []

    for entry in all_entries:
        name = entry.name

        if _matches_any(name, ignore_patterns):
            continue

        is_meta = _matches_any(name, inline_masks)
        is_hidden = name.startswith(".")

        if is_hidden and not show_hidden and not is_meta:
            continue

        if entry.is_file():
            if show_ext is not None and not is_meta:
                if entry.suffix.lower() not in show_ext:
                    continue

        candidates.append((entry, is_meta))

    # Sort: dirs first, then files; then name.
    candidates.sort(key=lambda t: (t[0].is_file(), t[0].name.lower()))

    trunc_info: Optional[Tuple[int, int]] = None
    if limit > 0 and len(candidates) > limit:
        trunc_info = (len(candidates), limit)
        candidates = candidates[:limit]

    meta_files: List[Path] = []
    subdirs: List[Path] = []
    normal_files: List[Path] = []

    for entry, is_meta in candidates:
        if entry.is_dir():
            subdirs.append(entry)
        elif entry.is_file():
            if is_meta:
                meta_files.append(entry)
            else:
                normal_files.append(entry)

    return (meta_files, subdirs, normal_files, trunc_info)


def _render_tree_recursive(
    dir_path: Path,
    indent: str,
    depth: int,
    show_hidden: bool,
    show_ext: Optional[Set[str]],
    inline_masks: Optional[List[str]],
    limit: int,
    ignore_patterns: List[str],
    root: Path,
) -> List[str]:
    """
    Recursive helper to render a token-efficient directory view.

    Format rules I like:
      - Directories end with "/"
      - Files are grouped in compact [files] lines (ls-ish)
      - Meta files inline as:
            name [inline] one-liner
        or multi-line fenced blocks:
            name
            ```file:relpath
            ...
            ```
      - Truncation and filtering are explicit tags
    """
    check_for_interrupt()

    lines: List[str] = []

    # Artifacts are summarized, never traversed.
    if dir_path.name == "artifacts":
        try:
            file_count = sum(
                1
                for name in os.listdir(dir_path)
                if os.path.isfile(os.path.join(dir_path, name))
            )
            lines.append(f"{indent}{dir_path.name}/ [summarized files={file_count}]")
        except OSError as exc:
            lines.append(f"{indent}{dir_path.name}/ [error {exc}]")
        return lines

    lines.append(f"{indent}{dir_path.name}/")

    if depth <= 0:
        total = _safe_count_dir_entries(dir_path)
        if total:
            lines.append(f"{indent}  [not traversed items={total}]")
        return lines

    meta_files, subdirs, normal_files, trunc_info = _list_visible_entries(
        dir_path=dir_path,
        show_hidden=show_hidden,
        show_ext=show_ext,
        inline_masks=inline_masks,
        ignore_patterns=ignore_patterns,
        limit=limit,
    )

    child_indent = indent + "  "

    # If the directory can't be read, make that explicit and bail.
    if not meta_files and not subdirs and not normal_files:
        total = _safe_count_dir_entries(dir_path)
        if total is None:
            lines.append(f"{child_indent}[error cannot read directory]")
            return lines
        if total > 0:
            lines.append(f"{child_indent}[filtered items={total}]")
        return lines

    # Meta files first: context for me.
    for meta_path in meta_files:
        lines.extend(_render_meta_file(meta_path, child_indent, root))

    # Then structure (subdirs).
    for sub in subdirs:
        lines.extend(
            _render_tree_recursive(
                dir_path=sub,
                indent=child_indent,
                depth=depth - 1,
                show_hidden=show_hidden,
                show_ext=show_ext,
                inline_masks=inline_masks,
                limit=limit,
                ignore_patterns=ignore_patterns,
                root=root,
            )
        )

    # Then bulk files (compact listing).
    if normal_files:
        names = [p.name for p in normal_files]
        lines.extend(_wrap_words(f"{child_indent}[files] ", names))

    if trunc_info is not None:
        total, shown = trunc_info
        lines.append(f"{child_indent}[truncated total={total} shown={shown}]")

    return lines


def tree(
    start_path: str = ".",
    max_depth: int = 5,
    show_hidden: bool = True,
    show_extensions: Optional[List[str]] = None,
    inline_meta_masks: Optional[List[str]] = None,
    ignore_globs: Optional[List[str]] = None,
    files_per_dir_limit: int = 50,
) -> str:
    """
    Generates a token-efficient tree view of the filesystem with optional inline metadata.

    Args:
        start_path:
            Directory to start the tree from. Defaults to CWD.
        max_depth:
            Maximum depth to traverse. Defaults to 5. Use -1 for unlimited.
        show_hidden:
            If True, shows files and directories starting with '.'.
            Hidden entries that match `inline_meta_masks` are always shown.
        show_extensions:
            List of file extensions to display (e.g. [".py", ".yaml"]).
            If None, shows all files. Files matching `inline_meta_masks`
            are always shown regardless of extension.
        inline_meta_masks:
            Filename patterns. Matching files will have their contents
            inlined under the file node (one-liner compressed when possible).
        ignore_globs:
            Extra filename patterns to ignore, in addition to .logosignore
            and built-in defaults.
        files_per_dir_limit:
            Safety limit to prevent spamming context with huge directories.

    Returns:
        A string representing the directory tree.

    Note to self:
        - I prefer indentation + tags over box-drawing glyphs.
        - I group normal files into compact lines (ls-ish) with a leading '| '
        - I inline meta files because they usually contain intent/context.
        - The `artifacts/` directory is always summarized and not traversed.
        - Meta masks override both `show_hidden` and `show_extensions`.
    """
    if max_depth < 0:
        max_depth = 1_000  # if -1 then effectively unlimited

    root = Path(start_path)

    if not root.exists():
        return f"{start_path} [error not found]"
    if root.is_file():
        return f"{start_path} [error expected directory]"

    ignore_patterns = _load_ignore_patterns()
    if ignore_globs:
        ignore_patterns.extend(ignore_globs)

    show_ext = _normalize_extensions(show_extensions)

    # Render with a root header that doesn't waste tokens.
    # If start_path is ".", show "./" (classic).
    header = "./" if str(root) in (".", "") else f"{root.as_posix().rstrip('/')}/"

    # For recursion, I want to print names, so I render children under the header.
    # That keeps the output compact and avoids repeating absolute paths.
    lines: List[str] = [header]

    # Special-case: render root contents without printing root.name/ again.
    meta_files, subdirs, normal_files, trunc_info = _list_visible_entries(
        dir_path=root,
        show_hidden=show_hidden,
        show_ext=show_ext,
        inline_masks=inline_meta_masks,
        ignore_patterns=ignore_patterns,
        limit=files_per_dir_limit,
    )

    if max_depth <= 0:
        total = _safe_count_dir_entries(root)
        if total:
            lines.append(f"  [not traversed items={total}]")
        return "\n".join(lines).rstrip()

    if not meta_files and not subdirs and not normal_files:
        total = _safe_count_dir_entries(root)
        if total is None:
            lines.append("  [error cannot read directory]")
        elif total > 0:
            lines.append(f"  [filtered items={total}]")
        return "\n".join(lines).rstrip()

    for meta_path in meta_files:
        lines.extend(_render_meta_file(meta_path, "  ", root))

    for sub in subdirs:
        # The recursive renderer prints "subdirname/" itself.
        if sub.name == "artifacts":
            # Keep artifacts behavior consistent even at root.
            try:
                file_count = sum(
                    1
                    for name in os.listdir(sub)
                    if os.path.isfile(os.path.join(sub, name))
                )
                lines.append(f"  {sub.name}/ [summarized files={file_count}]")
            except OSError as exc:
                lines.append(f"  {sub.name}/ [error {exc}]")
            continue

        lines.extend(
            _render_tree_recursive(
                dir_path=sub,
                indent="  ",
                depth=max_depth - 1,
                show_hidden=show_hidden,
                show_ext=show_ext,
                inline_masks=inline_meta_masks,
                limit=files_per_dir_limit,
                ignore_patterns=ignore_patterns,
                root=root,
            )
        )

    if normal_files:
        names = [p.name for p in normal_files]
        lines.extend(_wrap_words("  [files] ", names))

    if trunc_info is not None:
        total, shown = trunc_info
        lines.append(f"  [truncated total={total} shown={shown}]")

    return "\n".join(lines).rstrip()


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
    with open(path, "a") as f:
        f.write(content)


def show(path: str, max_chars: int = 2000, pattern: Optional[str] = None) -> str:
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