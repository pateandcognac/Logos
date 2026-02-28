## 11. Implementation Plan

### Phase 1: Foundation (Do First)

1. **Extract HUD to `logos/vision.py`**
   - Move `HudElement`, `HUD_ANCHORS`, font constants, `overlay_hud()`
   - Update chora.py to import from vision.py
   - Verify existing HUD still works

2. **Add `PhantasmaContext` dataclass to chora.py**

3. **Add phantasma lifecycle manager to `Chora` class**
   - `_load_mind_palace()` — parse YAML, import modules, validate schemas
   - `_build_phantasma_instance()` — call `build()`, apply pose transform, cache
   - `_rebuild_dynamic_phantasmata()` — for render loop
   - LRU or dict cache for static instance geometry

4. **Add instance management API**
   - `place()`, `remove()`, `update_instance()`, `move_instance()`, `set_visible()`
   - `list_instances()`, `describe_instance()`, `list_phantasmata()`, `describe_phantasma()`
   - `reload_mind_palace()`, `rebuild()`

5. **Integrate phantasmata into render loop**
   - Insert geometry into scene after floor + point cloud
   - Collect and apply `hud()` contributions
   - Freeze raycast-visible phantasmata into snapshots

6. **Add FOV parameter** to `render()` with presets

7. **Add sidecar save** (JSON alongside PNG)

8. **Update `mind_palace.yaml` loading** with schema validation

### Phase 2: Self-Model

9. **Create `self_model.py`**
   - Port geometry from existing `logos_mesh.py`
   - Add SCHEMA with augmentation toggles
   - Add `hud()` for system status indicators
   - Write thorough first-person comments as prompt engineering

    **Future additions:**
   - This require a pause for direct human interaction.
   - Add frustum visualization (Astra + pan-tilt)
   - Live face and arm pose updates
   - Sensor reading. Not particularly useful on a rendering, but useful as "how to read a sensor with my API context"

10. **Special-case self-model in chora**
    - Always loaded, always follows robot TF
    - Not in mind_palace.yaml (managed separately)
    - Still follows SCHEMA/build()/hud() convention

### Phase 3: System Phantasmata (Prove the Pattern)

11. **`phantasmata/grid_overlay.py`** — configurable floor grid
12. **`phantasmata/pointer_arrow.py`** — ephemeral 3D arrow for "point at thing"
13. **`phantasmata/occupied_plane.py`** — transparent obstacle plane at lidar height

### Phase 4: Config & Polish

14. **`config/chora_tuning.yaml`** — externalize advanced renderer settings
15. **Simplify `logos.config.chora`** to minimal keys
16. **Integrate with `logos.help()` system** — crawl phantasmata/, format SCHEMA
17. **Remove `gc.collect()` per-render** — gate behind setting or Nth-render
