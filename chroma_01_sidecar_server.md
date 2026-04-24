# Logos Chroma Sidecar Server — Implementation Spec (Part 1 of 3)

This is a focused sub-spec extracted from `chroma_implementation.md`.
It covers **Phases 1 and 2**: building the standalone Python 3.11 FastAPI sidecar that owns Chroma and Ollama embeddings.

See also:
- `chroma_02_logos_client.md` — Phase 3: Python 3.8 Logos API client
- `chroma_03_indexing_rag.md` — Phases 4–6: indexing and RAG helpers

---

## 1. Project Context

Logos is a ROS Noetic robot system running on Ubuntu 20.04. The robot uses a custom Python API to expose tools and robot capabilities to an LLM-controlled Python interpreter.

Important constraints:

* ROS Noetic on Ubuntu 20.04 uses Python 3.8.
* Current ChromaDB packages require newer Python than the Logos runtime can reliably use.
* Logos should not import the modern `chromadb` package directly inside the ROS / Python 3.8 process.
* Logos runs on a repurposed ThinkPad T580, not a small SBC.
* Hardware: ThinkPad T580, 32 GB RAM, Intel i7-8550U, CPU-only.
* Local embeddings are preferred.
* Ollama is available and has already been tested successfully with embedding models.
* Quality matters more than speed.
* Initial scope is text-only.
* Image / multimodal retrieval should remain a future-compatible design path, but should not be implemented in v1.

The main purpose of this project is not yet "personal memory." The immediate goal is a semantic RAG layer for Logos's own API documentation, docstrings, and few-shot examples.

---

## 2. Desired Architecture

Use a two-part architecture:

1. A standalone modern Python sidecar service.
2. A Python 3.8-compatible memory subsystem inside the Logos API.

The sidecar service owns Chroma, Ollama embedding calls, persistence, collection setup, and validation.

The Logos API memory subsystem acts as a thin compatibility client. It exposes Chroma-ish classes and methods to Logos's LLM agent, but internally forwards requests over HTTP to the sidecar.

The intended data path is:

```text
Logos LLM agent / Python tool node / Python 3.8
    ↓
Logos API memory module
    ↓ HTTP
~/src/logos_chroma_server/ running Python 3.11
    ↓
Chroma SDK + Chroma server/client usage + Ollama embeddings
```

**This spec covers the bottom layer: `~/src/logos_chroma_server/`.**

---

## 3. Sidecar Repository Layout

Create or use:

```text
~/src/logos_chroma_server/
```

This project should run in Python 3.11 or another modern Python version compatible with current Chroma packages.

Suggested layout:

```text
~/src/logos_chroma_server/
    README.md
    .env.example
    src/
        logos_chroma_server/
            __init__.py
            main.py
            config.py
            schemas.py
            chroma_backend.py
            embeddings.py
            collections.py
            errors.py
            health.py
    scripts/
        run_dev.sh
        install_venv.sh
    tests/
        test_health.py
        test_embeddings.py
        test_collections.py
        test_roundtrip.py
```

The exact Python packaging tool is not critical. Use the simplest stable approach already common on the machine. A plain venv and pip install is acceptable. Avoid clever dependency managers.

---

## 4. Embedding Strategy

Use Ollama as the local embedding backend for v1.

Rationale:

* Ollama is already installed/tested locally.
* It cleanly separates model serving from the Python 3.8 Logos runtime.
* It provides a straightforward local HTTP API for embedding text.
* It allows future embedding model changes without forcing changes inside Logos's Python interpreter.

The sidecar should call Ollama explicitly, receive vectors, then pass those embeddings to Chroma. Do not rely on Chroma collection embedding functions for v1 unless there is a strong local reason to do so.

Why explicit embedding is preferred:

* The sidecar can record exactly which embedding model was used.
* The sidecar can validate dimensions before writing to Chroma.
* Re-embedding can be triggered intentionally.
* Collection metadata can record model/dimension/source information.
* Future migrations are easier.

Default embedding model:

* Use `mxbai-embed-large` as the first default unless local testing suggests a different model is clearly better.

Important rule:

* Do not mix embedding models inside the same Chroma collection.

If the embedding model changes, either rebuild the relevant collections or create new model-versioned collections. Same-dimensional embeddings from different models are still not semantically interchangeable.

