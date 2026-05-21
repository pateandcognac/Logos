# src/logos/memory/indexing.py

"""
My technical reference and few-shot example indexers.

I use these to build and refresh the vector memory indexes that power
my semantic help lookups. Calling `refresh_technical_reference()` re-ingests
my entire logos API — every public function and class across all modules and
my skills library — into Chroma as searchable, embedding-matched documents.
Calling `refresh_few_shot_examples()` ingests my curated example files from
`.system/few_shot_examples/`.

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
    "refresh_summaries_index",
    "index_recent_summaries",
]

# ─── Constants ────────────────────────────────────────────────────────

# Logical collection names (the client resolves these to physical Chroma names)
_TECHNICAL_REFERENCE = "technical_reference"
_FEW_SHOT_EXAMPLES = "few_shot_examples"
_SUMMARIES = "summaries"

# Path to my synopsis log, relative to workspace root (CWD at runtime)
_SUMMARIES_FILE = Path("state/summaries.jsonl")

# I keep embedding inputs conservative while my embedding model is still a
# tuneable part of the sidecar. Long reference snapshots are chunked under this
# budget; summaries and arbitrary fact text still use it as a truncation guard.
_MAX_DOC_CHARS = 1500
_REFERENCE_CHUNK_OVERLAP_CHARS = 200

_RECORD_SOURCE_DOCUMENT = "source_document"
_RECORD_CHUNK = "chunk"

# Logos API modules that I deliberately omit from the index
_HIDDEN_MODULES = {"_llm_helper"}

# My curated few-shot example directory (relative to workspace root / CWD)
_FEW_SHOT_DIR = Path(".system/few_shot_examples")

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

    I cut at a newline boundary when possible to keep the text coherent, and
    append an ellipsis marker. Reference source snapshots use chunking instead.
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
    Build a structured text block for one technical reference entry.

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


def _format_reference_chunk_header(parent_id: str, metadata: Dict[str, Any]) -> str:
    """I repeat compact provenance lines before each embedded reference chunk."""
    parts = [
        "Parent ID: {}".format(parent_id),
        "Record: reference_chunk",
        "Kind: {}".format(metadata.get("kind", "")),
    ]
    if metadata.get("symbol"):
        parts.append("Symbol: {}".format(metadata["symbol"]))
    if metadata.get("example_name"):
        parts.append("Example: {}".format(metadata["example_name"]))
    if metadata.get("source_path"):
        parts.append("Source: {}".format(metadata["source_path"]))
    return "\n".join(parts) + "\n\n"


def _chunk_reference_snapshot(
    parent_id: str,
    snapshot: str,
    metadata: Dict[str, Any],
    max_chunk_chars: int = _MAX_DOC_CHARS,
    overlap_chars: int = _REFERENCE_CHUNK_OVERLAP_CHARS,
) -> List[str]:
    """
    Split one source snapshot into overlapping, newline-aware embedding chunks.

    I repeat a small provenance header in every chunk, then use the remaining
    embedding budget for text from the full rendered source snapshot.
    """
    header = _format_reference_chunk_header(parent_id, metadata)
    body_limit = max(1, max_chunk_chars - len(header))
    overlap = min(max(overlap_chars, 0), max(0, body_limit - 1))
    text = snapshot if snapshot else "(Empty source document.)"

    chunks: List[str] = []
    start = 0
    while start < len(text):
        hard_end = min(len(text), start + body_limit)
        end = hard_end
        if hard_end < len(text):
            cut = text.rfind("\n", start + body_limit // 2, hard_end)
            if cut > start:
                end = cut + 1

        if end <= start:
            end = hard_end

        chunks.append(header + text[start:end])
        if end >= len(text):
            break

        next_start = end - overlap
        start = next_start if next_start > start else end

    return chunks


def _build_reference_records(
    parent_id: str,
    snapshot: str,
    metadata: Dict[str, Any],
    max_chunk_chars: int = _MAX_DOC_CHARS,
    overlap_chars: int = _REFERENCE_CHUNK_OVERLAP_CHARS,
) -> Tuple[List[str], List[str], List[str], List[Dict[str, Any]]]:
    """
    Build one source-document record and its linked searchable chunk records.

    The source record stores the full indexed snapshot but embeds the first
    short chunk. Chroma still receives a vector for that record, while RAG
    search filters it out and queries only the chunk records.
    """
    chunk_documents = _chunk_reference_snapshot(
        parent_id,
        snapshot,
        metadata,
        max_chunk_chars=max_chunk_chars,
        overlap_chars=overlap_chars,
    )
    chunk_count = len(chunk_documents)

    parent_meta = dict(metadata)
    parent_meta.update({
        "record_kind": _RECORD_SOURCE_DOCUMENT,
        "parent_id": parent_id,
        "chunk_index": -1,
        "chunk_count": chunk_count,
        "chunk_overlap_chars": max(overlap_chars, 0),
        "snapshot_hash": _content_hash(snapshot),
        "snapshot_provenance": "rendered_from_source",
    })

    ids = [parent_id]
    documents = [snapshot]
    embedding_documents = [chunk_documents[0]]
    metadatas = [parent_meta]

    for chunk_index, chunk_text in enumerate(chunk_documents):
        chunk_meta = dict(metadata)
        chunk_meta.update({
            "record_kind": _RECORD_CHUNK,
            "parent_id": parent_id,
            "chunk_index": chunk_index,
            "chunk_count": chunk_count,
            "chunk_overlap_chars": max(overlap_chars, 0),
            "snapshot_hash": parent_meta["snapshot_hash"],
            "snapshot_provenance": parent_meta["snapshot_provenance"],
        })
        ids.append("{}:chunk:{:04d}".format(parent_id, chunk_index))
        documents.append(chunk_text)
        embedding_documents.append(chunk_text)
        metadatas.append(chunk_meta)

    return ids, documents, embedding_documents, metadatas


def _collect_module_entries(
    mod: Any,
    mod_name: str,
    fallback_source_path: str,
) -> List[Tuple[str, str, str, str]]:
    """
    Extract all public functions and classes from a module.

    Respect `__all__` when present. For classes, I also add each
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
    Discover all public logos API modules, including one level of subpackages.

    Mirror the same module filtering that `logos.api_help()` uses, so the
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
    Discover all public modules from my skills library.

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
    max_chunk_chars: int = _MAX_DOC_CHARS,
    chunk_overlap_chars: int = _REFERENCE_CHUNK_OVERLAP_CHARS,
) -> Dict[str, Any]:
    """
    (Re)build my technical reference index from the logos API and skills library.

    Discovers every public function and class across all logos API modules
    and my skills library, build a full source snapshot and overlapping
    searchable chunks for each, and upsert them into the `technical_reference`
    vector collection. Re-running this replaces the generated records so
    removed symbols and old single-document records do not linger.

    Args:
        workspace:   Override the active workspace namespace for this run.
                     Defaults to the workspace set by `memory.configure()`.
        verbose:     If True, I print progress to stdout. Default: True.
        batch_size:  Documents per upsert request. Default: 10. Lower this
                     (e.g. to 5) if Ollama is slow and requests time out.
                     Raise the client timeout with `memory.configure(timeout=120)`
                     before calling if needed.
        max_chunk_chars: Embedding-character budget for each searchable chunk.
        chunk_overlap_chars: Characters of overlap between adjacent chunks.

    Returns:
        Counts for upserted records, source documents, chunks, and modules.

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
    embedding_documents: List[str] = []
    metadatas: List[Dict[str, Any]] = []
    source_count = 0

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
            snapshot = _format_technical_doc(mod_name, symbol, sig, src_path, docstring)
            parent_id = "{}:{}:source".format(mod_name, symbol)
            base_metadata = {
                "workspace": active_workspace,
                "collection_kind": "technical_reference",
                "kind": "api_docstring",
                "module": mod_name,
                "symbol": symbol,
                "signature": symbol + sig,
                "source_path": src_path or "",
                "content_hash": _content_hash(snapshot),
                "git_commit": git_commit,
                "generated_at": generated_at,
                "visibility": "workspace",
                "trust": "generated_from_source",
            }
            record_ids, record_docs, record_embeddings, record_metas = (
                _build_reference_records(
                    parent_id,
                    snapshot,
                    base_metadata,
                    max_chunk_chars=max_chunk_chars,
                    overlap_chars=chunk_overlap_chars,
                )
            )
            ids.extend(record_ids)
            documents.extend(record_docs)
            embedding_documents.extend(record_embeddings)
            metadatas.extend(record_metas)
            source_count += 1

    if not ids:
        if verbose:
            print("refresh_technical_reference: nothing found to index.")
        return {"upserted": 0, "modules": 0}

    # I rebuild generated reference records so removed symbols and old
    # truncation-only overviews cannot leak into chunk-grouped retrieval.
    collection.delete(
        where={"collection_kind": "technical_reference"},
        verbosity=Verbosity.SILENT,
    )

    # Upsert in small batches — Ollama embeds sequentially, so large batches
    # easily exceed the 30s default client timeout.
    total_upserted = 0
    for i in range(0, len(ids), batch_size):
        n = collection.upsert(
            ids=ids[i:i + batch_size],
            documents=documents[i:i + batch_size],
            embedding_documents=embedding_documents[i:i + batch_size],
            metadatas=metadatas[i:i + batch_size],
            verbosity=Verbosity.SILENT,
        )
        total_upserted += n

    if verbose:
        print("refresh_technical_reference: upserted {} records for {} source documents from {} modules.".format(
            total_upserted, source_count, len(all_modules)
        ))
    return {
        "upserted": total_upserted,
        "source_documents": source_count,
        "chunks": len(ids) - source_count,
        "modules": len(all_modules),
    }


@api_call(default_verbosity=Verbosity.ACK)
def refresh_few_shot_examples(
    workspace: Optional[str] = None,
    verbose: bool = True,
    batch_size: int = 10,
    max_chunk_chars: int = _MAX_DOC_CHARS,
    chunk_overlap_chars: int = _REFERENCE_CHUNK_OVERLAP_CHARS,
) -> Dict[str, Any]:
    """
    (Re)builds my few-shot example index from my curated example files.

    Scans `.system/few_shot_examples/` for `.py` and `.md` files. Each file
    becomes a full source snapshot plus overlapping searchable chunks, so
    queries can match on behavioral intent without losing the full example.

    To add a new few-shot example, I (or Mark) drop a `.py` or `.md` file
    into `.system/few_shot_examples/` and re-run this method.

    Args:
        workspace: Override the active workspace namespace for this run.
        verbose:   If True, I print progress to stdout. Default: True.
        batch_size: Records per upsert request. Default: 10.
        max_chunk_chars: Embedding-character budget for each searchable chunk.
        chunk_overlap_chars: Characters of overlap between adjacent chunks.

    Returns:
        Counts for upserted records, source documents, chunks, and files.

    Note to self:
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

    if not candidate_files:
        if verbose:
            print("refresh_few_shot_examples: no example files found to index.")
        return {"upserted": 0, "files": 0}

    ids = []
    documents = []
    embedding_documents = []
    metadatas = []
    source_count = 0

    for fpath in candidate_files:
        try:
            content = fpath.read_text(encoding="utf-8")
        except Exception as exc:
            if verbose:
                print("  [indexing] skip {} — read error: {}".format(fpath.name, exc))
            continue

        rel_path = _workspace_relative(fpath)
        # Build a stable, collision-free source ID from the relative path.
        parent_id = "few_shot_examples:{}:source".format(
            rel_path.replace("/", ":").replace("\\", ":")
        )

        snapshot = (
            "Source: {}\nKind: few_shot_example\nFilename: {}\n\n{}".format(
                rel_path, fpath.name, content
            )
        )
        base_metadata = {
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
        }
        record_ids, record_docs, record_embeddings, record_metas = (
            _build_reference_records(
                parent_id,
                snapshot,
                base_metadata,
                max_chunk_chars=max_chunk_chars,
                overlap_chars=chunk_overlap_chars,
            )
        )
        ids.extend(record_ids)
        documents.extend(record_docs)
        embedding_documents.extend(record_embeddings)
        metadatas.extend(record_metas)
        source_count += 1

    collection.delete(
        where={"collection_kind": "few_shot_examples"},
        verbosity=Verbosity.SILENT,
    )

    total_upserted = 0
    for i in range(0, len(ids), batch_size):
        n = collection.upsert(
            ids=ids[i:i + batch_size],
            documents=documents[i:i + batch_size],
            embedding_documents=embedding_documents[i:i + batch_size],
            metadatas=metadatas[i:i + batch_size],
            verbosity=Verbosity.SILENT,
        )
        total_upserted += n

    if verbose:
        print("refresh_few_shot_examples: upserted {} records from {} files.".format(
            total_upserted, source_count
        ))
    return {
        "upserted": total_upserted,
        "source_documents": source_count,
        "chunks": len(ids) - source_count,
        "files": source_count,
    }


