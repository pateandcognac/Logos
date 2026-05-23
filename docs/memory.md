# Memory

Logos has two memory layers in this repository: local chronological state and a
semantic vector-memory sidecar.

## Local State

The `state/` directory is runtime data, not public documentation:

- `io_buffer.jsonl` is the current palimpsest used to rebuild near-term context.
- `io_history.jsonl` is the complete local I/O record.
- `summaries.jsonl` stores generated synopses.

These files can contain personal or sensitive context and should generally stay
ignored for public publishing.

## Palimpsest Summarization

The buffer is not simply truncated. Logos can summarize older context into
synopses so useful continuity survives when the live context window gets too
large. The Python implementation lives in `src/logos/memory/_buffer.py`, with
policy hooks in `src/hook_routines/memory_manager.py`.

## Semantic Memory Sidecar

Modern ChromaDB does not fit the ROS Noetic Python 3.8 runtime, so Logos talks
to a separate Python 3.11 sidecar over HTTP.

Expected local sidecar:

- URL: `http://127.0.0.1:8123`
- Storage: `~/.local/share/logos_chroma`
- Embeddings: local Ollama embedding models, currently experimenting with
  `granite-embedding:30m`
- Collection naming: `logos__{namespace}__{kind}`

The client code in `src/logos/memory/` owns the robot-side naming conventions
and HTTP calls. The sidecar remains mostly name-agnostic.

## Public Publishing Notes

Memory exports, diaries, summaries, and history logs may contain personal data.
For a public release, keep generated memory/state ignored unless a specific file
has been intentionally reviewed and curated.
