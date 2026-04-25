# src/logos/memory/indexing.py

"""
My technical reference and few-shot example indexers.

I use these to build and refresh the vector memory indexes that power
my semantic help lookups. Calling `refresh_technical_reference()` re-ingests
my entire logos API — every public function and class across all modules and
my skills library — into Chroma as searchable, embedding-matched documents.
Calling `refresh_few_shot_examples()` ingests my curated example files from
`.system/few_shot_examples/` and the `.system/output_format.txt` template.

I treat the vector database as a *generated index*, not a source of truth.
The source code and example files are authoritative. I use deterministic IDs
and upsert semantics, so re-running a refresh safely updates rather than
duplicates any existing entries.

Typical usage:

    from logos.memory import indexing

    indexing.refresh_all_reference_indexes()     # full rebuild
    indexing.refresh_technical_reference()       # logos API + skills only
    indexing.refresh_few_shot_examples()         # curated example files only
"""

import datetime
import hashlib
import importlib
import inspect
import pkgutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..core import Verbosity, api_call
from .config import get_config
from .client import get_or_create_collection

__all__ = [
    "refresh_technical_reference",
    "refresh_few_shot_examples",
    "refresh_all_reference_indexes",
]

# ─── Constants ────────────────────────────────────────────────────────

# Logical collection names (the client resolves these to physical Chroma names)
_TECHNICAL_REFERENCE = "technical_reference"
_FEW_SHOT_EXAMPLES = "few_shot_examples"

# mxbai-embed-large has a 512-token context window (~1500 chars).
# I truncate documents to this limit before sending them to Ollama.
_MAX_DOC_CHARS = 1500

# Logos API modules that I deliberately omit from the index
_HIDDEN_MODULES = {"_llm_helper"}

# My curated few-shot example directory (relative to workspace root / CWD)
_FEW_SHOT_DIR = Path(".system/few_shot_examples")

# Fixed extra files I always include as few-shot examples
_FEW_SHOT_EXTRA_FILES = [
    Path(".system/output_format.txt"),
]


# ─── Private helpers ──────────────────────────────────────────────────

def _get_git_commit() -> str:
    """I try to get the current short git commit hash for provenance metadata."""
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            stderr=subprocess.DEVNULL,
        ).decode().strip()
    except Exception:
        return "unknown"


def _content_hash(text: str) -> str:
    """I compute a short MD5 hash of document text for cheap change detection."""
    return hashlib.md5(text.encode("utf-8")).hexdigest()[:12]


def _truncate(text: str, max_chars: int = _MAX_DOC_CHARS) -> str:
    """
    I truncate a document to fit within the embedding model's context window.

    mxbai-embed-large supports ~512 tokens. I cut at a newline boundary when
    possible to keep the text coherent, and append an ellipsis marker.
    """
    if len(text) <= max_chars:
        return text
    # Try to break on a newline near the limit
    cut = text.rfind("\n", 0, max_chars)
    if cut < max_chars // 2:
        cut = max_chars
    return text[:cut] + "\n... [truncated]"


def _workspace_relative(abs_path: Any) -> str:
    """I make an absolute path relative to my workspace root (CWD at runtime)."""
    try:
        return str(Path(abs_path).relative_to(Path.cwd()))
    except (ValueError, TypeError):
        return str(abs_path)


def _safe_signature(obj: Any) -> str:
    """I safely extract the signature of a callable as a string."""
    try:
        return str(inspect.signature(obj))
    except (ValueError, TypeError):
        return "(...)"


def _safe_source_path(obj: Any) -> str:
    """I get the source file of an object as a workspace-relative path."""
    try:
        return _workspace_relative(inspect.getfile(obj))
    except (TypeError, OSError):
        return ""


def _format_technical_doc(
    module_name: str,
    symbol: str,
    signature: str,
    source_path: str,
    docstring: str,
    kind: str = "api_docstring",
) -> str:
    """
    I build a structured text block for one technical reference entry.

    I combine the symbol name, signature, source location, and docstring
    into a format that embeds well semantically — the header lines give the
    retrieval model context about *where* the function lives, and the
    docstring gives it the *what* and *why*.
    """
    parts = [
        "Symbol: {}.{}".format(module_name, symbol),
        "Signature: {}{}".format(symbol, signature),
        "Module: {}".format(module_name),
        "Source: {}".format(source_path),
        "Kind: {}".format(kind),
        "",
        docstring if docstring else "(No docstring.)",
    ]
    return "\n".join(parts)


