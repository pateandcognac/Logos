# Logos Chroma Memory Integration — Agent Handoff Spec

This document is a context-rich implementation handoff for an agent working locally on the Logos robot machine. It describes the desired architecture, constraints, project layout, implementation priorities, and acceptance criteria for adding a Chroma-backed semantic memory / RAG system to Logos.

The target agent should treat this document as the starting project spec, not as immutable law. Prefer practical progress, clear code, and transparent behavior over over-engineered abstractions.

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

The main purpose of this project is not yet “personal memory.” The immediate goal is a semantic RAG layer for Logos’s own API documentation, docstrings, and few-shot examples. Logos already has a useful self-documenting `logos_help()` mechanism. This project should extend that idea with semantic retrieval.

The long-term goal may include durable personal memory, workspace-local episodic memory, shared human preferences, and image-aware memory. Do not optimize v1 around those future features, but avoid decisions that would block them.

---

## 2. Desired Architecture

Use a two-part architecture:

1. A standalone modern Python sidecar service.
2. A Python 3.8-compatible memory subsystem inside the Logos API.

The sidecar service owns Chroma, Ollama embedding calls, persistence, collection setup, and validation.

The Logos API memory subsystem acts as a thin compatibility client. It exposes Chroma-ish classes and methods to Logos’s LLM agent, but internally forwards requests over HTTP to the sidecar.

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

The Logos agent should understand that it is using a compatibility client, not the real Chroma SDK imported into Python 3.8.

The design should be transparent but ergonomic:

* The agent should not need to manually pass the current workspace on every call.
* The active workspace should be configured during Logos startup.
* The agent should be able to inspect the resolved collection name, workspace, and backend configuration when needed.
* Defaults should be safe and workspace-local.
* Shared/global memory should be opt-in.

---

## 3. Repository / Directory Layout

### 3.1 Chroma Sidecar Project

Create or use:

```text
~/src/logos_chroma_server/
```

This project should run in Python 3.11 or another modern Python version compatible with current Chroma packages.

Suggested layout:

```text
~/src/logos_chroma_server/
    README.md
    pyproject.toml
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

The exact Python packaging tool is not critical. Use the simplest stable approach already common on the machine. A plain venv and pip install is acceptable. Avoid clever dependency managers unless the existing local convention clearly uses one.

### 3.2 Logos API Memory Subsystem

Implement the Python 3.8 client directly inside the Logos API repository.

Likely location:

```text
~/robot_workspaces/Logos/src/logos/memory/
```

Suggested layout:

```text
~/robot_workspaces/Logos/src/logos/memory/
    __init__.py
    client.py
    collection.py
    config.py
    errors.py
    indexing.py
    rag.py
