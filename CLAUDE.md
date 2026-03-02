# Phantasmata: Dynamic Object System for Map3d

## Spec for Claude Code Implementation

**Project:** Logos — a ROS Noetic Turtlebot2-like robot controlled by a VLLM
**Module:** `src/logos/map3d.py` (virtual 3D world renderer, ROS map, navigation tool)
**Author context:** Mark (human), Claude (spec author), Claude Code (implementer)
**Python:** 3.8 strict (ROS Noetic constraint)
**Open3D:** 0.13.0 strict — do NOT upgrade or assume newer API

---

## 1. Executive Summary

Broadly, the `logos` API is a Python runtime environment and primary tool for
the VLLM AI controlling Logos the robot. It empowers them to interact with not just
their robot body, but also filesystem and context window. Of note is a cognitive
hook system, which runs configurable context collecting Python snippets each thought
loop. That context populates a header and footer surrounding the main io_buffer,
overwriting any content that was there. Crucially, these snippets are run in 
the same environment as the agent's code, enabling them to prime their
environment each loop; this means the agent can always see and use
up-to-the-moment information and the data structure that goes with it,
without context bombing it into the main io_buffer or bloating Python memory.

Map3d is Logos's "mind palace" — a virtual 3D renderer that lets the AI see its
environment from arbitrary viewpoints using the ROS occupancy grid, live RGBD
point cloud, and a self-model. The AI can then raycast rendered pixels back to
world coordinates for navigation and spatial reasoning.

**This spec defines Phantasmata:** a dynamic, scriptable object system that turns
most planned features (furniture, waypoints, grid overlays, debug visualizations,
alerts, skybox, occupied-plane overlay, etc.) into modular Python plugins rather
than hardcoded renderer features. Each phantasma is a `.py` file that returns
Open3D geometry and/or HUD overlays, with full access to the Python runtime,
ROS, the Logos API, and the filesystem.

### What stays in Map3d core

- The occupancy grid floor plane (it IS the world)
- The live Astra point cloud (raw sensor data)
- Camera setup, projection, lighting, background
- The render loop, scene assembly, snapshot/raycast pipeline
- The phantasma lifecycle manager
- Snapshot sidecar save/load for deferred raycasting

### What becomes a phantasma

Everything else. Furniture, waypoints, grid lines, skybox, camera frustum visualization,
occupied obstacle plane, battery alerts, velocity arrows, compass, scale bars,
debug visualizations, walls, decorative objects, "where are my keys"
pointers — all of it. Even HUD contributions (compass bar, scale indicator,
world-space labels) can come from phantasmata.

### What moves out of Map3d

- **The self-model** moves from `logos_mesh.py` to `self_model.py`, living
  alongside phantasmata. It becomes the most important phantasma: a dynamic,
  introspectable model of Logos's physical form that also serves as a
  prompt-engineering artifact and API usage example.
- **HUD rendering** (the `_overlay_hud` mechanism, `HudElement` dataclass,
  anchor system) moves to `logos/vision.py` so it's reusable for real camera
  image overlays too. Map3d calls into it.

#### Important Note about testing from Mark:

In practice, the `logos` API is loaded by an external ROS python_worker_node which interfaces with the AI cognition_node that provides it code to execute. Without this pipeline, you may have trouble testing the code you've written yourself. Ask the Mark for assistance as needed.
btw - You should be able to use `git` afaik? So feel free to make use of it.

---

## 2. Architecture Overview

```
Logos/
├── config/
│   ├── mind_palace_00.yaml        # Instance placement & params
│   └── map3d_tuning.yaml          # Advanced renderer knobs
├── src/logos/
│   ├── map3d.py                   # Core renderer + phantasma lifecycle
│   ├── vision.py                  # HUD system (extracted), camera capture
│   ├── self_model.py              # Logos's own mesh + augmentations
│   └── ...
└── phantasmata/                   # Plugin directory
    ├── grid_overlay.py
    ├── waypoints.py
    ├── occupied_plane.py
    ├── pointer_arrow.py
    ├── battery_indicator.py       # Used by charging_dock phantasma
    ├── charging_dock.py           # Monitors battery, triggers HUD alerts
    ├── coffee_table.py            # Example parametric furniture
    ├── cabinet.py                 # Example with doors_open state
    └── ...
```

### logos.config (was logos.state)

The relevant config sections. Note: `logos.state` is being renamed to
`logos.config` project-wide. The `map3d` section is deliberately minimal:

For more, see `config/my_config_schema.yaml`

A separate `config/map3d_tuning.yaml` (does not exist yet) holds advanced
knobs (voxel size, SOR params, hit radius, point sizes, etc.) that rarely change.
This file also serves as documentation of all available tuning parameters. These
values are loaded into `map3d.settings` at init and can be changed programmatically.

