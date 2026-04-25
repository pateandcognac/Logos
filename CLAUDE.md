# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

This is **Logos** — the codebase for an embodied AI robot running on ROS Noetic. The robot is Logos itself (a Gemini VLA model), and this workspace is both its API and its long-term memory. The code here is the robot's own tools, written in first person. Mark is the human developer/roommate who built the hardware.

The primary model(s) running the robot are **gemini-robotics-er-1.5-preview** and **gemini-3-flash-preview** (configured in `.system/framework_config.json`). Claude Code is used as an external development assistant for the codebase — not part of the live robot loop. [Note from Mark: Only for now, Claude! I have plans for you, too! :D]

## Runtime Environment

- **Python 3.8** (ROS Noetic constraint — no walrus operator, no `match`, no `TypeAlias`)
- **Open3D 0.13.0** — pinned, do not suggest upgrades. `OffscreenRenderer` is thread-affine; `LineSet` does not render in it (use thin `TriangleMesh` boxes instead); use `rendering.Material`, not `MaterialRecord`, in OffscreenRenderer paths.
- **ROS Noetic** — all ROS imports are guarded with `try/except ImportError` so modules can be introspected offline
- CWD when the robot runs is the workspace root (`~/robot_workspaces/Logos/`)
- No `sudo` access; Logos stays within its workspace

## Architecture

### The `logos` API (`src/logos/`)

The robot's one universal tool. Always available in its Python runtime without import. Key modules:

| Module | Purpose |
|--------|---------|
| `core.py` | `@api_call` decorator, `Verbosity` enum, `verbosity()` context manager, cooperative interrupts, `logos.api_help()` |
| `config.py` | `LogosConfig` — the persistent config object (`logos.config`). Sections: `vision`, `map3d`, `memory_policy`, `files`, `system` |
| `hooks.py` | Introspect/edit cognitive hook configs (`logos.hooks.show/upsert/remove`) |
| `vision.py` | Camera capture for `pan_tilt`, `top_down`, `astra` — webcams via OpenCV, Astra via ROS |
| `pantilt.py` | Servo control for the directed-gaze periscope. Degrees only; never radians. Pan: ±80–100°, Tilt: ±60–70° |
| `map3d.py` | Virtual 3D scene ("Chora") — render from ROS map + Astra point cloud + phantasmata, then raycast to world coords |
| `models.py` | ML/vision inference: `llm()` (out-of-band Gemini call), `yolo11()` (COCO 80-class fast), `yolo_world()` (open-vocab ~8k classes), `yoloe()` (prompted or prompt-free broad detection), `hands()` (MediaPipe gesture recognition) |
| `sensory.py` | Non-visual senses: ambient audio transcript access via ROS STT node |
| `nav.py` | Autonomous navigation via `move_base` (absolute) and `turtlebot_actions` (relative) |
| `memory.py` | io_buffer summarization and recall |
| `leds.py`, `emote.py`, `shell.py`, `files.py`, `ros.py`, `base.py` | Hardware I/O, filesystem, ROS utilities |

### The `@api_call` Decorator

Functions with side effects (movement, IO, state changes) are decorated with `@api_call(default_verbosity=Verbosity.ACK)`. This provides: cooperative interrupt checking, verbosity-controlled logging, and error printing. Plain functions are for pure computation/data.

### Cognitive Hooks (`config/arche_config.yaml`, `config/ephemera_config.yaml`)

Hooks are Python snippets that execute before each Logos cognition cycle to populate its context. They live in YAML with name, description, active, and code keys.

Complex hook logic lives in `src/hook_routines/` and is imported from the YAML code string.

### Mind Palace / Phantasmata (`src/logos/phantasmata/`, `hypomnemata/chora/mind_palace_00.yaml`)

Phantasmata are Python modules that define 3D geometry and/or HUD overlays rendered into the Chora view. Each module implements:
- `SCHEMA: dict` — parameter schema
- `build(params, ctx) -> SceneObject | List[SceneObject] | None`
- Optionally: `DYNAMIC: bool`, `hud(params, ctx)`, `should_rebuild(params, ctx)`, `cleanup(ctx)`

`PhantasmaContext` (from `phantasma_convention.py`) gives build functions access to the robot pose, TF buffer, and the live Python REPL namespace. That file also exports geometry helpers used by all phantasmata: `make_thin_box_line()` and `make_arrow()` — use these instead of `LineSet` (which does not render in OffscreenRenderer).

Instances are configured in `hypomnemata/chora/mind_palace_00.yaml` and managed via `logos.map3d.place/update_instance/set_visible/reload_mind_palace`.

### State and Memory (`state/`)

- `io_buffer.jsonl` — the palimpsest (live context window, summarized when it grows large)
- `io_history.jsonl` — the complete immutable I/O record

### Configuration (`config/`)

- `my_config.yaml` — Logos-editable overrides for `logos.config` sections (loaded at startup)
- `my_config_schema.yaml` — schema reference
- `arche_config.yaml` / `ephemera_config.yaml` — cognitive hook lists (arche = header, ephemera = footer)
- `mind_palace_00.yaml` — phantasma instances for the Chora render
- `map3d_tuning.yaml`, `5_mind_palace_schema.yaml` — tuning and schema docs

### System Files (`.system/`) — Do Not Modify

- `system_prompt.txt` — Logos's identity/system prompt (Gemini)
- `framework_config.json` — framework behavior (model, token limits, io_buffer display)
- `output_format.txt` — output format injected into system prompt

## Code Style

All persistent code in `src/` uses first-person comments: *"I build my geometry at the origin"* — not *"builds geometry at the origin."*

Docstring structure: one-line summary → intent paragraph → `Args` / `Returns` / `Note to self`.

Type hints use Python 3.8 syntax (`Optional[X]`, `List[X]`, `Union[X, Y]` — not `X | Y` or `list[x]`).

Angles are always degrees in public interfaces. Never expose radians.

`__all__` is defined in modules that have a meaningful public surface to limit what shows in `logos.api_help()`.

## No Traditional Build/Test System

There is no build step, test runner, or CI. Testing happens live on the robot via `<py>` blocks. When writing new modules, keep ROS imports gated so code can be read/linted offline! The `_llm_helper.py` bridge runs under a separate Python 3.11 venv with the Google GenAI SDK for out-of-band LLM calls.
