## 3. Phantasma Module Convention

A phantasma is a `.py` file in the `phantasmata/` directory.

### 3.1 Required Interface

```python
# phantasmata/example_object_schema.py
"""One-line summary of what I am.

Longer description of my purpose, visual appearance, and behavior.
I'm written in first person because I'm part of Logos's mind.
"""

# ---- Schema: what params I accept ----
# logos.help() reads this. mind_palace.yaml validates against it.
SCHEMA = {
    'width':  {'type': 'float', 'default': 1.0, 'unit': 'm',
               'description': 'My width along X'},
    'color':  {'type': 'rgb',   'default': [0.5, 0.5, 0.5],
               'description': 'My surface color'},
    'active': {'type': 'bool',  'default': True,
               'description': 'Whether I should appear at all'},
}

# Lifecycle flag (default False if absent)
#   False = I'm built once and cached until my params change or
#           someone calls chora.rebuild(). Efficient for static geometry.
#   True  = I'm rebuilt every render. Use for live/animated state.
DYNAMIC = False

def build(params, ctx):
    """
    Construct my geometry and return it.

    Args:
        params: Dict of my resolved parameters (YAML merged over SCHEMA defaults).
        ctx:    PhantasmaContext — my window into the runtime.

    Returns:
        SceneObject, List[SceneObject], or None.
        None means "I have nothing to show right now."
        Name field can be '__auto__' — chora replaces with my instance name.
    """
    ...
```

### 3.2 Optional Interface

```python
def hud(params, ctx):
    """
    Contribute HUD overlays to the rendered image.

    Args:
        params: Same as build().
        ctx:    Same as build().

    Returns:
        List[HudElement] or None.

    Note to self:
        This runs every render regardless of DYNAMIC flag.
        I use this for compass bars, scale indicators, world-space labels,
        or any 2D overlay that accompanies my 3D geometry.
    """
    ...

def cleanup(ctx):
    """
    Called when my instance is removed from the scene.

    Note to self:
        I use this if I allocated ROS subscribers, opened files, or
        hold large resources that won't be garbage collected promptly.
    """
    ...
```

### 3.3 Schema Types

The `SCHEMA` dict supports these type strings:

| Type | Python type | YAML example | Notes |
|------|-------------|--------------|-------|
| `'float'` | `float` | `1.5` | Optional `'range': [min, max]`, `'unit': 'm'` |
| `'int'` | `int` | `3` | Optional `'range': [min, max]` |
| `'bool'` | `bool` | `true` | |
| `'str'` | `str` | `"hello"` | |
| `'rgb'` | `List[float]` | `[1.0, 0.5, 0.0]` | 3-element, 0.0–1.0 |
| `'rgba'` | `List[float]` | `[1.0, 0.5, 0.0, 0.8]` | 4-element, 0.0–1.0 |
| `'choice'` | `str` | `"billboard"` | Requires `'options': [...]` |
| `'path'` | `str` | `"waypoints.yaml"` | Filesystem path (relative to workspace) |
| `'list'` | `list` | `[1, 2, 3]` | Generic list |

### 3.4 Conditional Caching for Dynamic Phantasmata

For `DYNAMIC = True` phantasmata that are expensive to rebuild but only change
occasionally (e.g., battery indicator that only changes geometry when level
crosses a threshold), an optional `should_rebuild()` function gates the rebuild:

```python
DYNAMIC = True

def should_rebuild(params, ctx):
    """
    Return True if I need to rebuild my geometry this frame.
    If absent or returns True, build() runs every render.
    If returns False, my cached geometry from the last build() is reused.

    Note to self:
        I use this to avoid rebuilding expensive geometry every frame
        when my underlying state hasn't actually changed.
    """
    battery = logos.ros.get_battery_level()
    return battery != _last_battery_level

def build(params, ctx):
    ...
```

The lifecycle manager calls `should_rebuild()` first. If it returns `False`,
the cached `SceneObject` from the previous `build()` is reused without calling
`build()` again. Module-level state (like `_last_battery_level`) is fine here
since phantasmata are long-lived Python modules.

---

The runtime context passed to `build()`, `hud()`, `should_rebuild()`, and
`cleanup()`. This is a convenience namespace — phantasmata can also just import
whatever they need directly, since they run in the same Python process.

```python
@dataclass
class PhantasmaContext:
    """Runtime context I receive in my build() and hud() calls."""

    # ---- Logos ecosystem ----
    config: dict             # logos.config (the live config/preferences dict)
    ns: dict                 # The shared REPL namespace (interpreter globals)

    # ---- ROS convenience ----
    tf_buffer: Any           # tf2_ros.Buffer for TF lookups
    robot_pose: Optional[dict]
    # {'x', 'y', 'z', 'yaw', 'roll', 'pitch'} in map frame, or None

    # ---- Chora-specific ----
    map_snapshot: Optional[MapSnapshot]  # Current frozen map for this render
    world_frame: str                     # Active world frame ("map" / "odom" / "")

    # ---- Instance metadata ----
    instance_name: str       # My name from mind_palace.yaml
    instance_config: dict    # My full entry from mind_palace.yaml
```

### Why `ns` (the REPL namespace)?

The AI's Python interpreter shares globals across the session. A phantasma can
read variables the AI set during cognition — for example, if the AI stored
`last_known_keys_position` in the REPL, a "find my keys" phantasma can read it
directly from `ctx.ns`. This is the deepest level of integration: the AI's
thoughts (as Python state) directly shape what appears in the rendered world.

---