def _collect_module_entries(
    mod: Any,
    mod_name: str,
    fallback_source_path: str,
) -> List[Tuple[str, str, str, str]]:
    """
    I extract all public functions and classes from a module.

    I respect `__all__` when present. For classes, I also add each
    public method as a separate entry so method-level queries resolve.

    Returns:
        A list of `(symbol, signature, source_path, docstring)` tuples.
    """
    public_names = getattr(mod, "__all__", None)
    entries = []

    for name, obj in inspect.getmembers(mod):
        # Honour __all__ when present; otherwise skip private names
        if public_names is not None:
            if name not in public_names:
                continue
        else:
            if name.startswith("_"):
                continue
            # Skip names that were imported from another module
            obj_module = inspect.getmodule(obj)
            if obj_module is not None and obj_module.__name__ != mod.__name__:
                continue

        if inspect.isroutine(obj):
            sig = _safe_signature(obj)
            doc = inspect.getdoc(obj) or ""
            src = _safe_source_path(obj) or fallback_source_path
            entries.append((name, sig, src, doc))

        elif inspect.isclass(obj):
            # Index the class itself
            sig = _safe_signature(obj)
            doc = inspect.getdoc(obj) or ""
            src = _safe_source_path(obj) or fallback_source_path
            entries.append((name, sig, src, doc))

            # Index each public method separately for fine-grained retrieval
            for mname, mobj in inspect.getmembers(obj, inspect.isroutine):
                if mname.startswith("_"):
                    continue
                msig = _safe_signature(mobj)
                mdoc = inspect.getdoc(mobj) or ""
                entries.append(("{}.{}".format(name, mname), msig, src, mdoc))

    return entries


def _discover_logos_modules() -> List[Tuple[str, Any]]:
    """
    I discover all public logos API modules, including one level of subpackages.

    I mirror the same module filtering that `logos.api_help()` uses, so the
    index stays in sync with what is actually documented.

    Returns:
        A list of `(full_module_name, module_object)` pairs.
    """
    # Local import to avoid a circular import at module load time
    import logos

    result = []

    for _importer, modname, ispkg in pkgutil.iter_modules(logos.__path__):
        if modname.startswith("_") or modname in _HIDDEN_MODULES:
            continue
        full_name = "logos.{}".format(modname)
        try:
            mod = importlib.import_module(full_name)
        except Exception:
            continue
        result.append((full_name, mod))

        # For subpackages (like logos.memory), also walk one level of submodules
        if ispkg:
            pkg_path = getattr(mod, "__path__", [])
            for _, sub_modname, _ in pkgutil.iter_modules(pkg_path):
                if sub_modname.startswith("_"):
                    continue
                sub_full = "{}.{}".format(full_name, sub_modname)
                try:
                    sub_mod = importlib.import_module(sub_full)
                    result.append((sub_full, sub_mod))
                except Exception:
                    continue

    return result


def _discover_skills_modules() -> List[Tuple[str, Any]]:
    """
    I discover all public modules from my skills library.

    Returns:
        A list of `(full_module_name, module_object)` pairs.
    """
    try:
        import skills as skills_pkg
    except ImportError:
        return []

    result = []
    skills_path = getattr(skills_pkg, "__path__", [])

    for _importer, modname, _ in pkgutil.iter_modules(skills_path):
        if modname.startswith("_"):
            continue
        full_name = "skills.{}".format(modname)
        try:
            mod = importlib.import_module(full_name)
            result.append((full_name, mod))
        except Exception:
            continue

    return result


# ─── Public API ───────────────────────────────────────────────────────

