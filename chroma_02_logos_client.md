# Logos Chroma API Client — Implementation Spec (Part 2 of 3)

This is a focused sub-spec extracted from `chroma_implementation.md`.
It covers **Phase 3**: building the Python 3.8-compatible Logos API memory client that talks to the sidecar over HTTP.

Prerequisites: the sidecar from `chroma_01_sidecar_server.md` must be running and passing its roundtrip test before this client is wired in.

See also:
- `chroma_01_sidecar_server.md` — Phases 1 & 2: the sidecar server
- `chroma_03_indexing_rag.md` — Phases 4–6: indexing and RAG helpers

---

## 1. Project Context

Logos is a ROS Noetic robot system running on Ubuntu 20.04 using Python 3.8.

Current ChromaDB packages require newer Python than the Logos runtime can reliably use. The solution is a thin HTTP client inside Logos that forwards calls to a Python 3.11 sidecar. **This spec builds that client.**

The Logos agent should understand that it is using a compatibility client, not the real Chroma SDK imported into Python 3.8.

The design should be transparent but ergonomic:

* The agent should not need to manually pass the current workspace on every call.
* The active workspace should be configured during Logos startup.
* The agent should be able to inspect the resolved collection name, workspace, and backend configuration when needed.
* Defaults should be safe and workspace-local.
* Shared/global memory should be opt-in.

---

## 2. Architecture Overview

```text
Logos LLM agent / Python tool node / Python 3.8
    ↓
Logos API memory module  ← THIS SPEC
    ↓ HTTP
~/src/logos_chroma_server/ running Python 3.11
    ↓
Chroma SDK + Ollama embeddings
```

**This spec covers the middle layer only.**

---

## 3. Logos API Memory Subsystem Layout

Implement the Python 3.8 client directly inside the Logos API repository.

Location:

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

This code must remain **Python 3.8-compatible**.

Do not create a separate ROS package for the memory client in v1. The Logos API is intentionally somewhat monolithic for transparency, self-documentation, flexibility, and agent inspectability. The LLM agent is allowed to inspect and edit its own Logos API code, so the memory client should live where the agent can see it naturally.

A separate `~/robot_ws/src/logos_memory_client/` package may be created later only if independent ROS nodes need their own importable client. Do not add that moving part prematurely.

---

## 4. v1 Scope for This Layer

Implement:

* Python 3.8 Logos API client with Chroma-like methods.
* Workspace-aware collection resolution.
* Health and backend-info passthrough.

Do not implement in v1:

* Image embeddings or multimodal retrieval.
* Autonomous memory writing by the agent.
* Complex auth.
* A full clone of the entire Chroma Python SDK.
* A separate ROS package for the memory client.

---

## 5. Collection and Namespace Policy

The system should distinguish between workspace scope, collection purpose, and data source / trust level.

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

## 6. Logos API Memory Client Interface

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

## 7. Startup Integration

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

Look at existing startup/inject patterns first:

```bash
grep -R "workspace" -n ~/robot_workspaces/Logos/src/logos | head -100
grep -R "startup\|inject\|tool" -n ~/robot_workspaces/Logos/src/logos | head -100
```

---

## 8. Error Handling (Client Side)

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

## 9. Agent Transparency

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

## 10. Implementation Phase

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

---

## 11. Testing Strategy (Client)

Logos API client tests:

* Collection name resolution.
* Request serialization.
* Query response passthrough shape.
* Sidecar unavailable error.
* Python 3.8 compatibility if test environment exists.

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

## 12. Coding Style

* Keep code clear and boring.
* **Use Python 3.8-compatible syntax** in Logos API code — no walrus operator, no `match`, no `TypeAlias`, no `X | Y` union syntax.
* Prefer small modules.
* Add docstrings to public functions/classes.
* Use type hints where they improve clarity (`Optional[X]`, `List[X]`, `Union[X, Y]`).
* Do not make broad abstractions before v1 works.

The Logos API uses first-person comments in `src/`: *"I build my geometry at the origin"* — not *"builds geometry."* Match that style.

---

## 13. Critical Non-Goals

Do not:

* Import current `chromadb` inside Logos's Python 3.8 runtime.
* Build a full Chroma clone.
* Create a separate ROS package for the client unless a real node needs it.
* Let technical reference and personal memory share one collection.
* Let workspace-specific technical docs bleed into shared memory.
* Treat generated vector entries as source of truth.
* Hide the sidecar architecture from the Logos agent.
* Make the LLM pass workspace names on every ordinary call.