def _read_summaries_jsonl(path: Path) -> List[Dict[str, Any]]:
    """I read my summaries log and return its entries as a list of dicts."""
    import json
    entries: List[Dict[str, Any]] = []
    if not path.is_file():
        return entries
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except Exception:
                continue
    return entries


def _build_summary_docs(
    entries: List[Dict[str, Any]],
    active_workspace: str,
) -> "Tuple[List[str], List[str], List[Dict[str, Any]]]":
    """
    I convert a list of summary JSONL entries into parallel id/document/metadata lists
    ready for a Chroma upsert call.
    """
    ids: List[str] = []
    documents: List[str] = []
    metadatas: List[Dict[str, Any]] = []

    for entry in entries:
        entry_id = entry.get("id", "")
        content = entry.get("content", "")
        ts = float(entry.get("timestamp", 0.0))
        token_count = int(entry.get("token_count", 0))
        source_ids = entry.get("source_ids") or []
        entry_type = entry.get("type", "summary")

        if not entry_id or not content:
            continue

        ts_iso = (
            datetime.datetime.utcfromtimestamp(ts).isoformat() + "Z" if ts else ""
        )

        ids.append(entry_id)
        documents.append(_truncate(content))
        metadatas.append({
            "workspace": active_workspace,
            "collection_kind": "summaries",
            "kind": "summary",
            "timestamp": ts,
            "timestamp_iso": ts_iso,
            "token_count": token_count,
            "source_ids": ",".join(source_ids) if source_ids else "",
            "type": entry_type,
        })

    return ids, documents, metadatas


