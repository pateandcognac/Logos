# Logos

Logos is a transparent hobby and research workspace for an embodied AI robot
running on ROS Noetic. It is not a polished product, installable SDK, or
turnkey robotics stack. It is the living code, documentation, configuration,
and memory scaffolding for one particular robot: a kit-bashed Turtlebot2-based
body built by Mark and inhabited by a Gemini robotics agent.

If you are reading this repository for the first time, start here:

1. [`.system/system_prompt.txt`](.system/system_prompt.txt) is the best
   description of Logos from the inside. It is Logos-facing runtime context.
2. [`.system/quick_start.md`](.system/quick_start.md) is the compact capability
   matrix Logos sees while writing Just-In-Time Behavior scripts.

Those two files explain the robot's operating world more directly than any
public-facing README can. This file is a human map around them.

## What This Repo Is

This repository is a ROS Noetic robot workspace plus the agent-facing API that
lets Logos improvise short Python behaviors in a persistent runtime. Logos sees
the `logos` API as one universal tool: camera capture, pan-tilt gaze, base
movement, sound, memory, hooks, the virtual 3D Chora scene, and filesystem
utilities are all available from Python.

The project is intentionally personal and experimental. Some files are clean
reference material; others are workbench notes, live configuration, memories, or
hardware-specific affordances. The point of publishing it is transparency:
showing how an embodied AI robot workspace can be assembled, lived in, and
iterated on by a self-taught builder.

## What Runs Live

Live robot behavior is centered on:

- `src/logos/` — the core Logos API, written for Python 3.8 and ROS Noetic.
- `src/skills/` — higher-level behaviors composed from the core API.
- `src/hook_routines/` — reusable code called by cognition hooks before each
  Logos thought cycle.
- `config/` — runtime YAML for hooks, preferences, cron jobs, and defaults.
- `.system/` — Logos-facing framework files, prompt context, few-shot examples,
  and generated API references.
- `hypomnemata/chora/` — live Chora and mind-palace configuration.
- `state/` and `ipc/` — local runtime memory/log/capture directories. These are
  not public data products and should generally stay untracked.

Human-facing repository documentation lives in `docs/` and is not needed by the
robot at runtime.

## Architecture At A Glance

Logos uses a third path between fixed state machines and end-to-end control:
Just-In-Time Behavior scripting. The agent emits short Python programs into a
persistent Python 3.8 environment. Those programs can run for seconds or
minutes, call ROS and hardware APIs, save observations, and yield back to the
next cognition cycle.

Major pieces:

- ROS Noetic provides the robot substrate: navigation, transforms, sensor
  topics, and base integration.
- Python 3.8 is required because of ROS Noetic constraints.
- Open3D 0.13.0 renders the Chora, Logos's virtual third-person spatial scene.
- Gemini robotics models provide the main embodied reasoning loop, currently
  configured in `.system/framework_config.json`.
- `logos.map3d` renders the robot, ROS map, Astra point cloud, and phantasmata
  into a raycastable 3D scene.
- Phantasmata in `src/logos/phantasmata/` are scriptable virtual objects placed
  into the Chora mind palace.
- Cognitive hooks in `config/arche_config.yaml` and
  `config/ephemera_config.yaml` populate Logos's context before each thought.
- The memory package talks to a local ChromaDB/Ollama sidecar because the
  robot's Python 3.8 environment cannot directly import modern ChromaDB.

## Hardware And Software Constraints

This repository assumes one physical robot and its local machine. Many paths,
camera names, ROS topics, and calibration decisions are hardware-specific.

Important constraints:

- ROS Noetic.
- Python 3.8 syntax only in runtime code.
- Open3D 0.13.0 pinned. Do not assume newer Open3D APIs.
- Public API angles are degrees, not radians.
- ROS imports are guarded so modules can be inspected offline.
- API keys and service credentials are expected through environment variables,
  never committed files.
- No `sudo` is assumed for the robot runtime.

## Repo Map

```text
.system/                  Logos-facing prompt, framework, examples, API docs
config/                   Runtime YAML configuration and hooks
docs/                     Human-facing public documentation
hypomnemata/              Logos's personal/reference files and Chora configs
ipc/                      Local image/metadata IPC captures, ignored
src/logos/                Core robot API
src/logos/memory/         Python 3.8 client for the vector memory sidecar
src/logos/phantasmata/    Chora virtual objects and self-model geometry
src/skills/               Higher-level behaviors
state/                    Local palimpsest/history/summaries, ignored
```

## More Documentation

- [Architecture](docs/architecture.md)
- [Runtime](docs/runtime.md)
- [Memory](docs/memory.md)
- [Chora](docs/chora.md)
- [Repository Hygiene](docs/repo-hygiene.md)
- [Contributing](CONTRIBUTING.md)
- [Security](SECURITY.md)
- [License](LICENSE)

## License

This repository is released under the [MIT License](LICENSE).

## Public Release Notes

This repository is shared as a living research artifact. Expect rough edges,
hardware assumptions, private-context placeholders, and code written for one
specific embodied agent. If you fork it, treat it as a source of patterns and
ideas rather than a package you can drop onto another robot unchanged.

Before publishing a new public snapshot, run a fresh secret/personal-data scan
and consider scanning Git history too. This pass only changes the current tree;
it does not rewrite history.
