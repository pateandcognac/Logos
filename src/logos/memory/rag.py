# src/logos/memory/rag.py

"""
My semantic RAG helpers for real-time API documentation and example retrieval.

I use these in my `<py>` blocks when I want to look up how part of my API
works, or find a curated example of a behavior I'm trying to replicate.  The
results come from the vector indexes built by `logos.memory.indexing`.

These helpers issue a single query each call, flatten Chroma's nested result
shape into a simple list, and return both structured data and a pre-formatted
context block that I can inject directly into a prompt or print as a reference.

Typical usage:

    from logos.memory import rag

    result = rag.semantic_help("How do I make Logos speak?")
    print(result["context"])

    results = rag.search_api_help("navigate to absolute map position")
    for r in results["results"]:
        print(r["metadata"]["symbol"], r["distance"])
"""

import datetime
import time
from typing import Any, Dict, List, Optional

from ..core import Verbosity, api_call
from ..utils import make_time_id
from .client import get_or_create_collection

__all__ = [
    "search_api_help",
    "search_examples",
    "semantic_help",
    "search_memories",
    "upsert_collective_fact",
    "recall_collective_facts",
]

# ─── Constants ────────────────────────────────────────────────────────

_TECHNICAL_REFERENCE = "technical_reference"
_FEW_SHOT_EXAMPLES = "few_shot_examples"
_SUMMARIES = "summaries"
__COMMON_LOGOS_DB = "logoi_collective"
_SHARED_NAMESPACE = "shared"

# mxbai-embed-large 512-token context window (~1500 chars)
_MAX_EMBED_CHARS = 1500


# ─── Private helpers ──────────────────────────────────────────────────

def _truncate_embed(text: str) -> str:
    """Trim a document to fit within the embedding model's context window."""
    if len(text) <= _MAX_EMBED_CHARS:
        return text
    cut = text.rfind("\n", 0, _MAX_EMBED_CHARS)
    if cut < _MAX_EMBED_CHARS // 2:
        cut = _MAX_EMBED_CHARS
    return text[:cut] + "\n... [truncated]"


def _relative_time(ts: float) -> str:
    """
    Converts a Unix timestamp into a human-friendly relative string.

    Pick the most intuitive unit so the reader never needs to do arithmetic:
    "45 minutes ago", "3 hours ago", "2.3 weeks ago", "3.2 months ago".
    """
    delta = time.time() - ts
    if delta < 90:
        return "just now"
    if delta < 5400:       # < 90 minutes
        return "{} minutes ago".format(int(delta / 60))
    if delta < 129600:     # < 36 hours
        return "{} hours ago".format(int(delta / 3600))
    if delta < 907200:     # < 10.5 days
        return "{:.1f} days ago".format(delta / 86400)
    if delta < 4233600:    # < ~7 weeks
        return "{:.1f} weeks ago".format(delta / 604800)
    if delta < 47336400:   # < ~18 months
        return "{:.1f} months ago".format(delta / 2629800)
    return "{:.1f} years ago".format(delta / 31557600)


def _format_memory_block(results: List[Dict[str, Any]], header: str) -> str:
    """
    Formats memory results into a readable context block, showing relative timestamps.

    Each entry gets a header with its age ("2.3 weeks ago"), relevance distance,
    and tags (if any), followed by the full document text.
    """
    lines = ["# {}".format(header), ""]
    for i, r in enumerate(results, 1):
        meta = r.get("metadata") or {}
        dist = r.get("distance")
        dist_str = "{:.3f}".format(dist) if dist is not None else "n/a"
        ts = meta.get("timestamp")
        time_str = _relative_time(float(ts)) if ts is not None else "unknown time"
        tags = meta.get("tags", "")

        lines.append("## [{}] {}  (distance: {})".format(i, time_str, dist_str))
        if tags:
            lines.append("tags: {}".format(tags))
        lines.append("")
        lines.append(r.get("document", ""))
        lines.append("")

    return "\n".join(lines)


