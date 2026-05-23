# Architecture

This is a human-facing overview of the Logos robot workspace. The Logos-facing
truth lives in [`.system/system_prompt.txt`](../.system/system_prompt.txt) and
the API quick reference in [`.system/quick_start.md`](../.system/quick_start.md).

## Core Idea

Logos is an embodied AI agent that controls a ROS Noetic robot through a
persistent Python 3.8 runtime. Instead of relying only on fixed state machines,
Logos writes short Just-In-Time Behavior scripts: small Python programs that
compose perception, movement, speech, memory, and filesystem operations for the
moment at hand.

That runtime exposes the `logos` API without requiring explicit imports inside
Logos's code blocks. The API is the stable layer between the model and the body.

## Main Layers

- Cognition framework: builds Logos's prompt from system context, palimpsest
  state, hooks, and current user/environment input.
- Persistent Python tool: executes Logos-authored Python blocks in a stateful
  ROS-aware Python 3.8 process.
- `src/logos/`: hardware and OS primitives, including vision, navigation,
  pan-tilt gaze, sound, LEDs, files, shell helpers, Chora rendering, and memory.
- `src/skills/`: higher-level behaviors composed from `logos` primitives.
- Hook system: YAML-configured Python snippets run before each cognition cycle
  to add live context or small reflexive behavior.
- Chora/map3d: an Open3D 0.13.0 virtual scene used for spatial reasoning.
- Memory sidecar: a Python 3.11 FastAPI/ChromaDB service accessed through a
  Python 3.8-compatible HTTP client.

## Runtime Data Flow

1. New input arrives from Mark, speech transcription, environment hooks, or
   prior Python output.
2. The framework runs active arche and ephemera hooks from `config/`.
3. Recent I/O plus summaries are assembled from `state/`.
4. Logos receives this context and may emit a Python block.
5. The Python runtime executes the block using `logos` APIs and ROS.
6. Output, saved captures, and state updates return to the next cognition loop.

## Design Biases

The code favors creative composability over robotics purity. Public interfaces
prefer degrees, compact YAML, readable docs, and primitives Logos can recombine
on the fly. ROS conventions are used where they help and bypassed where direct
hardware or filesystem IPC is more practical for this one robot.

Persistent runtime code should stay Python 3.8-compatible. In practice that
means `Optional[X]` instead of `X | None`, no `match`, and no walrus operator.
