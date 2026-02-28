## 8. Chora API Changes

### 8.1 New Phantasma Lifecycle Methods

```python
class Chora:

    # ---- Instance management (AI-facing API) ----

    @api_call(default_verbosity=Verbosity.ACK)
    def place(
        self,
        name: str,
        object: str,
        pose: Optional[Dict] = None,
        params: Optional[Dict] = None,
        description: str = "",
        render_visible: bool = True,
        raycast_visible: bool = True,
        costmap_affects: bool = False,
        save_to_yaml: bool = False,
    ) -> None:
        """
        Place a new phantasma instance in my world.

        Args:
            name:           Unique instance name.
            object:         Which phantasmata/*.py module to use.
            pose:           {'position': [x,y,z], 'rpy_deg': [r,p,y]}
            params:         Object-specific parameters (merged over SCHEMA).
            description:    What this is, for my own reference.
            save_to_yaml:   If True, persist to mind_palace.yaml.

        Note to self:
            Transient instances (save_to_yaml=False) exist only for this
            session. Good for temporary markers, debug viz, search results.
        """
        ...

    @api_call(default_verbosity=Verbosity.ACK)
    def remove(self, name: str, save_to_yaml: bool = False) -> None:
        """Remove an instance from my world."""
        ...

    @api_call(default_verbosity=Verbosity.ACK)
    def update_instance(self, name: str, **param_overrides) -> None:
        """
        Update params on an existing instance and trigger rebuild.

        Note to self:
            chora.update_instance('hallway_cabinet', doors_open=True,
                                  door_angle_deg=90)
        """
        ...

    @api_call(default_verbosity=Verbosity.ACK)
    def move_instance(
        self,
        name: str,
        position: Optional[List[float]] = None,
        rpy_deg: Optional[List[float]] = None,
    ) -> None:
        """Reposition an instance without rebuilding geometry."""
        ...

    @api_call(default_verbosity=Verbosity.ACK)
    def set_visible(
        self,
        name: str,
        render: Optional[bool] = None,
        raycast: Optional[bool] = None,
    ) -> None:
        """Toggle visibility flags on an instance."""
        ...

    # ---- Introspection ----

    def list_instances(self) -> Dict[str, dict]:
        """What's currently in my world."""
        ...

    def describe_instance(self, name: str) -> dict:
        """Full details: params, schema, pose, visibility, description."""
        ...

    def list_phantasmata(self) -> List[str]:
        """What .py modules are available in phantasmata/."""
        ...

    def describe_phantasma(self, object_name: str) -> dict:
        """SCHEMA + docstring + DYNAMIC flag for a phantasma module."""
        ...

    # ---- Bulk operations ----

    @api_call(default_verbosity=Verbosity.ACK)
    def reload_mind_palace(self) -> None:
        """Re-read YAML, rebuild everything."""
        ...

    @api_call(default_verbosity=Verbosity.ACK)
    def rebuild(self, name: str) -> None:
        """Force rebuild of a specific instance (even if static/cached)."""
        ...
```

### 8.2 Render Loop Integration

Inside `_render_scene()`, after adding the floor and point cloud:

```python
# ---- Phantasmata ----
# For each registered instance:
#   1. If DYNAMIC and should_rebuild() returns True (or absent): call build()
#   2. If static and no cached geometry: call build()
#   3. If static and cached: use cache
#   4. If build() returned None: skip
#   5. Apply pose transform (TF lookup if frame override, else static 4x4)
#   6. Add to scene if render_visible
#   7. Freeze for raycast snapshot if raycast_visible
#
# After rendering:
#   8. Collect hud() contributions from all instances that define it
#   9. Pass to overlay_hud() along with system HUD elements
```

### 8.3 FOV Parameter (New)

Add `fov_deg` parameter to `render()`:

```python
def render(
    self,
    ...
    fov_deg: Optional[float] = None,  # Vertical FOV in degrees. None = use config default.
    ...
):
```

Implementation: `scene.camera.set_projection(fov_deg, aspect, near, far)` where
`aspect = width / height`, `near = 0.01`, `far = 100.0`.

Provide named presets as module constants:

```python
# Common camera FOVs (vertical, degrees)
FOV_ASTRA = 49.5       # Astra Pro depth camera vertical FOV
FOV_WEBCAM_WIDE = 55.0 # Typical wide-angle webcam
FOV_DEFAULT = 60.0      # Good general-purpose
```

### 8.4 Snapshot Sidecar Save

When saving a render to disk, optionally save a JSON sidecar containing
everything needed to raycast that image later:

```python
# artifacts/chora/latest_render.png       <- the image
# artifacts/chora/latest_render.json      <- the sidecar
```

Sidecar contains:
```json
{
    "render_id": "a1b2c3d4e5f6",
    "timestamp": 1709000000.0,
    "resolution": [768, 768],
    "fov_deg": 60.0,
    "camera_world_pos": [1.0, 2.0, 0.7],
    "look_at_world_pos": [3.0, 2.0, 0.0],
    "view_matrix": [[...], ...],
    "projection_matrix": [[...], ...],
    "ray_infinity_distance_m": 50.0,
    "world_frame": "map",
    "robot_pose": {"x": 1.0, "y": 2.0, "yaw": 45.0}
}
```

This enables deferred raycasting: the AI can look at a saved render later
and still project pixel coordinates to world coordinates (minus point cloud
and mesh intersection — only floor and infinity would work, but that's the
most common use case).

Add `save_sidecar: bool = True` parameter to `render()` (defaults to True
when `save` is True).