```

This code must remain Python 3.8-compatible.

Do not create a separate ROS package for the memory client in v1. The Logos API is intentionally somewhat monolithic for transparency, self-documentation, flexibility, and agent inspectability. The LLM agent is allowed to inspect and edit its own Logos API code, so the memory client should live where the agent can see it naturally.

A separate `~/robot_ws/src/logos_memory_client/` package may be created later only if independent ROS nodes need their own importable client. Do not add that moving part prematurely.

---

## 4. Scope for v1

Implement:

* A Python 3.11 Chroma sidecar server.
* Local text embeddings through Ollama.
* Chroma-backed storage and query for text documents.
* Python 3.8 Logos API client with Chroma-like methods.
* Workspace-aware collection resolution.
* A semantic API help / RAG workflow for Logos docstrings and few-shot examples.
* Deterministic upsert of generated technical reference documents.
* Health and backend-info endpoints.
* Basic tests proving end-to-end indexing and querying.

Do not implement in v1:

* Image embeddings.
* Multimodal retrieval.
* Long-term personal memory UI / UX.
* Autonomous memory writing by the agent.
* Complex auth.
* Multi-user remote deployment.
* A full clone of the entire Chroma Python SDK.
* A separate ROS package for the memory client.

---

## 5. Embedding Strategy

Use Ollama as the local embedding backend for v1.

Rationale:

* Ollama is already installed/tested locally.
* It cleanly separates model serving from the Python 3.8 Logos runtime.
* It provides a straightforward local HTTP API for embedding text.
* It allows future embedding model changes without forcing changes inside Logos’s Python interpreter.

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

---

## 6. Collection and Namespace Policy

The system should distinguish between:

* Workspace scope.
* Collection purpose.
* Data source / trust level.

Do not use only the workspace name as the collection name.

Recommended physical Chroma collection naming convention:

```text
logos__{namespace}__{collection_kind}
```

Examples:

```text
logos__Logos_nav_test__technical_reference
logos__Logos_nav_test__few_shot_examples
logos__shared__human_context
logos__Logos_nav_test__episodic_memory
```

Where:

* `namespace` is usually the current workspace slug.
* `collection_kind` describes what kind of data is stored.
* `shared` is reserved for explicitly shared memory.

Initial v1 collection kinds:

```text
technical_reference
few_shot_examples
```

Future collection kinds:

```text
human_context
workspace_notes
episodic_memory
vision_reference
multimodal_reference
```

Default behavior:

* `technical_reference` is workspace-scoped.
* `few_shot_examples` is workspace-scoped.
* `human_context` is shared/global when implemented.
* Agent-writable memory should not be part of v1 unless specifically requested later.

The Logos-side client should allow simple names while resolving them internally:

```python
docs = memory.get_or_create_collection("technical_reference")
```

Internally, with workspace `Logos_nav_test`, this resolves to:

```text
logos__Logos_nav_test__technical_reference
```

The collection object should expose transparency helpers:

```python
docs.name              # logical name, e.g. "technical_reference"
docs.resolved_name     # physical Chroma collection name
docs.workspace         # active workspace namespace
docs.backend_info()    # server/model/config summary
```

Allow explicit namespace override for advanced use:

```python
shared = memory.get_or_create_collection(
    "human_context",
    namespace="shared",
)
```

---

## 7. Technical Reference vs Memory

This distinction is important.

Technical API docs, docstrings, signatures, and few-shot examples should be treated as generated reference indexes, not mutable memory.

The source of truth is the Logos codebase and curated example files, not the vector database.

The vector database is an index.

For generated technical reference documents:

* Use deterministic IDs.
* Use upsert, not append-only accumulation.
* Include source path, symbol name, signature, and content hash.
* Rebuild or refresh when source files change.
* Treat generated reference as more authoritative than ordinary memory.

For future episodic or personal memory:

* Use timestamped IDs.
* Preserve history.
* Include provenance and timestamps.
* Keep separate from technical reference.

Do not mix these worlds. Mixing generated API docs with agent-written memories creates stale, spooky retrieval soup.

---

## 8. Sidecar Server API

Use FastAPI unless there is a strong reason not to.

The sidecar should not try to fully emulate Chroma’s entire HTTP API. It should expose the subset Logos needs while keeping method names and response shapes Chroma-like.

### 8.1 Required Endpoints

#### `GET /health`

Returns basic process health.

Example response:

```json
{
  "ok": true,
  "service": "logos_chroma_server",
  "version": "0.1.0"
}
```

#### `GET /backend-info`

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

#### `POST /collections/get-or-create`

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

#### `POST /collections/{collection_name}/upsert`

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

Response should be Chroma-ish and simple:

```json
{
  "ok": true,
  "count": 2
}
```

#### `POST /collections/{collection_name}/add`

Optional for v1 if `upsert` is enough. Implement only if the Logos client wants Chroma-like parity.

#### `POST /collections/{collection_name}/query`

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

#### `POST /collections/{collection_name}/get`

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

#### `POST /collections/{collection_name}/delete`

Support delete by ids and/or metadata filter.

Use carefully. Generated indexes should usually be refreshed by deterministic upsert or explicit rebuild commands.

---

## 9. Logos API Memory Client

The Logos-side memory client should be Python 3.8-compatible and should not import Chroma.

It should use a boring HTTP library compatible with the existing environment. `requests` is acceptable if already available. If not, use the simplest available option.

Expose a Chroma-ish interface:

```python
from logos import memory

memory.configure(
    workspace="Logos_nav_test",
    server_url="http://127.0.0.1:8123",
)

collection = memory.get_or_create_collection("technical_reference")

