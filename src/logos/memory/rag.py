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

from typing import Any, Dict, List, Optional

from .client import get_or_create_collection

__all__ = [
    "search_api_help",
    "search_examples",
    "semantic_help",
]

# ─── Constants ────────────────────────────────────────────────────────

_TECHNICAL_REFERENCE = "technical_reference"
_FEW_SHOT_EXAMPLES = "few_shot_examples"


# ─── Private helpers ──────────────────────────────────────────────────

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
    I format a list of result dicts into a human- and LLM-readable context block.

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

    I search the `few_shot_examples` collection for files that match
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
    I search both my API docs and my example files to answer a behavioral question.

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
