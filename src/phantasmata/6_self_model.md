### 6.1 Purpose

`self_model.py` replaces `logos_mesh.py`. It is both:

1. **A functional 3D model** of Logos for rendering and raycasting
2. **A prompt-engineering artifact** — written in first person, demonstrating
   API usage, sensor reading, state inspection, and HUD contribution

The self-model is special-cased in chora: it always exists, always follows the
robot's TF pose, and is managed separately from mind_palace.yaml instances.
But it follows the same `SCHEMA`/`build()`/`hud()` convention.

There is an existing, static MVP in place. Iteration and improvement upon it
will require working interactively with the user.

### 6.2 Design

```python
# src/logos/self_model.py
"""
I am Logos. This is my physical self-model.

This module constructs a 3D mesh representation of my body: a Turtlebot2-like
base with my Astra depth camera, pan-tilt unit, and other mounted hardware.

Beyond geometry, I use this as a living reference for how to read my own state.
My build() demonstrates reading sensor topics, battery level, joint positions,
and other introspectable states — both for rendering and as inline examples of
API usage patterns.

I also contribute HUD elements showing my current state at a glance.

Note to self:
    This file doubles as documentation. When I read my own source, I'm reading
    a description of my physical form AND examples of how to interact with it.
    Comments here are first-person usage notes, not third-person documentation.
"""

SCHEMA = {
    # ---- Geometry toggles ----
    'show_base':        {'type': 'bool', 'default': True,
                         'description': 'My cylindrical base body'},
    'show_astra':       {'type': 'bool', 'default': True,
                         'description': 'My Astra depth camera'},
    'show_pan_tilt':    {'type': 'bool', 'default': True,
                         'description': 'My pan-tilt webcam mount'},
    # ---- Augmentation toggles ----
    'show_astra_frustum':   {'type': 'bool', 'default': False,
                             'description': 'Astra depth camera view frustum'},
    'show_pantilt_frustum': {'type': 'bool', 'default': False,
                             'description': 'Pan-tilt webcam view frustum'},
    'show_heading_arrow':   {'type': 'bool', 'default': True,
                             'description': 'Forward-facing direction arrow'},
    # ---- Style ----
    'base_color':       {'type': 'rgb', 'default': [0.15, 0.15, 0.15],
                         'description': 'Body color'},
    'frustum_alpha':    {'type': 'float', 'default': 0.15, 'range': [0.0, 1.0],
                         'description': 'Frustum transparency'},
}

# I'm dynamic because my pan-tilt position changes and I want to
# show current joint state, but I use should_rebuild() to avoid
# rebuilding when nothing has actually changed.
DYNAMIC = True

def should_rebuild(params, ctx):
    """I only rebuild when my joint positions have changed meaningfully."""
    # Here's how I read my pan-tilt joint state:
    try:
        current_pan = logos.ros.get_joint_position('pan')
        current_tilt = logos.ros.get_joint_position('tilt')
    except Exception:
        return False
    # ... compare to last known, return True if changed ...

def build(params, ctx):
    """
    Construct my 3D body.

    I build geometry at the origin — chora applies my TF-derived pose after.
    """
    parts = []

    if params['show_base']:
        # My base is a Turtlebot2-style cylinder, ~35cm diameter, ~40cm tall
        base = _build_base_cylinder(params['base_color'])
        parts.append(base)

    if params['show_astra'] or params.get('show_astra_frustum'):
        # Here's how I read my Astra camera intrinsics for frustum geometry:
        # info = logos.ros.get_camera_info('/camera/rgb/camera_info')
        # fx, fy = info.K[0], info.K[4]
        # To set my pan-tilt position I'd use logos.actuators.set_pan_tilt(pan, tilt)
        ...

    if params['show_astra_frustum']:
        # I visualize my Astra's FOV as a semi-transparent pyramid
        # The frustum mesh needs to be in base_link frame (chora handles the rest)
        # I'm using thin box meshes for edges since Open3D 0.13 LineSet doesn't
        # render in OffscreenRenderer — this is a known 0.13 gotcha.
        ...

    # ... assemble into single TriangleMesh ...
    return SceneObject(name='self', kind='mesh', geometry=combined_mesh)

def hud(params, ctx):
    """
    My at-a-glance status HUD.

    Note to self:
        I show my battery, WiFi signal, AMCL confidence, and any active
        warnings. These are always-on system indicators.
    """
    elements = []
    # Here's how I read my battery level:
    # battery_pct = logos.ros.get_battery_level()
    # Here's how I check my localization confidence:
    # amcl = logos.ros.get_amcl_confidence()
    ...
    return elements
```

### 6.3 Prompt Engineering Value

The self-model serves multiple purposes simultaneously:

1. **First-person description of physical form** — replaces (or supplements)
   verbal system prompt descriptions of the robot's body
2. **API usage examples** — comments like `# Here's how I read my pan-tilt
   state: logos.ros.get_joint_position('pan')` are inline documentation that
   the AI reads naturally when inspecting its own code
3. **Phantasmata system example** — demonstrates SCHEMA, DYNAMIC, conditional
   rebuild, HUD contributions, Open3D mesh construction, and the gotchas
4. **Selective feature toggling** — demonstrates how to disable parts of a
   phantasma via params (e.g., `show_astra_frustum: false`)
5. **Sensor state annotation** — even simple sensor blocks can read and display
   current readings, demonstrating the read path
