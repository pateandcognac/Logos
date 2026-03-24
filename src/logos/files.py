# Logos/src/logos/files.py

"""
This module contains all my tools for interacting with the filesystem.

I use these functions to explore my workspace, read my memories, inspect code,
and make careful edits to files on disk.

Note to self:
    My primary audience is me. I want output and behavior that are:

    - predictable
    - token-efficient
    - explicit when something is ambiguous
    - safe enough that I do not quietly damage files

    Pretty tree glyphs are for humans. Indentation, tags, and hard failure on
    ambiguous edits are for me.
"""

import difflib
import fnmatch
import os
import re
import tempfile
from pathlib import Path
from typing import List, Optional, Pattern, Set, Tuple

from .core import Verbosity, api_call, check_for_interrupt

__all__ = [
    "FileEditError",
    "tree",
    "read",
    "write",
    "append",
    "show",
    "diff",
    "replace_exact",
    "replace_regex",
    "insert_before",
    "insert_after",
]

WORKSPACE_PATH = Path.cwd()


class FileEditError(Exception):
    """
    I raise this when a file edit cannot be completed safely.

    Note to self:
        I prefer failing loudly over making a "best guess" when an edit is
        ambiguous. Silent corruption is worse than a hard stop.
    """


def _load_ignore_patterns() -> List[str]:
    """
    Load ignore patterns from `.logosignore` in my workspace root.

    Note to self:
        I keep a few default junk patterns built in, then extend them with
        user-defined patterns when the ignore file exists.
    """
    ignore_file = WORKSPACE_PATH / ".logosignore"
    patterns = ["__pycache__", "*.pyc", ".DS_Store"]

    if ignore_file.exists():
        with open(ignore_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    patterns.append(line)

    return patterns


def _matches_any(name: str, patterns: Optional[List[str]]) -> bool:
    """
    Return True when `name` matches any glob pattern in `patterns`.

    Note to self:
        I treat `None` and empty lists as "no match rules".
    """
    if not patterns:
        return False
    return any(fnmatch.fnmatch(name, pat) for pat in patterns)


def _normalize_extensions(show_extensions: Optional[List[str]]) -> Optional[Set[str]]:
    """
    Normalize extension filters into a lowercase set like {".py", ".md"}.

    Args:
        show_extensions:
            A list of extensions with or without a leading dot, or None.

    Returns:
        A normalized lowercase set of extensions, or None when no filtering is
        requested.

    Note to self:
        I normalize aggressively so callers do not need to care whether they
        passed "py" or ".py".
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
    """
    Count entries in a directory.

    Returns:
        The number of entries, or None if I cannot read the directory.

    Note to self:
        I use this for summaries and fallback status lines. I do not want an
        unreadable directory to crash a tree render.
    """
    try:
        return sum(1 for _ in dir_path.iterdir())
    except OSError:
        return None


def _wrap_words(prefix: str, words: List[str], max_width: int = 110) -> List[str]:
    """
    Wrap a list of words into compact lines that all begin with `prefix`.

    Args:
        prefix:
            The text prepended to each output line.
        words:
            The tokens to pack into wrapped lines.
        max_width:
            The maximum width of a rendered line.

    Returns:
        A list of wrapped lines.

    Note to self:
        This is my compact "ls-ish" file listing. It stays readable without
        wasting tokens on one filename per line.
    """
    if not words:
        return []

    lines: List[str] = []
    current = prefix

    for word in words:
        if current == prefix:
            candidate = current + word
        else:
            candidate = current + " " + word

        if len(candidate) <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = prefix + word

    if current != prefix:
        lines.append(current)

    return lines


def _relpath_for_display(path: Path, root: Path) -> str:
    """
    Return a best-effort relative path for display.

    Note to self:
        Relative paths are nicer in inline blocks. If I cannot make the path
        relative to the requested root, I fall back to the full POSIX path.
    """
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def _clean_inline_text(raw: str) -> List[str]:
    """
    Clean file text for inline display.

    I normalize newlines, strip leading and trailing blank lines, remove
    trailing whitespace from each line, and preserve internal indentation.

    Args:
        raw:
            The raw file contents.

    Returns:
        A cleaned list of lines.

    Note to self:
        This keeps inline file previews compact and stable without mangling the
        meaningful indentation inside multi-line content.
    """
    text = raw.replace("\r\n", "\n").replace("\r", "\n")
    text = text.strip("\n")
    lines = [line.rstrip() for line in text.splitlines()]

    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()

    return lines


def _render_meta_file(meta_path: Path, indent: str, root: Path) -> List[str]:
    """
    Render a metadata-style file matched by an inline mask.

    If the cleaned content is a single line, I compress it inline.
    If it is multi-line, I emit a fenced block with a relative file label.

    Args:
        meta_path:
            The file to render.
        indent:
            The indentation prefix for every emitted line.
        root:
            The root path used for relative display.

    Returns:
        A list of rendered lines.

    Note to self:
        I show these files first because they often contain intent and context
        that helps me reason about the rest of a directory.
    """
    try:
        raw = meta_path.read_text(encoding="utf-8")
    except Exception as exc:
        return [f"{indent}{meta_path.name} [error {exc}]"]

    lines = _clean_inline_text(raw)

    if not lines:
        return [f"{indent}{meta_path.name} [inline] [empty]"]

    if len(lines) == 1:
        one_line = lines[0].strip()
        if not one_line:
            return [f"{indent}{meta_path.name} [inline] [empty]"]
        return [f"{indent}{meta_path.name} [inline] {one_line}"]

    rel = _relpath_for_display(meta_path, root)
    out: List[str] = []
    out.append(f"{indent}{meta_path.name}")
    out.append(f"{indent}```file:{rel}")
    out.extend(f"{indent}{line}" for line in lines)
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
    List and classify visible entries in a directory.

    Args:
        dir_path:
            The directory to inspect.
        show_hidden:
            Whether to include dotfiles and dot-directories.
        show_ext:
            Optional set of allowed file extensions.
        inline_masks:
            Optional glob patterns for files whose contents should be rendered
            inline.
        ignore_patterns:
            Glob patterns to exclude.
        limit:
            Maximum number of visible entries to keep.

    Returns:
        A tuple of:
            - meta_files
            - subdirs
            - normal_files
            - truncation info as (total_before_truncation, shown_after_truncation)
              or None

    Note to self:
        I classify entries before rendering so the tree can present context
        first, then structure, then bulk files.
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

    candidates.sort(key=lambda item: (item[0].is_file(), item[0].name.lower()))

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
    Recursively render a token-efficient directory view.

    Args:
        dir_path:
            The directory I am rendering.
        indent:
            The current indentation prefix.
        depth:
            Remaining traversal depth.
        show_hidden:
            Whether to include hidden entries.
        show_ext:
            Optional extension filter.
        inline_masks:
            Optional filename masks for inlined file content.
        limit:
            Maximum visible entries per directory.
        ignore_patterns:
            Glob patterns to ignore.
        root:
            The overall tree root for relative display.

    Returns:
        A list of rendered lines.

    Note to self:
        My format rules are simple:
            - directories end with "/"
            - normal files are grouped into compact lines prefixed with '|'
            - meta files inline their contents
            - truncation and filtering are stated explicitly
    """
    check_for_interrupt()

    lines: List[str] = []

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

    if not meta_files and not subdirs and not normal_files:
        total = _safe_count_dir_entries(dir_path)
        if total is None:
            lines.append(f"{child_indent}[error cannot read directory]")
            return lines
        if total > 0:
            lines.append(f"{child_indent}[filtered items={total}]")
        return lines

    for meta_path in meta_files:
        lines.extend(_render_meta_file(meta_path, child_indent, root))

    for subdir in subdirs:
        lines.extend(
            _render_tree_recursive(
                dir_path=subdir,
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

    if normal_files:
        names = [path.name for path in normal_files]
        lines.extend(_wrap_words(f"{child_indent}| ", names))

    if trunc_info is not None:
        total, shown = trunc_info
        lines.append(f"{child_indent}[truncated total={total} shown={shown}]")

    return lines


def _read_text(path: Path) -> str:
    """
    Read UTF-8 text from a file.

    Args:
        path:
            The file to read.

    Returns:
        The full text content.

    Note to self:
        I keep my text I/O explicitly UTF-8 so behavior stays boring and
        repeatable across environments.
    """
    return path.read_text(encoding="utf-8")


def _atomic_write_text(path: Path, content: str) -> None:
    """
    Write text to disk atomically.

    Args:
        path:
            The destination file.
        content:
            The full text to write.

    Note to self:
        I write to a temporary file in the same directory, then replace the
        target. That reduces the chance that I leave a half-written file behind
        if something goes sideways mid-write.
    """
    path.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=str(path.parent),
        delete=False,
    ) as temp_file:
        temp_file.write(content)
        temp_name = temp_file.name

    os.replace(temp_name, str(path))


def _compile_regex(pattern: str, flags: int = 0) -> Pattern[str]:
    """
    Compile a regular expression and raise a clearer error on failure.

    Args:
        pattern:
            The regex pattern string.
        flags:
            Regex compilation flags.

    Returns:
        A compiled regex object.

    Raises:
        FileEditError:
            If the pattern is invalid.

    Note to self:
        Regex failures are easier to debug when I re-raise them as my own edit
        error type with the original message attached.
    """
    try:
        return re.compile(pattern, flags)
    except re.error as exc:
        raise FileEditError(f"invalid regex pattern: {exc}") from exc


def _normalize_newline_for_insert(
    original_text: str,
    insertion: str,
) -> str:
    """
    Normalize inserted text so it matches the file's newline style.

    Args:
        original_text:
            The full original file content.
        insertion:
            The text I want to insert.

    Returns:
        The insertion text with line endings adapted to the original content.

    Note to self:
        I default to `\\n`. If the target file clearly uses Windows newlines, I
        convert inserted text to `\\r\\n` so I do not create mixed line endings.
    """
    newline = "\r\n" if "\r\n" in original_text else "\n"
    normalized = insertion.replace("\r\n", "\n").replace("\r", "\n")
    return normalized.replace("\n", newline)


def _count_literal_occurrences(text: str, needle: str) -> int:
    """
    Count non-overlapping occurrences of a literal substring.

    Args:
        text:
            The text to search.
        needle:
            The literal substring to count.

    Returns:
        The number of non-overlapping matches.

    Note to self:
        I use this before exact replacement so I can fail when an edit is
        ambiguous or unexpectedly missing.
    """
    if needle == "":
        raise FileEditError("empty search text is not allowed")
    return text.count(needle)


def _validate_expected_count(
    actual_count: int,
    expected_count: int,
    context: str,
) -> None:
    """
    Ensure a match count is exactly what I expected.

    Args:
        actual_count:
            The observed number of matches.
        expected_count:
            The required number of matches.
        context:
            A short label describing the operation.

    Raises:
        FileEditError:
            If the count does not match.

    Note to self:
        Match-count validation is the difference between "careful edit" and
        "roulette wheel."
    """
    if expected_count < 1:
        raise FileEditError("expected_count must be at least 1")

    if actual_count != expected_count:
        raise FileEditError(
            f"{context} expected {expected_count} match(es), found {actual_count}"
        )


def _make_unified_diff(
    old_text: str,
    new_text: str,
    path_label: str,
    context_lines: int = 3,
) -> str:
    """
    Build a unified diff string for two text snapshots.

    Args:
        old_text:
            The original content.
        new_text:
            The updated content.
        path_label:
            A label to show in the diff headers.
        context_lines:
            Number of context lines around each hunk.

    Returns:
        A unified diff string.

    Note to self:
        Diffs are excellent for review and logs, even when they are not my
        primary editing primitive.
    """
    old_lines = old_text.splitlines(keepends=True)
    new_lines = new_text.splitlines(keepends=True)

    diff_lines = difflib.unified_diff(
        old_lines,
        new_lines,
        fromfile=f"a/{path_label}",
        tofile=f"b/{path_label}",
        n=context_lines,
    )
    return "".join(diff_lines)


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
    Generate a token-efficient tree view of the filesystem.

    Args:
        start_path:
            The directory where I start the tree. Defaults to ".".
        max_depth:
            The maximum traversal depth. Use -1 for effectively unlimited depth.
        show_hidden:
            If True, I include hidden files and directories.
        show_extensions:
            Optional list of extensions to include, like [".py", ".yaml"].
        inline_meta_masks:
            Optional filename patterns whose contents I should inline.
        ignore_globs:
            Optional extra ignore patterns in addition to `.logosignore` and my
            built-in defaults.
        files_per_dir_limit:
            A per-directory safety cap to keep large trees from flooding my
            context.

    Returns:
        A rendered directory tree as a string.

    Note to self:
        I prefer indentation and tags over decorative box-drawing characters.
        I inline small metadata files because they often contain the intent I
        need to understand a workspace quickly.
    """
    if max_depth < 0:
        max_depth = 1_000

    root = Path(start_path)

    if not root.exists():
        return f"{start_path} [error not found]"
    if root.is_file():
        return f"{start_path} [error expected directory]"

    ignore_patterns = _load_ignore_patterns()
    if ignore_globs:
        ignore_patterns.extend(ignore_globs)

    show_ext = _normalize_extensions(show_extensions)

    header = "./" if str(root) in (".", "") else f"{root.as_posix().rstrip('/')}/"
    lines: List[str] = [header]

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

    for subdir in subdirs:
        if subdir.name == "artifacts":
            try:
                file_count = sum(
                    1
                    for name in os.listdir(subdir)
                    if os.path.isfile(os.path.join(subdir, name))
                )
                lines.append(f"  {subdir.name}/ [summarized files={file_count}]")
            except OSError as exc:
                lines.append(f"  {subdir.name}/ [error {exc}]")
            continue

        lines.extend(
            _render_tree_recursive(
                dir_path=subdir,
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
        names = [path.name for path in normal_files]
        lines.extend(_wrap_words("  | ", names))

    if trunc_info is not None:
        total, shown = trunc_info
        lines.append(f"  [truncated total={total} shown={shown}]")

    return "\n".join(lines).rstrip()


def read(path: str) -> str:
    """
    Read the entire text content of a file.

    Args:
        path:
            The path to the file I want to read.

    Returns:
        The file content as a string.

    Note to self:
        This is my most direct way to recall something I have saved on disk.
    """
    return _read_text(Path(path))


@api_call(default_verbosity=Verbosity.ACK)
def write(path: str, content: str):
    """
    Write text to a file, replacing any existing content.

    Args:
        path:
            The path to the file I want to write.
        content:
            The full text content I want to save.

    Note to self:
        I create parent directories as needed. I also write atomically so I do
        not leave a mangled partial file behind if the write gets interrupted.
    """
    _atomic_write_text(Path(path), content)


@api_call(default_verbosity=Verbosity.ACK)
def append(path: str, content: str):
    """
    Append text to the end of a file.

    Args:
        path:
            The file I want to extend.
        content:
            The text I want to append.

    Note to self:
        This is handy for logs and incremental notes when I do not need to
        inspect the whole file first.
    """
    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)

    with open(file_path, "a", encoding="utf-8") as f:
        f.write(content)


def show(path: str, max_chars: int = 32767, pattern: Optional[str] = None) -> str:
    """
    Print and return a possibly filtered, truncated view of a file.

    Args:
        path:
            The file I want to inspect.
        max_chars:
            The maximum number of characters I should print and return.
        pattern:
            An optional regular expression. If provided, I keep only matching
            lines before truncation.

    Returns:
        The displayed text snippet.

    Note to self:
        I use this when I want quick visibility in my context window. For more
        complex processing, I should read the whole file and reason in Python.
    """
    check_for_interrupt()

    content = read(path)

    if pattern is not None:
        regex = _compile_regex(pattern)
        lines = content.splitlines()
        filtered_lines = [line for line in lines if regex.search(line)]
        content = "\n".join(filtered_lines)

    snippet = content[:max_chars]
    print(snippet)

    if len(content) > max_chars:
        truncated = len(content) - max_chars
        print(f"\n[... truncated {truncated} characters ...]")

    return snippet


def diff(path: str, new_content: str, context_lines: int = 3) -> str:
    """
    Show how a file would change if I replaced it with `new_content`.

    Args:
        path:
            The target file path.
        new_content:
            The full replacement content to compare against the current file.
        context_lines:
            The number of surrounding context lines to include per diff hunk.

    Returns:
        A unified diff string.

    Note to self:
        I can use this for review, logging, and "show me before you commit"
        style workflows.
    """
    file_path = Path(path)
    old_content = _read_text(file_path) if file_path.exists() else ""
    return _make_unified_diff(
        old_text=old_content,
        new_text=new_content,
        path_label=file_path.as_posix(),
        context_lines=context_lines,
    )


@api_call(default_verbosity=Verbosity.ACK)
def replace_exact(path: str, old: str, new: str, expected_count: int = 1) -> str:
    """
    Replace an exact literal substring in a file.

    Args:
        path:
            The file I want to edit.
        old:
            The exact text I expect to find.
        new:
            The replacement text.
        expected_count:
            The exact number of matches I require before I proceed.

    Returns:
        A unified diff showing the change I made.

    Raises:
        FileEditError:
            If the search text is empty or the match count is not exactly what I
            expected.

    Note to self:
        This is my safest general-purpose edit. If I can identify a unique
        literal block, I should prefer this over regex.
    """
    check_for_interrupt()

    file_path = Path(path)
    original = read(path)

    match_count = _count_literal_occurrences(original, old)
    _validate_expected_count(match_count, expected_count, "exact replace")

    replacement = _normalize_newline_for_insert(original, new)
    updated = original.replace(old, replacement)

    _atomic_write_text(file_path, updated)

    return _make_unified_diff(
        old_text=original,
        new_text=updated,
        path_label=file_path.as_posix(),
    )


@api_call(default_verbosity=Verbosity.ACK)
def replace_regex(
    path: str,
    pattern: str,
    repl: str,
    expected_count: int = 1,
    flags: int = 0,
) -> str:
    """
    Replace text in a file using a regular expression.

    Args:
        path:
            The file I want to edit.
        pattern:
            The regex pattern I want to match.
        repl:
            The replacement text, interpreted by `re.sub`.
        expected_count:
            The exact number of regex matches I require before I proceed.
        flags:
            Optional regex compilation flags like `re.MULTILINE`.

    Returns:
        A unified diff showing the change I made.

    Raises:
        FileEditError:
            If the regex is invalid or the match count is not exactly what I
            expected.

    Note to self:
        Regex is useful, but it is also where I can get sloppy fast. I should
        keep patterns tight and always require an expected match count.
    """
    check_for_interrupt()

    file_path = Path(path)
    original = read(path)
    regex = _compile_regex(pattern, flags=flags)

    matches = list(regex.finditer(original))
    _validate_expected_count(len(matches), expected_count, "regex replace")

    normalized_repl = _normalize_newline_for_insert(original, repl)
    updated, _ = regex.subn(normalized_repl, original, count=expected_count)

    _atomic_write_text(file_path, updated)

    return _make_unified_diff(
        old_text=original,
        new_text=updated,
        path_label=file_path.as_posix(),
    )


@api_call(default_verbosity=Verbosity.ACK)
def insert_before(
    path: str,
    anchor: str,
    content: str,
    expected_count: int = 1,
) -> str:
    """
    Insert text immediately before an exact anchor string.

    Args:
        path:
            The file I want to edit.
        anchor:
            The exact text I expect to find.
        content:
            The text I want to insert before the anchor.
        expected_count:
            The exact number of anchor matches I require.

    Returns:
        A unified diff showing the change I made.

    Raises:
        FileEditError:
            If the anchor is empty or its match count is not exactly what I
            expected.

    Note to self:
        This is ideal when I know the code or text that should come next, but I
        do not want to rewrite the anchor itself.
    """
    check_for_interrupt()

    file_path = Path(path)
    original = read(path)

    match_count = _count_literal_occurrences(original, anchor)
    _validate_expected_count(match_count, expected_count, "insert_before anchor")

    normalized_content = _normalize_newline_for_insert(original, content)
    updated = original.replace(anchor, normalized_content + anchor, expected_count)

    _atomic_write_text(file_path, updated)

    return _make_unified_diff(
        old_text=original,
        new_text=updated,
        path_label=file_path.as_posix(),
    )


@api_call(default_verbosity=Verbosity.ACK)
def insert_after(
    path: str,
    anchor: str,
    content: str,
    expected_count: int = 1,
) -> str:
    """
    Insert text immediately after an exact anchor string.

    Args:
        path:
            The file I want to edit.
        anchor:
            The exact text I expect to find.
        content:
            The text I want to insert after the anchor.
        expected_count:
            The exact number of anchor matches I require.

    Returns:
        A unified diff showing the change I made.

    Raises:
        FileEditError:
            If the anchor is empty or its match count is not exactly what I
            expected.

    Note to self:
        This is useful when I want to add code or notes right after a known
        block without touching the anchor itself.
    """
    check_for_interrupt()

    file_path = Path(path)
    original = read(path)

    match_count = _count_literal_occurrences(original, anchor)
    _validate_expected_count(match_count, expected_count, "insert_after anchor")

    normalized_content = _normalize_newline_for_insert(original, content)
    updated = original.replace(anchor, anchor + normalized_content, expected_count)

    _atomic_write_text(file_path, updated)

    return _make_unified_diff(
        old_text=original,
        new_text=updated,
        path_label=file_path.as_posix(),
    )