@api_call(default_verbosity=Verbosity.ACK)
def refresh_technical_reference(
    workspace: Optional[str] = None,
    verbose: bool = True,
    batch_size: int = 10,
) -> Dict[str, Any]:
    """
    (Re))build my technical reference index from the logos API and skills library.

    Discovers every public function and class across all logos API modules
    and my skills library, build a structured document for each, and upsert
    them into the `technical_reference` vector collection. Re-running this
    is safe: entries that have not changed are updated in place; nothing
    is duplicated.

    Args:
        workspace:   Override the active workspace namespace for this run.
                     Defaults to the workspace set by `memory.configure()`.
        verbose:     If True, I print progress to stdout. Default: True.
        batch_size:  Documents per upsert request. Default: 10. Lower this
                     (e.g. to 5) if Ollama is slow and requests time out.
                     Raise the client timeout with `memory.configure(timeout=120)`
                     before calling if needed.

    Returns:
        A dict with `{"upserted": N, "modules": M}` counts.

    Note to self:
        I should run this whenever I add or update logos API code or skills.
        The vector index is a generated artifact — my source files are the
        authoritative source of truth.
    """
    collection = get_or_create_collection(
        _TECHNICAL_REFERENCE,
        namespace=workspace,
        verbosity=Verbosity.SILENT,
    )

    cfg = get_config()
    active_workspace = workspace or cfg.workspace or "unknown"
    git_commit = _get_git_commit()
    generated_at = datetime.datetime.utcnow().isoformat() + "Z"

    ids: List[str] = []
    documents: List[str] = []
    metadatas: List[Dict[str, Any]] = []

    all_modules = _discover_logos_modules() + _discover_skills_modules()

    for mod_name, mod in all_modules:
        mod_source_path = _safe_source_path(mod)

        try:
            entries = _collect_module_entries(mod, mod_name, mod_source_path)
        except Exception as exc:
            if verbose:
                print("  [indexing] skip {} — inspect failed: {}".format(mod_name, exc))
            continue

        for symbol, sig, src_path, docstring in entries:
            doc_text = _truncate(
                _format_technical_doc(mod_name, symbol, sig, src_path, docstring)
            )
            doc_id = "{}:{}:overview".format(mod_name, symbol)

            ids.append(doc_id)
            documents.append(doc_text)
            metadatas.append({
                "workspace": active_workspace,
                "collection_kind": "technical_reference",
                "kind": "api_docstring",
                "module": mod_name,
                "symbol": symbol,
                "signature": symbol + sig,
                "source_path": src_path or "",
                "chunk_kind": "overview",
                "content_hash": _content_hash(doc_text),
                "git_commit": git_commit,
                "generated_at": generated_at,
                "visibility": "workspace",
                "trust": "generated_from_source",
            })

    if not ids:
        if verbose:
            print("refresh_technical_reference: nothing found to index.")
        return {"upserted": 0, "modules": 0}

    # Upsert in small batches — Ollama embeds sequentially, so large batches
    # easily exceed the 30s default client timeout.
    total_upserted = 0
    for i in range(0, len(ids), batch_size):
        n = collection.upsert(
            ids=ids[i:i + batch_size],
            documents=documents[i:i + batch_size],
            metadatas=metadatas[i:i + batch_size],
            verbosity=Verbosity.SILENT,
        )
        total_upserted += n

    if verbose:
        print("refresh_technical_reference: upserted {} documents from {} modules.".format(
            total_upserted, len(all_modules)
        ))
    return {"upserted": total_upserted, "modules": len(all_modules)}


