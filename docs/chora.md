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

Instances are configured in `hypomnemata/chora/mind_palace_00.yaml`. The helper
conventions live in `src/logos/phantasmata/phantasma_convention.py`.

## Relationship To Runtime

Chora is not just documentation. It is a live part of Logos's proprioception and
spatial imagination. Human readers should treat the code here as both geometry
and self-description.