collection.upsert(
    ids=[...],
    documents=[...],
    metadatas=[...],
)

results = collection.query(
    query_texts=["How do I use the speech API?"],
    n_results=5,
)
```

Recommended module-level functions:

```python
configure(workspace=None, server_url=None, timeout=None)
get_client()
get_or_create_collection(name, namespace=None, metadata=None)
backend_info()
health()
```

Recommended collection methods:

```python
upsert(ids, documents=None, metadatas=None, embeddings=None)
add(ids, documents=None, metadatas=None, embeddings=None)
query(query_texts=None, query_embeddings=None, n_results=10, where=None, where_document=None, include=None)
get(ids=None, where=None, where_document=None, limit=None, offset=None, include=None)
delete(ids=None, where=None, where_document=None)
backend_info()
```

The client should keep response shapes close to Chroma where practical. Do not over-normalize responses into a custom format unless there is a clear reason.

The client should have clear error messages. When the sidecar is down, say that the Logos Chroma sidecar is unreachable and include the configured URL. Do not make failures look like empty query results.

---

## 10. Startup Integration

Logos already injects a small startup script into the Python tool node, mostly imports and setup.

Add memory configuration there.

Conceptual example:

```python
import logos.memory as memory

memory.configure(
    workspace=LOGOS_WORKSPACE_NAME,
    server_url="http://127.0.0.1:8123",
)
```

The actual variable names should follow the existing startup config conventions.

The agent should not be required to pass the workspace manually on normal memory calls.

The injected startup context or system prompt should explain:

```text
The Logos API includes a Python 3.8-compatible memory client. It mirrors the subset of Chroma collection behavior needed by Logos and forwards requests to a local Python 3.11 Chroma sidecar. By default, technical reference retrieval is scoped to the current Logos workspace. Shared memory is reserved for stable non-technical context.
```

---

## 11. Semantic Help / RAG Indexing

The first real use case is semantic retrieval over Logos API docs and usage examples.

Implement a helper that can build or refresh the technical reference index.

Possible API:

```python
from logos.memory import indexing

indexing.refresh_technical_reference()
indexing.refresh_few_shot_examples()
indexing.refresh_all_reference_indexes()
```

Possible agent-facing RAG helper:

```python
from logos.memory import rag

rag.search_api_help("How do I make Logos speak?")
rag.search_examples("How do I rotate in place and then speak?")
rag.semantic_help("How do I dock Logos?")
```

The output of semantic help should be concise and useful for the LLM agent. It should include source names and enough context to act.

Example return shape:

```python
{
    "query": "How do I make Logos speak?",
    "results": [
        {
            "document": "...",
            "metadata": {
                "symbol": "say",
                "signature": "say(text: str, ...)"
            },
            "distance": 0.123,
        }
    ]
}
```

The helper may format a human/LLM-readable context block too, but it should also keep raw structured results available.

---

## 12. Document Chunking Policy

For v1, keep chunking simple and deterministic.

Each function/class/API entry should become one document when possible.

For each API object, include:

* Symbol name.
* Module path.
* Signature.
* Docstring.
* Any known few-shot examples.
* Safety notes or usage constraints if available.

Suggested document format:

```text
Symbol: logos.motion.rotate
Signature: rotate(angle_degrees: float, speed: float = ...)
Source: src/logos/motion.py
Kind: api_docstring

Docstring:
...

Usage notes:
...

