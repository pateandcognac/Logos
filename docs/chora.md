# Chora And Phantasmata

Chora is Logos's virtual spatial scene: a third-person, raycastable Open3D view
of the robot, the ROS map, live depth context, and scriptable virtual objects.

## What Chora Does

`logos.map3d` renders a virtual camera view that Logos can inspect visually.
That render can include:

- the robot's self model;
- the floor/map plane;
- occupied, free, and unknown map areas;
- the Astra RGB-D point cloud;
- laser scan context;
- phantasmata placed into the scene.

The key bridge is raycasting: Logos can point at pixels in a render and convert
them back into world coordinates. This makes Chora a practical interface for
spatial reasoning and navigation goal selection.

## Open3D Constraints

This project is pinned to Open3D 0.13.0.

Important local lessons:

- `OffscreenRenderer` is thread-affine.
- `LineSet` does not render correctly in this path.
- Thin `TriangleMesh` boxes are used for line-like geometry.
- Offscreen renderer code uses `rendering.Material`, not newer material APIs.

## Phantasmata

Phantasmata are Python modules in `src/logos/phantasmata/`. Each module defines
virtual geometry or HUD overlays that can be placed in the mind palace.

Typical module surface:

- `SCHEMA`: parameter schema for configuration.
- `build(params, ctx)`: returns scene geometry or `None`.
- optional `DYNAMIC`, `hud(params, ctx)`, `should_rebuild(params, ctx)`, and
  `cleanup(ctx)`.

Instances are configured in `hypomnemata/chora/mind_palace_00.yaml` or similar. The helper
conventions live in `src/logos/phantasmata/phantasma_convention.py`.

## Waypoints

My waypoints are first-class spatial records in
`hypomnemata/chora/waypoints_00.yaml`, not separate mind-palace instances. The
single `nav_waypoints` phantasma renders the enabled records as a layer, while
`logos.waypoints` provides the same validated records to navigation:

```python
logos.waypoints.list()
logos.waypoints.get("front_door")
logos.waypoints.reload()
logos.waypoints.upsert_here(
    "reading_spot",
    name="Reading Spot",
    description="A comfortable map pose by the chair",
    navigable=True,
    emoji="📚",
)
logos.waypoints.update("reading_spot", theta_deg=90.0)
logos.waypoints.remove("reading_spot")
logos.waypoints.go_to("front_door", wait=False)
```

Waypoint IDs are stable YAML mapping keys. Each record contains a map-frame
position and degree-based RPY pose, a short name, description, UTC creation
timestamp, and an explicit `navigable` safety flag. Optional emoji, tags,
render overrides, and free-form metadata add semantics without changing the
pose contract.

Maintenance writes are validated and atomically replace the YAML file.
`upsert()` accepts canonical Chora poses, flat `x/y/theta_deg`, coordinate
sequences, and ROS-style Pose, PoseStamped, Odometry, Transform, or Pose2D
objects and dictionaries. Quaternion orientations are converted to degree
RPY. `upsert_here()` captures the current map pose; new records default to
`navigable=False`. Inputs that explicitly declare a non-map frame are rejected.

The renderer supports `floor`, `pose_billboard`, `camera_billboard`, and
`marker` modes. A `pin` or RGB `axes` marker and a stored-yaw heading arrow can
be enabled independently. Camera-facing emoji rotate only around world Z; the
heading geometry always stays fixed to the stored pose.

OpenMoji assets come from the configured shared directory. Unicode emoji are
resolved to uppercase codepoint filenames, with an explicit `render.emoji_file`
override for unusual assets. Missing images degrade to pose geometry instead
of hiding the waypoint.

## Relationship To Runtime

Chora is not just documentation. It is a live part of Logos's proprioception and
spatial imagination. Human readers should treat the code here as both geometry
and self-description.
