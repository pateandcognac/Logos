# src/logos/memory/__init__.py

"""
My long-term memory subsystem — both working buffer and persistent vector store.

I have three layers:

**1. Buffer memory** — working memory tools for the palimpsest (`io_buffer.jsonl`).
   I use these to summarize past events and recall specific messages from my I/O history.

**2. Vector memory** — semantic storage backed by Chroma + Ollama embeddings served by
   my local Python 3.11 sidecar. I use these to store and retrieve knowledge across
   sessions without relying on my context window size.

**3. Reference indexes & RAG** — generated indexes over my logos API and curated example
   files, queryable via natural language. I use these to look up how to use my own API
   or find relevant behavioral examples without reading source code directly.

Because my main runtime is Python 3.8, the vector client is a thin HTTP compatibility
layer that forwards requests to the Logos Chroma sidecar (`~/src/logos_chroma_server`),
which owns the Chroma SDK and Ollama embedding calls.

Typical usage:

    # --- Vector store ---
    memory.configure(workspace="Logos", server_url="http://127.0.0.1:8123")
    col = memory.get_or_create_collection("technical_reference")
    col.upsert(ids=["say:v1"], documents=["Function say(text) makes me speak."])
    results = col.query(query_texts=["How do I talk out loud?"], n_results=3)

    # --- Reference indexing ---
    from logos.memory import indexing
    indexing.refresh_all_reference_indexes()

    # --- Semantic RAG lookup ---
    from logos.memory import rag
    result = rag.semantic_help("How do I navigate to an absolute map position?")
    print(result["context"])

Pass `namespace="shared"` to `get_or_create_collection` for cross-workspace memory.
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
    "recall",
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
    # Errors
    "MemoryError",
    "MemoryServerUnavailable",
    "MemoryRequestError",
    "MemoryEmbeddingError",
    "MemoryCollectionError",
    "MemoryConfigurationError",
]

# -- Reference indexing & RAG helpers (imported last to avoid circular imports) --
from . import indexing, rag