Suggested embedding metadata:

```python
{
    "embedding_provider": "ollama",
    "embedding_model": "mxbai-embed-large",
    "embedding_dimension": 1024,
    "embedded_at": "2026-04-24T...",
}
```

Verify the actual dimension from the Ollama response at runtime. Do not hardcode it blindly unless the server has validated it.

Check Ollama before starting:

```bash
ollama list
curl http://127.0.0.1:11434/api/tags
```

---

## 5. Sidecar Server API

Use FastAPI unless there is a strong reason not to.

The sidecar should not try to fully emulate Chroma's entire HTTP API. It should expose the subset Logos needs while keeping method names and response shapes Chroma-like.

### `GET /health`

Returns basic process health.

Example response:

```json
{
  "ok": true,
  "service": "logos_chroma_server",
  "version": "0.1.0"
}
```

### `GET /backend-info`

Returns Chroma and embedding backend information.

Example response:

```json
{
  "ok": true,
  "chroma": {
    "mode": "http_or_persistent",
    "host": "127.0.0.1",
    "port": 8000,
    "persist_directory": "/home/.../.logos_chroma"
  },
  "embeddings": {
    "provider": "ollama",
    "model": "mxbai-embed-large",
    "dimension": 1024,
    "base_url": "http://127.0.0.1:11434"
  }
}
```

The exact fields may vary, but keep it useful for debugging.

### `POST /collections/get-or-create`

Request:

```json
{
  "name": "logos__Logos_nav_test__technical_reference",
  "metadata": {
    "workspace": "Logos_nav_test",
    "kind": "technical_reference",
    "embedding_provider": "ollama",
    "embedding_model": "mxbai-embed-large"
  }
}
```

Response should include collection metadata and resolved name.

### `POST /collections/{collection_name}/upsert`

Accepts documents, metadata, and optional embeddings.

If embeddings are not provided, the sidecar embeds the documents through Ollama.

Request:

```json
{
  "ids": ["id1", "id2"],
  "documents": ["text one", "text two"],
  "metadatas": [
    {"kind": "api_docstring"},
    {"kind": "api_docstring"}
  ],
  "embeddings": null
}
```

Response:

```json
{
  "ok": true,
  "count": 2
}
```

### `POST /collections/{collection_name}/add`

Optional for v1 if `upsert` is enough. Implement only if the Logos client wants Chroma-like parity.

### `POST /collections/{collection_name}/query`

Accepts either `query_texts` or `query_embeddings`.

If `query_texts` are provided, the sidecar embeds them before querying Chroma.

Request:

```json
{
  "query_texts": ["How do I rotate Logos in place?"],
  "query_embeddings": null,
  "n_results": 5,
  "where": {"kind": "api_docstring"},
  "where_document": null,
  "include": ["documents", "metadatas", "distances"]
}
```

Response should intentionally resemble Chroma query output:

```json
{
  "ids": [["id1", "id2"]],
  "documents": [["...", "..."]],
  "metadatas": [[{"...": "..."}, {"...": "..."}]],
  "distances": [[0.123, 0.456]]
}
```

### `POST /collections/{collection_name}/get`

Support common Chroma-ish fields:

```json
{
  "ids": null,
  "where": {"source_path": "..."},
  "where_document": null,
  "limit": 20,
  "offset": 0,
  "include": ["documents", "metadatas"]
}
```

### `POST /collections/{collection_name}/delete`

Support delete by ids and/or metadata filter.

Use carefully. Generated indexes should usually be refreshed by deterministic upsert or explicit rebuild commands.

---

## 6. Server Configuration

Use a simple config file and environment variables.

Suggested `.env` fields:

```text
LOGOS_CHROMA_HOST=127.0.0.1
LOGOS_CHROMA_PORT=8123
LOGOS_CHROMA_PERSIST_DIR=/home/mark/.local/share/logos_chroma
LOGOS_OLLAMA_BASE_URL=http://127.0.0.1:11434
LOGOS_EMBEDDING_MODEL=mxbai-embed-large
LOGOS_DEFAULT_N_RESULTS=5
```

If Chroma itself is run as a separate server, include:

```text
LOGOS_CHROMA_MODE=http
LOGOS_CHROMA_HTTP_HOST=127.0.0.1
LOGOS_CHROMA_HTTP_PORT=8000
```

If the sidecar uses embedded persistent Chroma internally, include:

```text
LOGOS_CHROMA_MODE=persistent
```

The user has expressed a preference for Version B, where other nodes may also touch Chroma. Therefore the preferred architecture is sidecar-to-Chroma-server where practical. However, do not block v1 on this if local embedded Chroma inside the sidecar is vastly simpler. Make the backend mode configurable so it can move from persistent to HTTP server mode without changing the Logos API client.

---

## 7. Service Lifecycle

The Chroma sidecar should not be started by the Logos agent itself.

Preferred startup options, in order:

1. A small manual run script for development.
2. ROS launch integration 

Development script example:

```bash
#!/usr/bin/env bash
set -euo pipefail
cd ~/src/logos_chroma_server
source .venv/bin/activate
uvicorn logos_chroma_server.main:app --host 127.0.0.1 --port 8123
```

The Logos API client should fail clearly if the sidecar is not running.

---

## 8. Error Handling (Sidecar Side)

The sidecar should return clear HTTP error responses (not silent 200s with empty data) when:

* Ollama is unreachable.
* Embedding model is missing.
* Chroma collection is missing.
* Embedding dimension mismatch is detected.
* Request shape is invalid.

Do not silently return empty results for infrastructure failures.

---

## 9. Implementation Phases for This File

### Phase 1 — Sidecar Skeleton

Create `~/src/logos_chroma_server/`.

Implement:

* FastAPI app.
* Config loading.
* `/health`.
* `/backend-info`.
* Ollama embedding test call.
* Basic logging.

Acceptance:

* `curl http://127.0.0.1:8123/health` returns ok.
* `/backend-info` reports configured embedding model and Chroma mode.
* Server fails clearly if Ollama is unreachable or model is missing.

### Phase 2 — Chroma Backend

Implement:

* Chroma client initialization.
* Collection get/create.
* Upsert with explicit embeddings.
* Query with `query_texts`.
* Get and delete as needed.

Acceptance:

* Can upsert two test documents.
* Can query semantically and retrieve the expected one.
* Response shape resembles Chroma query output.

---

## 10. Testing Strategy (Sidecar)

Sidecar tests:

* Health endpoint.
* Backend-info endpoint.
* Ollama embedding returns a vector.
* Chroma collection create/upsert/query roundtrip.
* Error response when required fields are missing.

Manual acceptance test (run after client is also implemented):

```python
from logos import memory

memory.configure(workspace="Logos_test", server_url="http://127.0.0.1:8123")

col = memory.get_or_create_collection("technical_reference")

col.upsert(
    ids=["test:say"],
    documents=["Function say(text) makes Logos speak text out loud using the TTS system."],
    metadatas=[{"kind": "api_docstring", "symbol": "say"}],
)

result = col.query(
    query_texts=["How does Logos talk out loud?"],
    n_results=1,
)

print(result)
```

Expected: query returns the `test:say` document with metadata.

---

## 11. Coding Style

* Use Python 3.11-compatible modern style in sidecar code, but avoid being pointlessly fancy.
* Keep code clear and boring.
* Prefer small modules.
* Add docstrings to public functions/classes.
* Use type hints where they improve clarity.
* Do not make broad abstractions before v1 works.

Remember: this project is a compatibility bridge and RAG helper, not a new vector database framework.

---

## 12. Critical Non-Goals

Do not:

* Import current `chromadb` inside Logos's Python 3.8 runtime.
* Build a full Chroma clone.
* Create a separate ROS package for the client unless a real node needs it.
* Let technical reference and personal memory share one collection.
* Let workspace-specific technical docs bleed into shared memory.
* Treat generated vector entries as source of truth.
* Hide the sidecar architecture from the Logos agent.
* Make the LLM pass workspace names on every ordinary call.

---

## 13. Open Design Questions

1. Exact Ollama embedding model for v1.
   * Default assumption: `mxbai-embed-large`.

2. Whether sidecar uses Chroma HTTP server mode immediately or embedded persistent Chroma behind the sidecar.
   * User preference: server mode because other nodes may touch it.
   * Practical fallback: make backend configurable.