Moving forward, `logos.state` will be used by ROS callbacks, etc, to hold
robot state, rather than configuration preferences.

---

## 3. Phantasma Module Convention

A phantasma is a `.py` file in the `phantasmata/` directory.

### 3.1 Required Interface

```python
# phantasmata/example_object_schema.py
"""One-line summary of what the object is.

Longer description of my purpose, visual appearance, and behavior. I'm
written in first person because I'm part of Logos's environment and mind.
"""
...
See more in `Logos/src/3_phantasmata/phantasmata_convention.py`

---

## 4. PhantasmaContext

See `Logos/src/phantasmata/phantasmata_convention.py`

---

## 5. mind_palace.yaml

The instance placement file. Maps phantasma definitions (code) to instances
(placed in the world with specific parameters).

### Instance Schema

Each instance entry supports:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `object` | `str` | **required** | Which `phantasmata/*.py` to load |
| `description` | `str` | `""` | Free text for AI reference / help system |
| `pose` | `dict` | `None` | World placement (see below) |
| `pose.position` | `[x,y,z]` | `[0,0,0]` | Map frame meters |
| `pose.rpy_deg` | `[r,p,y]` | `[0,0,0]` | Degrees (we use degrees everywhere) |
| `pose.frame` | `str` | `None` | TF frame override (see §5.1) |
| `params` | `dict` | `{}` | Passed to `build()`, merged over SCHEMA defaults |
| `render_visible` | `bool` | `true` | Show in rendered image |
| `raycast_visible` | `bool` | `true` | Hittable by raycast |
| `costmap_affects` | `bool` | `false` | Flatten Z, inject into costmap |
| `shader` | `str` | `"defaultLit"` | Open3D shader override |

See more in: `Logos/memory/5_mind_palace_schema.yaml`

### 5.1 Pose Frame Override (Design Note / Future Consideration)

By default, phantasma instance poses are in the world frame (map). But some
objects are naturally defined relative to a specific TF frame:

```yaml
pose:
  frame: base_link        # Position is relative to base_link, re-resolved each render
  position: [0.0, 0.0, 0.4]
  rpy_deg: [0, 0, 0]
```

This would make the object "follow" whatever frame is specified — the robot
(`base_link`), the camera (`camera_rgb_optical_frame`), etc. Map3d would
TF-transform the pose to map frame at render time.

**Implementation note:** This is elegant but adds TF lookup cost per frame per
instance. Consider implementing only when needed (self_model augmentations like
the frustum are the main use case, and they can handle their own TF lookups
internally). Add a TODO/note in code for this.

---

## 6. Self-Model (self_model.py)

See `Logos/src/phantasmata/6_self_model.md`

---

## 7. HUD System Extraction

See `Logos/src/logos/7_hud_system_extraction.md`

---

## 8. Map3d API Changes

See `Logos/src/logos/8_map3d_api_changes.md`

---

## 9. Open3D 0.13 Gotchas & Constraints

**Implement with these burned into your brain. Do NOT Google for "better" approaches — they probably require newer Open3D.**

1. **OffscreenRenderer is thread-affine.** All renderer, scene, and material
   operations MUST happen on the dedicated render thread. The existing
   `_run_on_render_thread()` pattern is correct. Don't bypass it.

2. **LineSet does NOT render in OffscreenRenderer.** Use thin `TriangleMesh`
   boxes for lines (grid lines, arrows, wireframes, frustum edges). This is
   annoying but non-negotiable.

3. **Transparency:** Use `shader="defaultUnlit"` with `base_color` RGBA and
   `has_alpha=True`. Do NOT use shader strings like `"defaultUnlitTransparency"`
   or `"defaultLitTransparency"` — they cause Filament PreconditionPanic crashes
   in 0.13 (missing `srgbColor` uniform).

4. **`TriangleMesh.create_box()`** is NOT centered — it spans (0,0,0) to
   (w,h,d). Translate by (-w/2, -h/2, -d/2) if you want centered geometry
   that responds intuitively to pose placement.

5. **Texture via `rendering.Material`:** Use `mat.albedo_img` with an RGBA
   `o3d.geometry.Image`. This is the 0.13 path. `MaterialRecord` also exists
   but `Material` is the correct type for `scene.add_geometry()`.

6. **Transparency sorting artifacts** are unavoidable with multiple translucent
   layers. Open3D 0.13 does not do order-independent transparency. Accept
   artifacts for debug visualizations, or design around it (keep ≤2 translucent
   layers active).

7. **Raycasting:** Open3D 0.13's built-in raycasting (`RaycastingScene`) is
   broken or unavailable. That's why we do manual Möller–Trumbore and
   cylinder-distance tests. Don't try to use the built-in.

8. **`scene.camera.set_projection(fov, aspect, near, far)`** DOES exist in
   0.13. The intrinsic-matrix overload also exists. Both work.

9. **Scene rebuild cost:** `scene.clear_geometry()` + re-add everything is the
   pattern. There's no incremental scene update API in 0.13 OffscreenRenderer.
   This is fine for now. Optimize later if profiling shows it's a bottleneck (TODO).

10. **Renderer caching:** Creating `OffscreenRenderer` is expensive. The
    existing resolution-keyed cache (`self._renderers`) is correct. Don't
    create new renderers unnecessarily.

---

## 10. Coding Style Requirements

**Python 3.8 strict.** Use `from __future__ import annotations` at the top of
every file. Use `typing` module for type hints (`Optional`, `List`, `Dict`,
`Tuple`, `Union`). No `X | Y` union syntax. No walrus operator in complex
expressions (simple ones OK). No `match`/`case`.

**First person.** All comments, docstrings, and documentation are written as
Logos speaking about itself. "I build my geometry at the origin" not "builds
geometry at the origin." "Here's how I read my battery level" not "reads
battery level from ROS topic."

**Interleave gotcha comments.** When writing code that works around a known
limitation, include a comment explaining WHY in first person:
```python
# I'm using thin box meshes here because Open3D 0.13's LineSet doesn't
# render in OffscreenRenderer — this is a known 0.13 gotcha.
```

**PEP 8** with readability tweaks. Clear, descriptive names. Type hints on all
public functions and important internal helpers. Structured docstrings:
- First line: one-line summary
- Paragraph describing intent
- Sections: `Args:`, `Returns:`, `Note to self:` (for usage notes)

**Public API** lives under the `logos` namespace. Functions the AI calls from
`<py>` blocks are exposed as `logos.something`. Internal helpers are prefixed
with `_`.

**`@api_call(...)` decorator** on functions that do something in the world or
change persistent state. Data/compute functions are NOT decorated.

**Degrees everywhere.** Never expose radians in any public interface. Convert
internally.

**Memory hygiene.** Reuse variable names for large data. Use `del` for large
temporaries in long-lived code paths. Singletons for expensive objects. But
don't sweat small allocations — 32GB RAM, unused RAM is wasted RAM.

**YAML** for all configuration and data where human readability matters.

---

## 11. Implementation Plan

See `Logos/src/logos/11_implementation_plan.md`
---

## 12. TODOs & Future Work

See `Logos/src/logos/12_long_term_todos.md`

---

## 13. Key Files to Read

Before implementing, Claude Code should consider searching or reading these files for context:
- `Logos/memory/api_dashboard.md` — A `logos.help()` dump.
- `src/logos/map3d.py` — the existing renderer (uploaded, 2100 lines) 
- `src/logos/core.py` — `@api_call`, `Verbosity`, `check_for_interrupt`
- `src/logos/ros.py` — `logos_ros` helpers (TF, pose, topics)
- `src/logos/vision.py` — existing camera capture system, where HUD will live
- `logos_mesh.py` (or wherever the current robot mesh builder lives)
- `logos.help()` output — understand the introspection/stub system
- `logos.config` / `logos.state` — current config structure
- Any existing `phantasmata/` directory or prior art

---

## 14. Questions for Mark (if Ambiguous)

These are things Claude Code might need clarified during implementation:

1. Where does `logos.config` currently live and how is it loaded? (Need to know
   how to read `mind_palace_00.yaml` path and `phantasmata_dir` from it.)

A: Mark here :D There is a related TODO in the top 25 lines of `state.py`

2. What does `logos.help()` expect for it to discover and stub a module?
   (Need to know if SCHEMA is sufficient or if there's a registration step.)

A: I'm not sure. `def help()` starts at line 131 of core.py. Check it out and
   either make an elegant integrated solution there, or a distinct map3d
   helper, or whatever.  If integrating with help(), it is important that the
   info dumps of normal logos API functions and phantasmata be distinct.

   IMPORTANT ARCHITECTURAL DESIGN CONSIDERATION!!!!:
   If it makes more sense to put src/phantasmata/` somewhere else, like
   `src/logos/phantasmata`. OK. Claude Code has way better instincts than me that way!

3. Does `logos_mesh.py` currently live in `src/logos/` or elsewhere?

    A: Yes, currently in `logos/` --> `src/phantasmata/self_model.py`

4. Is there an existing `logos.utils.make_time_id()` or does it need to be
   created?

   A: Exists.

5. For the `@api_call` decorator — does it handle exceptions, or should
   phantasma `build()` failures be caught by the lifecycle manager?

   A: Have the lifecycle handle gracefully with some kind of subtle text feedback if possible.
   
6. Is there a preferred YAML library already in use? (`pyyaml` vs `ruamel.yaml`)

   A: ruamel.yaml

---

*Spec authored by Claude based on design conversation with Mark.*
*For implementation by Claude Code in the Logos workspace.*