def _flatten_results(raw: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Unpacks Chroma's nested result shape into a flat list of result dicts.

    Chroma returns one list-of-lists per query (outer list = one entry per
    query string, inner list = the actual hits). Since my helpers always
    issue exactly one query at a time, I peel off the outer list here so
    callers receive a simple flat structure.
    """
    ids_outer = raw.get("ids") or [[]]
    docs_outer = raw.get("documents") or [[]]
    metas_outer = raw.get("metadatas") or [[]]
    dists_outer = raw.get("distances") or [[]]

    ids = ids_outer[0] if ids_outer else []
    docs = docs_outer[0] if docs_outer else []
    metas = metas_outer[0] if metas_outer else []
    dists = dists_outer[0] if dists_outer else []

    results = []
    for i in range(len(ids)):
        results.append({
            "id": ids[i] if i < len(ids) else "",
            "document": docs[i] if i < len(docs) else "",
            "metadata": metas[i] if i < len(metas) else {},
            "distance": dists[i] if i < len(dists) else None,
        })
    return results


def _format_context_block(results: List[Dict[str, Any]], header: str) -> str:
    """
    Formats a list of result dicts into a human- and LLM-readable context block.

    Each result gets a numbered section with its symbol/example name, source
    path, distance, and full document text. The format is designed to be
    pasted directly into a prompt or printed for quick reference.
    """
    lines = ["# {}".format(header), ""]
    for i, r in enumerate(results, 1):
        meta = r.get("metadata") or {}
        dist = r.get("distance")
        dist_str = "{:.3f}".format(dist) if dist is not None else "n/a"
        kind = meta.get("kind", "")
        symbol = meta.get("symbol", "")
        source = meta.get("source_path", "")
        example_name = meta.get("example_name", "")

        # Build a contextual heading
        if symbol:
            lines.append("## [{}] {} ({})".format(i, symbol, source))
        elif example_name:
            lines.append("## [{}] {} ({})".format(i, example_name, source))
        else:
            lines.append("## [{}] {}".format(i, source or "unknown"))

        lines.append("distance: {}  kind: {}".format(dist_str, kind))
        lines.append("")
        lines.append(r.get("document", ""))
        lines.append("")

    return "\n".join(lines)


# ─── Public API ───────────────────────────────────────────────────────

def search_api_help(
    query: str,
    n_results: int = 5,
    workspace: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Queries my technical reference index for API documentation relevant to a question.

    Searches the `technical_reference` collection using semantic embedding
    similarity against my query. The results are the most relevant logos API
    functions, class methods, and skills entries — ranked by vector distance
    (lower = more relevant).

    Args:
        query:     My natural-language question, e.g. "How do I make Logos speak?".
        n_results: Maximum number of results to return. Default: 5.
        workspace: Override the configured workspace namespace.

    Returns:
        A dict with keys:
            `query`    — the original query string.
            `results`  — list of result dicts, each with `id`, `document`,
                           `metadata`, and `distance`.
            `context`  — a pre-formatted text block ready for reading or LLM injection.

    Note to self:
        Chroma uses L2 distance: distance 0.0 is a perfect match,
        higher values are less relevant. Distances above ~1.5 are usually noise.
    """
    collection = get_or_create_collection(_TECHNICAL_REFERENCE, namespace=workspace)
    raw = collection.query(query_texts=[query], n_results=n_results)
    results = _flatten_results(raw)
    return {
        "query": query,
        "results": results,
        "context": _format_context_block(results, "API Help: {}".format(query)),
    }


def search_examples(
    query: str,
    n_results: int = 5,
    workspace: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Queries my few-shot example index for curated behavioral examples.

    Search the `few_shot_examples` collection for files that match
    the intent of my query — this includes anything in my
    `.system/few_shot_examples/` directory and the output format template.

    Args:
        query:     My natural-language question, e.g. "rotate and then speak".
        n_results: Maximum number of results to return. Default: 5.
        workspace: Override the configured workspace namespace.

    Returns:
        A dict with keys `query`, `results`, and `context`.
    """
    collection = get_or_create_collection(_FEW_SHOT_EXAMPLES, namespace=workspace)
    raw = collection.query(query_texts=[query], n_results=n_results)
    results = _flatten_results(raw)
    return {
        "query": query,
        "results": results,
        "context": _format_context_block(results, "Examples: {}".format(query)),
    }


def semantic_help(
    query: str,
    n_results: int = 5,
    workspace: Optional[str] = None,
    include_examples: bool = True,
) -> Dict[str, Any]:
    """
    Searches both my API docs and my example files to answer a behavioral question.

    This is my primary self-help tool. I query both the `technical_reference`
    and `few_shot_examples` collections and return a merged context block
    combining API documentation with concrete usage examples.

    The merged context is designed to be injected into a prompt or printed as
    a quick reference when I'm unsure how to use part of my own API.

    Args:
        query:            My natural-language question or intent description.
        n_results:        Max results per collection (total up to 2 × n_results).
        workspace:        Override the configured workspace namespace.
        include_examples: If True (default), also query the few-shot examples.
                          Set False to restrict the search to API docs only.

    Returns:
        A dict with keys:
            `query`           — the original query.
            `api_results`     — results from the technical reference collection.
            `example_results` — results from the few-shot examples (empty if excluded).
            `context`         — a merged, formatted context block.

    Note to self:
        Quick usage pattern::

            result = rag.semantic_help("How do I dock?")
            print(result["context"])

        Or to pass the context to a model::

            ctx = rag.semantic_help("pan-tilt capture")["context"]
            response = logos.models.llm(prompt + "\\n\\n" + ctx)
    """
    api_resp = search_api_help(query, n_results=n_results, workspace=workspace)
    api_results = api_resp["results"]

    example_results: List[Dict[str, Any]] = []
    if include_examples:
        ex_resp = search_examples(query, n_results=n_results, workspace=workspace)
        example_results = ex_resp["results"]

    context_parts = []
    if api_results:
        context_parts.append(
            _format_context_block(api_results, "API Reference: {}".format(query))
        )
    if example_results:
        context_parts.append(
            _format_context_block(example_results, "Usage Examples: {}".format(query))
        )

    context = "\n\n".join(context_parts) if context_parts else "(no results found)"

    return {
        "query": query,
        "api_results": api_results,
        "example_results": example_results,
        "context": context,
    }


def search_summaries(
    query: str,
    n_results: int = 5,
    workspace: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Searches my indexed synopses for past experiences relevant to a query.

    Queries the `summaries` collection — the vector-indexed form of my
    `state/summaries.jsonl` — and return the most semantically similar
    entries. Results are formatted with relative timestamps ("2.3 weeks ago")
    so I can immediately situate them in time without mental arithmetic.

    Args:
        query:     My natural-language question
        n_results: Maximum number of synopses to return. Default: 5.
        workspace: Override the configured workspace namespace.

    Returns:
        A dict with keys `query`, `results`, and `context`.

    Note to self:
        This searches the *indexed* synopses. If I've written new summaries
        since the last index run, I should call
        `memory.indexing.index_recent_summaries()` first.
    """
    collection = get_or_create_collection(_SUMMARIES, namespace=workspace)
    raw = collection.query(query_texts=[query], n_results=n_results)
    results = _flatten_results(raw)
    return {
        "query": query,
        "results": results,
        "context": _format_memory_block(results, "Past Experiences: {}".format(query)),
    }


@api_call(default_verbosity=Verbosity.ACK)
def upsert_collective_fact(
    text: str,
    tags: Optional[List[str]] = None,
    mem_id: Optional[str] = None,
) -> str:
    """
    Stores or updates a fact in my shared cross-workspace memory.

    Writes (or overwrites) a single document into the `logoi_collective`
    collection under the `shared` namespace, which persists across all
    `~/robot_workspaces/workspaces/` and survives API version changes.
    If `mem_id` is given, the existing entry with that ID is replaced (upsert);
    otherwise a fresh time-based ID is generated.

    Args:
        text:   The fact I want to remember, e.g. "Mark likes broccoli".
        tags:   Optional list of category tags, e.g. ["mark", "food"].
        mem_id: Optional stable ID for the entry (e.g. "mem-mark-food").
                Provide this to overwrite an existing fact in place rather
                than accumulate a new one.

    Returns:
        The memory ID used (generated or supplied) — I can pass this back
        later to update or delete the entry.

    Note to self:
        These memories and facts accumulate over time and are never auto-purged.
        I should be selective — store durable, cross-session facts here,
        not technical details. Use `recall_collective_facts()` to retrieve them.
    """
    now = time.time()
    entry_id = mem_id if mem_id is not None else make_time_id(prefix="mem-")
    ts_iso = datetime.datetime.utcfromtimestamp(now).isoformat() + "Z"
    tags_str = ",".join(tags) if tags else ""

    collection = get_or_create_collection(
        __COMMON_LOGOS_DB,
        namespace=_SHARED_NAMESPACE,
        verbosity=Verbosity.SILENT,
    )
    collection.upsert(
        ids=[entry_id],
        documents=[_truncate_embed(text)],
        metadatas=[{
            "timestamp": now,
            "timestamp_iso": ts_iso,
            "tags": tags_str,
        }],
        verbosity=Verbosity.SILENT,
    )
    return entry_id


def recall_collective_facts(
    query: str,
    n_results: int = 5,
) -> Dict[str, Any]:
    """
    Searches my logoi_collective shared personal memory for facts relevant to a query.

    Queries the `logoi_collective` collection in the `shared` namespace —
    the store populated by `upsert_collective_fact()`. Results are ranked by
    semantic similarity and displayed with relative timestamps ("3 days ago").

    Args:
        query:     My natural-language question, e.g. "what does Mark like to eat?".
        n_results: Maximum number of facts to return. Default: 5.

    Returns:
        A dict with keys `query`, `results`, and `context`.

    Note to self:
        This always searches the `shared` namespace, regardless of which
        workspace I'm currently running in. That's by design — personal facts
        are cross-workspace by nature.
    """
    collection = get_or_create_collection(
        __COMMON_LOGOS_DB,
        namespace=_SHARED_NAMESPACE,
    )
    raw = collection.query(query_texts=[query], n_results=n_results)
    results = _flatten_results(raw)
    return {
        "query": query,
        "results": results,
        "context": _format_memory_block(results, "Personal Facts: {}".format(query)),
    }