@api_call(default_verbosity=Verbosity.ACK)
def refresh_few_shot_examples(
    workspace: Optional[str] = None,
    verbose: bool = True,
) -> Dict[str, Any]:
    """
    I (re)build my few-shot example index from my curated example files.

    I scan `.system/few_shot_examples/` for `.py` and `.md` files
    and also index the fixed `.system/output_format.txt` template. Each file
    becomes one document in the `few_shot_examples` collection; the entire
    file content is embedded so queries can match on behavioral intent and
    patterns, not just filenames.

    To add a new few-shot example, I (or Mark) drop a `.py` or `.md` file
    into `.system/few_shot_examples/` and re-run this method.

    Args:
        workspace: Override the active workspace namespace for this run.
        verbose:   If True, I print progress to stdout. Default: True.

    Returns:
        A dict with `{"upserted": N, "files": F}` counts.

    Note to self:
        `output_format.txt` is indexed read-only — I never write to it.
        New curated examples go into `.system/few_shot_examples/`.
    """
    collection = get_or_create_collection(
        _FEW_SHOT_EXAMPLES,
        namespace=workspace,
        verbosity=Verbosity.SILENT,
    )

    cfg = get_config()
    active_workspace = workspace or cfg.workspace or "unknown"
    git_commit = _get_git_commit()
    generated_at = datetime.datetime.utcnow().isoformat() + "Z"

    workspace_root = Path.cwd()
    candidate_files: List[Path] = []

    # Scan my curated few-shot directory
    few_shot_dir = workspace_root / _FEW_SHOT_DIR
    if few_shot_dir.is_dir():
        for ext in ("*.py", "*.md"):
            candidate_files.extend(sorted(few_shot_dir.glob(ext)))
    else:
        if verbose:
            print("  [indexing] creating few-shot dir: {}".format(few_shot_dir))
        few_shot_dir.mkdir(parents=True, exist_ok=True)

    # Add the fixed extra files (e.g. output_format.txt)
    for extra in (_FEW_SHOT_EXTRA_FILES or []):
        resolved = workspace_root / extra
        if resolved.is_file():
            candidate_files.append(resolved)
        elif verbose:
            print("  [indexing] extra file not found, skipping: {}".format(resolved))

    if not candidate_files:
        if verbose:
            print("refresh_few_shot_examples: no example files found to index.")
        return {"upserted": 0, "files": 0}

    ids = []
    documents = []
    metadatas = []

    for fpath in candidate_files:
        try:
            content = fpath.read_text(encoding="utf-8")
        except Exception as exc:
            if verbose:
                print("  [indexing] skip {} — read error: {}".format(fpath.name, exc))
            continue

        rel_path = _workspace_relative(fpath)
        # Build a stable, collision-free ID from the relative path
        doc_id = "few_shot_examples:{}".format(rel_path.replace("/", ":").replace("\\", ":"))

        # Prepend a brief header so the embedding carries provenance context.
        # Truncate to fit within the embedding model's context window.
        doc_text = _truncate(
            "Source: {}\nKind: few_shot_example\nFilename: {}\n\n{}".format(
                rel_path, fpath.name, content
            )
        )

        ids.append(doc_id)
        documents.append(doc_text)
        metadatas.append({
            "workspace": active_workspace,
            "collection_kind": "few_shot_examples",
            "kind": "few_shot_example",
            "source_path": rel_path,
            "example_name": fpath.stem,
            "content_hash": _content_hash(content),
            "git_commit": git_commit,
            "generated_at": generated_at,
            "visibility": "workspace",
            "trust": "curated_example",
        })

    n = collection.upsert(
        ids=ids,
        documents=documents,
        metadatas=metadatas,
        verbosity=Verbosity.SILENT,
    )

    if verbose:
        print("refresh_few_shot_examples: upserted {} documents from {} files.".format(
            n, len(ids)
        ))
    return {"upserted": n, "files": len(ids)}


@api_call(default_verbosity=Verbosity.ACK)
def refresh_all_reference_indexes(
    workspace: Optional[str] = None,
    verbose: bool = True,
) -> Dict[str, Any]:
    """
    I refresh both my technical reference and few-shot example indexes in one call.

    This is my go-to entry point after significant API or skill changes.
    I run `refresh_technical_reference()` followed by
    `refresh_few_shot_examples()` and return a combined result dict.

    Args:
        workspace: Override the active workspace namespace for this run.
        verbose:   If True, I print progress to stdout. Default: True.

    Returns:
        A dict with `{"technical_reference": {...}, "few_shot_examples": {...}}`.
    """
    if verbose:
        print("=== Refreshing all reference indexes ===")
    tech = refresh_technical_reference(
        workspace=workspace,
        verbose=verbose,
        verbosity=Verbosity.SILENT,
    )
    few = refresh_few_shot_examples(
        workspace=workspace,
        verbose=verbose,
        verbosity=Verbosity.SILENT,
    )
    if verbose:
        print("=== Done. ===")
    return {"technical_reference": tech, "few_shot_examples": few}