Examples:
...
```

Do not create huge mega-documents for the entire API. Retrieval works better when individual functions/classes are separate records.

If an entry is too long, split into stable subchunks:

```text
{symbol}:overview
{symbol}:examples
{symbol}:notes
```

---

## 13. Deterministic IDs and Metadata

Use deterministic IDs for generated technical reference documents.

Recommended pattern:

```text
{workspace}:{collection_kind}:{source_path}:{symbol}:{chunk_kind}
```

Example:

```text
Logos_nav_test:technical_reference:src/logos/speech.py:say:overview
```

Store a content hash in metadata so refresh code can skip unchanged documents if desired.

Suggested metadata for technical reference:

```python
{
    "workspace": "Logos_nav_test",
    "collection_kind": "technical_reference",
    "kind": "api_docstring",
    "source_path": "src/logos/speech.py",
    "module": "logos.speech",
    "symbol": "say",
    "signature": "say(text: str, voice: str = None)",
    "chunk_kind": "overview",
    "content_hash": "...",
    "git_commit": "...",
    "generated_at": "2026-04-24T...",
    "visibility": "workspace",
    "trust": "generated_from_source",
    "embedding_provider": "ollama",
    "embedding_model": "mxbai-embed-large"
}
```

For curated few-shot examples:

```python
{
    "workspace": "Logos_nav_test",
    "collection_kind": "few_shot_examples",
    "kind": "few_shot_example",
    "source_path": "...",
    "example_name": "speak_after_navigation",
    "content_hash": "...",
    "generated_at": "...",
    "visibility": "workspace",
    "trust": "curated_example"
}
```

---

## 14. Server Configuration

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

## 15. Service Lifecycle

The Chroma sidecar should not be started by the Logos agent itself.

Preferred startup options, in order:

1. A small manual run script for development.
2. A systemd user service or simple supervisor script for normal operation.
3. ROS launch integration only if it fits the existing harness cleanly.

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

## 16. Error Handling

The Logos API client should distinguish:

* Sidecar unreachable.
* Sidecar returned an error.
* Ollama unavailable.
* Embedding model missing.
* Chroma collection missing.
* Chroma query returned no results.
* Invalid request shape.
* Embedding dimension mismatch.

Do not silently return empty results for infrastructure failures.

Suggested exception classes inside Logos API:

```python
MemoryError
MemoryServerUnavailable
MemoryRequestError
MemoryEmbeddingError
MemoryCollectionError
MemoryConfigurationError
```

Keep names compatible with existing project style if there is already an error hierarchy.

---

## 17. Future Image / Multimodal Path

Do not implement images in v1.

Leave room for future methods:

```python
collection.add_images(...)
collection.query_images(...)
collection.query_multimodal(...)
```

Future design likely needs separate collections:

```text
logos__{workspace}__vision_reference
logos__{workspace}__multimodal_reference
```

Possible future approaches:

1. Image captions / scene summaries embedded as text.
2. True image embeddings with a multimodal model.
3. Dual retrieval: text collection + vision collection, then result fusion.

Do not contaminate the v1 text technical-reference collections with image embeddings later. Use separate collection kinds.

---

## 18. Agent Transparency

The Logos agent should know what it is using.

Suggested system/context wording:

```text
You have access to a local Chroma-backed memory client through the Logos Python API.
Because this runtime uses Python 3.8, the client is a thin compatibility layer that forwards requests to a Python 3.11 memory server using the official Chroma SDK.

By default, memory operations are scoped to your current workspace. Technical reference collections are generated from the current Logos source tree and should be treated as more authoritative than ordinary memory notes. Shared memory, when available, is reserved for stable non-technical context such as human preferences or long-lived interaction facts.

