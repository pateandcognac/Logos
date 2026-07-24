# Chora Waypoint System MVP

## Summary

Create a first-class `logos.waypoints` registry backed by YAML, with one Chora phantasma rendering the registry as a layer. Waypoints remain independent of rendering so navigation and future semantic retrieval can reuse them.

Default appearance: camera-facing emoji above an exact floor pin, plus a stored-yaw heading arrow. Floor, pose-facing billboard, camera-facing billboard, and marker-only modes remain selectable per waypoint.

## Data and Public API

- Replace the existing waypoint sketch with a versioned `hypomnemata/chora/waypoints_00.yaml`:
  - Top-level `schema_version: 1`, `frame: map`, and `waypoints` mapping keyed by stable ID.
  - Required record fields: `name`, `description`, `pose.position`, `pose.rpy_deg`, `created_at`, and `navigable`.
  - Optional fields: `emoji`, `tags`, `enabled`, `render`, and unrestricted `metadata`.
  - `render` supports `mode`, `scale_m`, `icon_height_m`, `marker`, and `show_heading`.
  - Store timestamps as ISO-8601 UTC and all angles in degrees.
- Add configuration for the waypoint file and `~/robot_workspaces/shared/openmoji-72x72-color/`.
- Add `logos.waypoints` with:
  - `list(tags=None, navigable_only=False)`
  - `get(id_or_name)` using exact ID first, then unique case-insensitive short name
  - `reload()` performing transactional validation and returning the loaded count
  - `go_to(id_or_name, wait=False)` delegating to `logos.nav.go_to_abs()` with stored X, Y, and yaw
- Require `navigable: true` before `go_to()` accepts a waypoint. Do not add fuzzy lookup or YAML-writing CRUD in the MVP.
- Invalid reloads retain the last-known-good registry. Unknown schema fields are rejected except inside `metadata`.

## Chora Rendering

- Add one active `nav_waypoints` instance to the mind palace, rather than generating a phantasma instance for every record.
- Implement these modes:
  - `floor`: horizontal decal; image “up” follows stored yaw.
  - `pose_billboard`: upright, double-sided quad whose normal follows stored yaw.
  - `camera_billboard`: upright cylindrical billboard rotated toward each virtual camera.
  - `marker`: no image, only spatial pose geometry.
- Make `marker` independently selectable as `none`, `pin`, or `axes`; default to `pin`. Draw the heading arrow independently and enable it by default.
- Keep the waypoint layer non-raycastable so icons do not intercept floor targeting. IDs remain discoverable through `logos.waypoints`.
- Resolve readable Unicode emoji to OpenMoji filenames, with variation-selector fallback and an optional explicit filename override. Decode palette PNGs to RGBA with OpenCV and cache them by path/mtime.
- Missing images degrade to pin/heading geometry with a render warning.
- Suppress the layer with a warning when Chora’s active world frame is not `map`, preventing silently misplaced navigation markers.
- Extend the general Chora contracts:
  - `PhantasmaContext` receives virtual camera and look-at world positions plus a warning callback.
  - `SceneObject` can carry an albedo image, RGBA multiplier, and alpha flag.
  - The renderer constructs the corresponding Open3D 0.13 material on its dedicated render thread and preserves these fields through camera clipping.

## Validation

- Offline checks:
  - Python 3.8 compilation/imports.
  - YAML validation, duplicate/ambiguous names, malformed poses, missing assets, Unicode filename resolution, and transactional reload failure.
  - Geometry bounds/orientation for every render mode and multiple camera positions.
  - Mocked `go_to()` delegation, including refusal of non-navigable records.
  - `git diff --check`.
- Live Chora checks with Mark:
  - Confirm RGBA transparency and texture orientation under Open3D 0.13.
  - Render all four modes from overhead and third-person cameras.
  - Verify camera billboards rotate while stored heading arrows remain fixed.
  - Confirm waypoint markers do not block floor raycasts.
  - Test reload after manually editing YAML.
  - Perform real navigation only as an explicit, separately authorized safe-space test.

## Future-Compatible Boundary

- Preserve stable IDs, tags, source metadata, and navigability so RTAB-Map-derived observations can later coexist with curated navigation poses.
- Do not convert every RTAB pose directly into a navigable waypoint. A future pipeline should sample visually/spatially novel keyframes, caption and embed them, cluster place candidates, and require validation before setting `navigable: true`.
- Future fuzzy retrieval can rank by text/visual relevance, distance, and recency, then pass selected IDs to the same renderer without changing the YAML or rendering contracts.

## Assumptions

- Public API lives at `logos.waypoints`; Chora is a consumer.
- MVP includes exact query and explicit navigation-by-ID.
- Camera-facing emoji plus pin and heading is the default.
- The existing waypoint YAML contains no authoritative coordinates, so implementation leaves an empty registry with commented examples rather than inventing locations.
