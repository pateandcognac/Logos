# src/logos/memory/__init__.py

"""
My long-term memory subsystem — working buffer, vector store, and personal facts.

I have three layers:

**1. Buffer memory** — working memory tools for the palimpsest (`io_buffer.jsonl`).
   I use these to summarize past events and recall specific messages from my I/O history.

**2. Vector memory** — semantic storage backed by Chroma + Ollama embeddings served by
   my local Python 3.11 sidecar. I use these to store and retrieve knowledge across
   sessions without relying on my context window size.

**3. Reference indexes, RAG, and personal facts** — generated indexes over my logos API,
   curated example files, and my synopsis history; plus a shared cross-workspace store
   for durable personal knowledge. I use these to look up my own API, search past
   experiences, and remember facts that survive workspace and API changes.

Because my main runtime is Python 3.8, the vector client is a thin HTTP compatibility
layer that forwards requests to the Logos Chroma sidecar (`~/src/logos_chroma_server`),
which owns the Chroma SDK and Ollama embedding calls.

Typical usage:

    # --- Setup ---
    memory.configure(workspace="Logos", server_url="http://127.0.0.1:8123")

    # --- Semantic self-help ---
    result = memory.rag.semantic_help("How do I navigate to an absolute map position?")
    print(result["context"])

    # --- Search past synopses ---
    past = memory.search_summaries("chair alignment in Chora")
    print(past["context"])   # shows "2.3 weeks ago" style timestamps

    # --- Personal facts (shared across workspaces) ---
    memory.upsert_collective_fact(
        "Mark doesn't like broccoli",
        tags=["mark", "food"],
        mem_id="mark-food-broccoli",
    )
    facts = memory.recall_collective_facts("what does Mark like to eat?")
    print(facts["context"])

    # --- Rebuild indexes ---
    memory.indexing.refresh_all_reference_indexes()    # API docs + few-shot examples
    memory.indexing.refresh_summaries_index()           # full synopsis history
    memory.indexing.index_recent_summaries(n=20)        # incremental: last 20 only

Pass `namespace="shared"` to `get_or_create_collection` for direct cross-workspace access.
"""

# -- Buffer memory (palimpsest tools) --
from ._buffer import (
    summarize_io_buffer,
    recall,
    replace_cell_content,
    BUFFER_FILE,
    HISTORY_FILE,
)

# -- Vector memory (Chroma sidecar client) --
from .config import configure
from .client import get_or_create_collection, backend_info, health
from .errors import (
    MemoryError,
    MemoryServerUnavailable,
    MemoryRequestError,
    MemoryEmbeddingError,
    MemoryCollectionError,
    MemoryConfigurationError,
)

__all__ = [
    # Buffer memory
    "summarize_io_buffer",
    "recall_msg"
    "replace_cell_content",
    "BUFFER_FILE",
    "HISTORY_FILE",
    # Vector memory
    "configure",
    "get_or_create_collection",
    "backend_info",
    "health",
    # Reference indexing & RAG
    "indexing",
    "rag",
    # Personal facts & memory search (convenience re-exports from rag)
    "upsert_collective_fact",
    "recall_collective_facts",
    "search_summaries",
    # Errors
    # "MemoryError",
    # "MemoryServerUnavailable",
    # "MemoryRequestError",
    # "MemoryEmbeddingError",
    # "MemoryCollectionError",
    # "MemoryConfigurationError",
]

# -- Reference indexing & RAG helpers (imported last to avoid circular imports) --
from . import indexing, rag
from .rag import upsert_collective_fact, recall_collective_facts, search_memories