Prefer semantic help queries over guessing API usage from memory.
```

This should be visible in the agent-facing docs or startup context.

---

## 19. Implementation Phases

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

### Phase 3 — Logos API Client

Create `logos/memory/` inside the Logos API.

Implement:

* `configure()`.
* `get_client()`.
* `get_or_create_collection()`.
* `Collection` class.
* `upsert`, `query`, `get`, `delete`.
* Workspace-to-collection-name resolution.
* `backend_info()`.

Acceptance:

* Python 3.8 can import the module.
* No `chromadb` import exists in Logos API client code.
* Agent-facing call shape is Chroma-ish.
* Sidecar-down errors are clear.

### Phase 4 — Technical Reference Indexer

Implement:

* Python docstring/signature extraction.
* Deterministic document construction.
* Stable IDs.
* Metadata generation.
* Upsert into `technical_reference`.

Acceptance:

* Running refresh indexes current Logos API docs.
* Re-running refresh updates rather than duplicates.
* Querying for an API behavior returns relevant docstrings.

### Phase 5 — Few-Shot Example Indexer

Implement:

* Locate curated examples.
* Chunk examples sensibly.
* Upsert into `few_shot_examples`.

Acceptance:

* Semantic queries retrieve relevant examples.
* Example source metadata is present.

### Phase 6 — Semantic Help Helper

Implement:

* `rag.semantic_help(query)` or similar.
* Query technical docs and examples.
* Return structured results plus optional formatted context.

Acceptance:

* The Logos agent can ask how to use an API capability and receive relevant doc/help snippets.
* The helper makes source/trust clear.

---

## 20. Testing Strategy

Keep tests practical.

Sidecar tests:

* Health endpoint.
* Backend-info endpoint.
* Ollama embedding returns a vector.
* Chroma collection create/upsert/query roundtrip.
* Error response when required fields are missing.

Logos API client tests:

* Collection name resolution.
* Request serialization.
* Query response passthrough shape.
* Sidecar unavailable error.
* Python 3.8 compatibility if test environment exists.

Indexer tests:

* Extracts known function signature/docstring.
* Produces deterministic IDs.
* Produces expected metadata.
* Upsert does not duplicate generated docs.

Manual acceptance test:

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

## 21. Coding Style

For Python:

* Keep code clear and boring.
* Use Python 3.8-compatible syntax in Logos API code.
* Use Python 3.11-compatible modern style in sidecar code, but avoid being pointlessly fancy.
* Prefer small modules.
* Add docstrings to public functions/classes.
* Use type hints where they improve clarity.
* Do not make broad abstractions before v1 works.

Remember: this project is a compatibility bridge and RAG helper, not a new vector database framework.

---

## 22. Critical Non-Goals

Do not:

* Import current `chromadb` inside Logos’s Python 3.8 runtime.
* Build a full Chroma clone.
* Create a separate ROS package for the client unless a real node needs it.
* Let technical reference and personal memory share one collection.
* Let workspace-specific technical docs bleed into shared memory.
* Treat generated vector entries as source of truth.
* Hide the sidecar architecture from the Logos agent.
* Make the LLM pass workspace names on every ordinary call.

---

## 23. Open Design Questions

These can be decided during implementation:

1. Exact Ollama embedding model for v1.

   * Default assumption: `mxbai-embed-large`.

2. Whether sidecar uses Chroma HTTP server mode immediately or embedded persistent Chroma behind the sidecar.

   * User preference: Version B / server mode because other nodes may touch it.
   * Practical fallback: make backend configurable.

3. Exact source locations for few-shot examples.

   * Search the Logos repo for existing examples and helper docs.

4. How `logos_help()` is currently implemented.

   * Reuse its existing introspection if possible.

5. How workspace name is currently passed into the Logos launch/startup system.

   * Reuse existing config rather than inventing a parallel one.

6. Whether to add a manual `rebuild_reference_index()` command exposed to the agent.

   * Likely yes.

---

## 24. Recommended First Local Commands for Agent

Start by inspecting existing conventions.

```bash
ls ~/src
ls ~/robot_workspaces
ls ~/robot_workspaces/Logos/src/logos
find ~/robot_workspaces/Logos/src/logos -maxdepth 3 -type f | sort | head -200
```

Look for:

```bash
grep -R "def logos_help\|logos_help" -n ~/robot_workspaces/Logos/src/logos || true
grep -R "workspace" -n ~/robot_workspaces/Logos/src/logos | head -100 || true
grep -R "startup\|inject\|tool" -n ~/robot_workspaces/Logos/src/logos | head -100 || true
```

Inspect the existing TTS server for style and deployment precedent:

```bash
find ~/src/logos_tts_server -maxdepth 3 -type f | sort | head -200
```

Check Ollama:

```bash
ollama list
curl http://127.0.0.1:11434/api/tags
```

Do not modify large areas of the Logos API until the sidecar has a proven upsert/query roundtrip.

---

## 25. Final Design Summary

Build `~/src/logos_chroma_server/` as a Python 3.11 local sidecar that owns Chroma and Ollama embeddings.

Build `logos/memory/` inside the Logos API as a Python 3.8-compatible Chroma-ish client.

Use workspace-scoped technical collections for generated API docs and examples.

Keep shared memory separate and future-facing.

Use deterministic IDs and upsert for generated technical reference.

Expose enough backend transparency that the Logos agent knows exactly what kind of tool it is using.

Do the smallest useful thing first: semantic help over Logos’s own API.
