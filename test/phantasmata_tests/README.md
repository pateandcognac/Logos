# Phantasmata Test Suite

Comprehensive tests for the Logos phantasmata system. These scripts demonstrate and verify the dynamic object system for Map3d (my mind palace renderer).

## Test Scripts

### 01_basic_phantasma_placement.py
**Basic lifecycle operations**

Tests fundamental instance management:
- Listing available phantasma modules
- Inspecting module schemas
- Placing instances
- Updating parameters
- Moving instances
- Toggling visibility
- Removing instances

**Run:** `python3 01_basic_phantasma_placement.py`

**Output:** Terminal output only (no files)

---

### 02_rendering_test.py
**Rendering pipeline verification**

Tests the render loop with phantasmata:
- Various camera positions and viewpoints
- Different resolutions
- HUD element composition
- Image file generation

**Run:** `python3 02_rendering_test.py`

**Output:** `renders/` directory with 6 PNG images

**Renders:**
1. Top-down view (5m height)
2. Ground-level perspective
3. Isometric view
4. With robot self-model
5. High resolution (1920×1080)
6. Complex multi-element HUD

---

### 03_comprehensive_demo.py
**Full system demonstration**

A complete showcase of the phantasmata system:
- Loading from `mind_palace.yaml`
- Programmatic instance creation
- Complex multi-object scenes
- Dynamic parameter updates
- Multi-viewpoint tour
- Scene cleanup

**Run:** `python3 03_comprehensive_demo.py`

**Output:** `demo_renders/` directory with 10 PNG images

**Scene composition:**
- Metric floor grid (from config)
- Navigation waypoint arrows
- Cardinal direction indicators
- 8-point circular search pattern
- Dynamic color-changing demonstration

**Views:**
1. Overhead (8m altitude)
2. Ground perspective
3. Northeast isometric
4. Close detail
5. West elevation
6. Robot POV
7-9. Dynamic update stages

---

## Running All Tests

```bash
# From the Logos workspace root:
cd test/phantasmata_tests

# Run individually
python3 01_basic_phantasma_placement.py
python3 02_rendering_test.py
python3 03_comprehensive_demo.py

# Or run all at once
python3 01_basic_phantasma_placement.py && \
python3 02_rendering_test.py && \
python3 03_comprehensive_demo.py
```

## Expected Output

```
test/phantasmata_tests/
├── 01_basic_phantasma_placement.py
├── 02_rendering_test.py
├── 03_comprehensive_demo.py
├── README.md
├── renders/                     (6 images from test 02)
│   ├── 01_top_down.png
│   ├── 02_ground_level.png
│   ├── 03_isometric.png
│   ├── 04_with_robot.png
│   ├── 05_high_res.png
│   └── 06_complex_hud.png
└── demo_renders/                (10 images from test 03)
    ├── 01_overview_high.png
    ├── 02_ground_perspective.png
    ├── 03_northeast_iso.png
    ├── 04_close_detail.png
    ├── 05_west_elevation.png
    ├── 06_robot_pov.png
    ├── 07_dynamic_red_forward.png
    ├── 07_dynamic_green_right.png
    └── 07_dynamic_blue_back.png
```

## What's Being Tested

### Phantasma Types Used
- **grid_overlay**: Metric floor grid for spatial reference
- **pointer_arrow**: 3D arrows for navigation and highlighting
- **self_model**: Robot self-representation (in test 02)

### System Components
- ✓ Module discovery and introspection
- ✓ Instance lifecycle (place, update, move, remove)
- ✓ SCHEMA validation and parameter merging
- ✓ Geometry building and caching
- ✓ Render loop integration
- ✓ HUD system extraction and composition
- ✓ Multi-viewpoint rendering
- ✓ Dynamic parameter updates

### Open3D 0.13 Compatibility
- ✓ Thin box meshes for lines (LineSet workaround)
- ✓ Correct transparency approach
- ✓ OffscreenRenderer thread affinity
- ✓ Material configuration

## Notes

All tests are written in first person (as Logos) with inline documentation showing typical API usage patterns. The code serves as both verification and example usage.

The tests assume:
- No ROS environment required
- No live robot/sensors needed
- Static geometry only (no live point clouds)
- Minimal dependencies (Open3D, numpy, opencv)

For tests requiring ROS (map snapshots, TF frames, live sensors), see the integration test suite.

---

**Author:** Logos (with Claude's help)
**Date:** 2026-02-28
**Phantasmata Version:** 1.0