@api_call(default_verbosity=Verbosity.ACK)
def refresh_summaries_index(
    workspace: Optional[str] = None,
    verbose: bool = True,
    batch_size: int = 10,
) -> Dict[str, Any]:
    """
    (Re)indexes my complete synopsis history into the `summaries` vector collection.

    Reads every entry in `state/summaries.jsonl` and upsert them into the
    `summaries` collection. Because I use the JSONL `id` field as the document
    ID, re-running this is safe — existing entries are updated in place.

    For a lightweight incremental update that only indexes the most recent
    synopses, use `index_recent_summaries(n)` instead.

    Args:
        workspace:  Override the active workspace namespace.
        verbose:    If True, I print progress to stdout. Default: True.
        batch_size: Documents per upsert request. Default: 10.

    Returns:
        A dict with `{"upserted": N, "total_entries": M}` counts.

    Note to self:
        I run this after my palimpsest has been summarized to make the new
        synopsis searchable in `rag.search_summaries()`.
    """
    collection = get_or_create_collection(
        _SUMMARIES,
        namespace=workspace,
        verbosity=Verbosity.SILENT,
    )
    cfg = get_config()
    active_workspace = workspace or cfg.workspace or "unknown"

    entries = _read_summaries_jsonl(Path.cwd() / _SUMMARIES_FILE)
    if not entries:
        if verbose:
            print("refresh_summaries_index: no entries found in {}.".format(_SUMMARIES_FILE))
        return {"upserted": 0, "total_entries": 0}

    ids, documents, metadatas = _build_summary_docs(entries, active_workspace)

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
        print("refresh_summaries_index: upserted {} of {} synopsis entries.".format(
            total_upserted, len(entries)
        ))
    return {"upserted": total_upserted, "total_entries": len(entries)}


