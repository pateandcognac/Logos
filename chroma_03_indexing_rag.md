# Logos Chroma Indexing & RAG — Implementation Spec (Part 3 of 3)

This is a focused sub-spec extracted from `chroma_implementation.md`.
It covers **Phases 4, 5, and 6**: building the technical reference indexer, few-shot example indexer, and semantic help RAG helper.

Prerequisites: both the sidecar (`chroma_01_sidecar_server.md`) and the Logos API client (`chroma_02_logos_client.md`) must be working before this layer is built.

See also:
- `chroma_01_sidecar_server.md` — Phases 1 & 2: the sidecar server
- `chroma_02_logos_client.md` — Phase 3: Python 3.8 Logos API client

---

## 1. Project Context

The immediate goal of the Logos memory system is a **semantic RAG layer for Logos's own API documentation, docstrings, and few-shot examples**. Logos already has a useful self-documenting `logos_help()` mechanism. This project extends that idea with semantic retrieval.

This spec builds the indexing pipeline and the agent-facing RAG helper.

---

## 2. Technical Reference vs Memory

This distinction is important.

Technical API docs, docstrings, signatures, and few-shot examples should be treated as **generated reference indexes**, not mutable memory.

The source of truth is the Logos codebase and curated example files, not the vector database.

**The vector database is an index.**

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

## 3. Semantic Help / RAG Indexing

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

Look at the existing `logos_help()` implementation and reuse its introspection where possible:

```bash
grep -R "def logos_help\|logos_help" -n ~/robot_workspaces/Logos/src/logos
```

---

## 4. Document Chunking Policy

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

## 5. Deterministic IDs and Metadata

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

## 6. Future Image / Multimodal Path

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

## 7. Implementation Phases for This File

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

* Locate curated examples (search the Logos repo for existing examples and helper docs).
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

## 8. Testing Strategy (Indexer)

Indexer tests:

* Extracts known function signature/docstring.
* Produces deterministic IDs.
* Produces expected metadata.
* Upsert does not duplicate generated docs.

Manual acceptance test (full end-to-end):

```python
from logos.memory import indexing, rag

indexing.refresh_technical_reference()

results = rag.search_api_help("How do I make Logos speak?")
print(results)
```

Expected: results include the `say` function docstring with source metadata.

---

## 9. Coding Style

* Keep code clear and boring.
* **Use Python 3.8-compatible syntax** — no walrus operator, no `match`, no `TypeAlias`, no `X | Y` union syntax.
* Prefer small modules.
* Add docstrings to public functions/classes.
* Use type hints where they improve clarity (`Optional[X]`, `List[X]`, `Union[X, Y]`).
* Do not make broad abstractions before v1 works.

The Logos API uses first-person comments in `src/`: *"I extract docstrings from my own API modules"* — match that style.

---

## 10. Critical Non-Goals

Do not:

* Let technical reference and personal memory share one collection.
* Let workspace-specific technical docs bleed into shared memory.
* Treat generated vector entries as source of truth (the codebase is the source of truth).
* Implement autonomous memory writing by the agent in v1.
* Build image or multimodal retrieval in v1.