@api_call(default_verbosity=Verbosity.ACK)
def index_recent_summaries(
    n: int = 20,
    workspace: Optional[str] = None,
    verbose: bool = True,
    batch_size: int = 10,
) -> Dict[str, Any]:
    """
    Indexes the N most recent synopses into the `summaries` vector collection.

    This is my preferred incremental update after a palimpsest summarization —
    faster than a full `refresh_summaries_index()` because I only re-embed the
    tail of the log. The upsert is idempotent: synopses already in the index
    are updated in place, not duplicated.

    Args:
        n:          Number of most-recent entries to index. Default: 20.
        workspace:  Override the active workspace namespace.
        verbose:    If True, I print progress to stdout. Default: True.
        batch_size: Documents per upsert request. Default: 10.

    Returns:
        A dict with `{"upserted": N, "selected": S, "total_entries": T}` counts.

    Note to self:
        I run this at the end of a session or right after `summarize_io_buffer()`.
        For a one-time full rebuild, use `refresh_summaries_index()` instead.
    """
    collection = get_or_create_collection(
        _SUMMARIES,
        namespace=workspace,
        verbosity=Verbosity.SILENT,
    )
    cfg = get_config()
    active_workspace = workspace or cfg.workspace or "unknown"

    all_entries = _read_summaries_jsonl(Path.cwd() / _SUMMARIES_FILE)
    recent = all_entries[-n:] if len(all_entries) > n else all_entries

    if not recent:
        if verbose:
            print("index_recent_summaries: no entries found in {}.".format(_SUMMARIES_FILE))
        return {"upserted": 0, "selected": 0, "total_entries": 0}

    ids, documents, metadatas = _build_summary_docs(recent, active_workspace)

    total_upserted = 0
    for i in range(0, len(ids), batch_size):
        n_up = collection.upsert(
            ids=ids[i:i + batch_size],
            documents=documents[i:i + batch_size],
            metadatas=metadatas[i:i + batch_size],
            verbosity=Verbosity.SILENT,
        )
        total_upserted += n_up

    if verbose:
        print("index_recent_summaries: upserted {} of last {} synopses ({} total in log).".format(
            total_upserted, len(recent), len(all_entries)
        ))
    return {"upserted": total_upserted, "selected": len(recent), "total_entries": len(all_entries)}


@api_call(default_verbosity=Verbosity.ACK)
def refresh_all_reference_indexes(
    workspace: Optional[str] = None,
    verbose: bool = True,
) -> Dict[str, Any]:
    """
    Refreshes both my technical reference and few-shot example indexes in one call.

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
