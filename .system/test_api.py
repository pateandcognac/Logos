<py>
# ─── Logos API Integration Test ───────────────────────────────────────
# Run this in a <py> block or as a standalone script.
# Tests: utils, leds, pantilt, vision (all cameras), pose
#
# Mark: Fire up navigation mid-test to verify pose fallback behavior.
# The script pauses at that point and waits for you.

import time
import numpy as np

results = {"passed": 0, "failed": 0, "skipped": 0}


def test(name, fn):
    """Run a test, catch exceptions, tally results."""
    try:
        fn()
        results["passed"] += 1
        print(f"  ✓ {name}")
    except AssertionError as e:
        results["failed"] += 1
        print(f"  ✗ {name}: {e}")
    except Exception as e:
        results["failed"] += 1
        print(f"  ✗ {name}: {type(e).__name__}: {e}")


def skip(name, reason):
    results["skipped"] += 1
    print(f"  ⊘ {name}: SKIPPED ({reason})")


# ═══════════════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("  LOGOS API INTEGRATION TEST")
print("=" * 60)


# ─── 1. UTILS ─────────────────────────────────────────────────────────
print("\n── utils ──")

def test_base36_basic():
    assert logos.utils.base36_encode(0, 4) == "0000"
    assert logos.utils.base36_encode(35, 1) == "z"
    assert logos.utils.base36_encode(36, 2) == "10"
    assert logos.utils.base36_encode(1296, 4) == "0100"  # 36^2
test("base36_encode basics", test_base36_basic)

def test_base36_padding():
    result = logos.utils.base36_encode(1, 6)
    assert len(result) == 6, f"Expected length 6, got {len(result)}: '{result}'"
    assert result == "000001"
test("base36_encode padding", test_base36_padding)

def test_base36_negative():
    try:
        logos.utils.base36_encode(-1)
        assert False, "Should have raised ValueError"
    except ValueError:
        pass
test("base36_encode rejects negatives", test_base36_negative)

def test_photo_id_format():
    pid = logos.utils.make_photo_id()
    assert len(pid) == 7, f"Expected 7 chars, got {len(pid)}: '{pid}'"
    assert all(c in logos.utils.ALPHABET for c in pid), f"Non-base36 chars in '{pid}'"
test("make_photo_id format", test_photo_id_format)

def test_photo_id_uniqueness():
    ids = [logos.utils.make_photo_id() for _ in range(5)]
    assert len(set(ids)) == len(ids), f"Duplicate IDs in burst: {ids}"
test("make_photo_id burst uniqueness", test_photo_id_uniqueness)

def test_photo_id_sortable():
    from datetime import datetime, timezone, timedelta
    t1 = datetime(2025, 6, 1, tzinfo=timezone.utc)
    t2 = t1 + timedelta(seconds=100)
    # Reset sequence state between calls with different times
    logos.utils._last_second = None
    id1 = logos.utils.make_photo_id(t1)
    logos.utils._last_second = None
    id2 = logos.utils.make_photo_id(t2)
    assert id1 < id2, f"IDs not chronologically sortable: '{id1}' >= '{id2}'"
test("make_photo_id chronological sort", test_photo_id_sortable)


# ─── 2. LEDS ──────────────────────────────────────────────────────────
print("\n── leds ──")

def test_color_normalize_int():
    assert logos.leds._normalize_color(0xFF0000) == 0xFF0000
    assert logos.leds._normalize_color(0x000000) == 0x000000
test("color normalize: int", test_color_normalize_int)

def test_color_normalize_tuple():
    assert logos.leds._normalize_color((255, 0, 0)) == 0xFF0000
    assert logos.leds._normalize_color((0, 255, 128)) == 0x00FF80
test("color normalize: tuple", test_color_normalize_tuple)

def test_color_normalize_named():
    assert logos.leds._normalize_color("red") == 0xFF0000
    assert logos.leds._normalize_color("off") == 0x000000
    assert logos.leds._normalize_color("White") == 0xFFFFFF
test("color normalize: named strings", test_color_normalize_named)

def test_color_normalize_hex_string():
    assert logos.leds._normalize_color("#FF8000") == 0xFF8000
    assert logos.leds._normalize_color("00ff00") == 0x00FF00
test("color normalize: hex strings", test_color_normalize_hex_string)

def test_color_normalize_clamp():
    result = logos.leds._normalize_color((300, -10, 128))
    assert result == logos.leds._normalize_color((255, 0, 128))
test("color normalize: tuple clamping", test_color_normalize_clamp)

def test_color_bad_input():
    try:
        logos.leds._normalize_color("chartreuse_sunset")
        assert False, "Should have raised ValueError"
    except ValueError:
        pass
test("color normalize: rejects unknown name", test_color_bad_input)

def test_pack_led():
    packed = logos.leds._pack_led(3, 0xFF0000)
    assert packed == (3 << 24) | 0xFF0000
test("LED pack protocol", test_pack_led)

# Live LED tests — visual confirmation needed
print("\n  Live LED tests (watch the robot!):")

def test_fill_face():
    logos.leds.fill("face", "blue", verbosity=logos.Verbosity.SILENT)
    time.sleep(0.5)
    logos.leds.off("face", verbosity=logos.Verbosity.SILENT)
test("fill face blue (flash)", test_fill_face)

def test_fill_notification():
    logos.leds.fill("notification", "green", verbosity=logos.Verbosity.SILENT)
    time.sleep(0.5)
    logos.leds.off("notification", verbosity=logos.Verbosity.SILENT)
test("fill notification green (flash)", test_fill_notification)

def test_fill_pantilt_leds():
    logos.leds.fill("pan_tilt", "warm", verbosity=logos.Verbosity.SILENT)
    time.sleep(0.5)
    logos.leds.off("pan_tilt", verbosity=logos.Verbosity.SILENT)
test("fill pan_tilt warm (flash)", test_fill_pantilt_leds)

def test_set_individual():
    colors = ["red", "green", "blue", "yellow", "cyan"]
    logos.leds.set("pan_tilt", colors, verbosity=logos.Verbosity.SILENT)
    time.sleep(0.8)
    logos.leds.off("pan_tilt", verbosity=logos.Verbosity.SILENT)
test("set individual pan_tilt LEDs", test_set_individual)

def test_set_too_many():
    try:
        logos.leds.set("pan_tilt", ["red"] * 20, verbosity=logos.Verbosity.SILENT)
        assert False, "Should have raised ValueError"
    except ValueError:
        pass
test("set rejects too many LEDs", test_set_too_many)

def test_laser_on_off():
    logos.leds.laser(1.0, verbosity=logos.Verbosity.SILENT)
    time.sleep(0.5)
    logos.leds.laser(0.0, verbosity=logos.Verbosity.SILENT)
test("laser on/off", test_laser_on_off)

def test_laser_half():
    logos.leds.laser(0.5, verbosity=logos.Verbosity.SILENT)
    time.sleep(0.3)
    logos.leds.laser(0.0, verbosity=logos.Verbosity.SILENT)
test("laser half brightness", test_laser_half)

def test_laser_clamp():
    logos.leds.laser(5.0, verbosity=logos.Verbosity.SILENT)
    time.sleep(0.2)
    logos.leds.laser(-1.0, verbosity=logos.Verbosity.SILENT)
test("laser clamp out-of-range", test_laser_clamp)

def test_all_off():
    logos.leds.fill("face", "white", verbosity=logos.Verbosity.SILENT)
    logos.leds.fill("notification", "white", verbosity=logos.Verbosity.SILENT)
    logos.leds.fill("pan_tilt", "white", verbosity=logos.Verbosity.SILENT)
    logos.leds.laser(1.0, verbosity=logos.Verbosity.SILENT)
    time.sleep(0.5)
    logos.leds.off(verbosity=logos.Verbosity.SILENT)  # should kill everything
test("off() kills all strips + laser", test_all_off)


# ─── 3. PAN/TILT ─────────────────────────────────────────────────────
print("\n── pantilt ──")

def test_deg_to_counts():
    # 0 degrees should map to home (400)
    assert logos.pantilt._deg_to_counts(0.0, 400) == 400
    # Positive degrees -> lower servo count (flipped mapping)
    assert logos.pantilt._deg_to_counts(10.0, 400) == 375  # 400 - 10*2.5
    # Negative degrees -> higher servo count
    assert logos.pantilt._deg_to_counts(-10.0, 400) == 425  # 400 + 10*2.5
test("deg_to_counts conversion", test_deg_to_counts)

def test_counts_to_deg():
    assert logos.pantilt._counts_to_deg(400, 400) == 0.0
    assert logos.pantilt._counts_to_deg(375, 400) == 10.0
    assert logos.pantilt._counts_to_deg(425, 400) == -10.0
test("counts_to_deg conversion", test_counts_to_deg)

def test_roundtrip_conversion():
    for deg in [-80, -45, -10, 0, 10, 45, 70, 100]:
        counts = logos.pantilt._deg_to_counts(float(deg), 400)
        back = logos.pantilt._counts_to_deg(counts, 400)
        assert abs(back - deg) < 0.5, f"Roundtrip failed for {deg}: got {back}"
test("deg/counts roundtrip", test_roundtrip_conversion)

def test_clamp():
    p, t = logos.pantilt._clamp_deg(200.0, 200.0)
    assert p == 100.0 and t == 70.0, f"Upper clamp failed: ({p}, {t})"
    p, t = logos.pantilt._clamp_deg(-200.0, -200.0)
    assert p == -80.0 and t == -60.0, f"Lower clamp failed: ({p}, {t})"
test("clamp to physical limits", test_clamp)

# Live pan/tilt tests
print("\n  Live pan/tilt tests (watch the head!):")

def test_home():
    logos.pantilt.home(verbosity=logos.Verbosity.SILENT)
    time.sleep(1.0)
    pan, tilt = logos.pantilt.get_position()
    # Allow some tolerance for servo feedback jitter
    assert abs(pan) < 5.0, f"Pan not near home: {pan}"
    assert abs(tilt) < 5.0, f"Tilt not near home: {tilt}"
test("home position", test_home)

def test_move_right():
    logos.pantilt.move(45.0, 0.0, verbosity=logos.Verbosity.SILENT)
    time.sleep(1.0)
    pan, tilt = logos.pantilt.get_position()
    assert abs(pan - 45.0) < 5.0, f"Expected pan ~45, got {pan}"
test("move: pan right 45°", test_move_right)

def test_move_left_up():
    logos.pantilt.move(-40.0, 30.0, verbosity=logos.Verbosity.SILENT)
    time.sleep(1.0)
    pan, tilt = logos.pantilt.get_position()
    assert abs(pan - (-40.0)) < 5.0, f"Expected pan ~-40, got {pan}"
    assert abs(tilt - 30.0) < 5.0, f"Expected tilt ~30, got {tilt}"
test("move: pan left 40°, tilt up 30°", test_move_left_up)

def test_nudge():
    logos.pantilt.move(0.0, 0.0, verbosity=logos.Verbosity.SILENT)
    time.sleep(0.8)
    logos.pantilt.nudge(10.0, 5.0, verbosity=logos.Verbosity.SILENT)
    time.sleep(0.8)
    pan, tilt = logos.pantilt.get_position()
    assert abs(pan - 10.0) < 5.0, f"Expected pan ~10 after nudge, got {pan}"
    assert abs(tilt - 5.0) < 5.0, f"Expected tilt ~5 after nudge, got {tilt}"
test("nudge from home", test_nudge)

def test_move_clamped():
    actual = logos.pantilt.move(999.0, -999.0, verbosity=logos.Verbosity.SILENT)
    assert actual == (100.0, -60.0), f"Clamped return mismatch: {actual}"
    time.sleep(0.8)
test("move clamps to limits", test_move_clamped)

# Return home for next tests
logos.pantilt.home(verbosity=logos.Verbosity.SILENT)
time.sleep(1.0)


# ─── 4. VISION: WEBCAMS ──────────────────────────────────────────────
print("\n── vision: webcams ──")

def test_capture_top_down():
    result = logos.vision.capture("top_down", verbosity=logos.Verbosity.SILENT)
    assert result is not None, "capture returned None"
    assert result.source == "top_down"
    assert isinstance(result.image, np.ndarray)
    assert result.image.ndim == 3, f"Expected 3D array, got {result.image.ndim}D"
    h, w = result.resolution
    assert (w, h) == (640, 480), f"Expected 640x480, got {w}x{h}"
    assert result.depth is None, "top_down shouldn't have depth"
    assert result.pan_tilt_degs is None, "top_down shouldn't have pan_tilt_degs"
test("capture top_down (default res)", test_capture_top_down)

def test_capture_pan_tilt():
    result = logos.vision.capture("pan_tilt", verbosity=logos.Verbosity.SILENT)
    assert result is not None, "capture returned None"
    assert result.source == "pan_tilt"
    h, w = result.resolution
    assert (w, h) == (1280, 960), f"Expected 1280x960, got {w}x{h}"
    assert result.pan_tilt_degs is not None, "pan_tilt should have pan_tilt_degs"
test("capture pan_tilt (default res)", test_capture_pan_tilt)

def test_capture_pan_tilt_high_res():
    result = logos.vision.capture(
        "pan_tilt", resolution=(2592, 1944),
        verbosity=logos.Verbosity.SILENT,
    )
    assert result is not None
    h, w = result.resolution
    assert (w, h) == (2592, 1944), f"Expected 2592x1944, got {w}x{h}"
test("capture pan_tilt (high res)", test_capture_pan_tilt_high_res)

def test_capture_pan_tilt_custom_res():
    result = logos.vision.capture(
        "pan_tilt", resolution=(800, 600),
        verbosity=logos.Verbosity.SILENT,
    )
    assert result is not None
    h, w = result.resolution
    assert (w, h) == (800, 600), f"Expected 800x600, got {w}x{h}"
test("capture pan_tilt (custom 800x600, downscaled from standard tier)", test_capture_pan_tilt_custom_res)

def test_capture_flip_check():
    """Capture from pan_tilt — can't verify flip programmatically, but confirm no crash."""
    result = logos.vision.capture("pan_tilt", verbosity=logos.Verbosity.SILENT)
    assert result is not None
    assert result.image.shape[2] == 3, "Expected BGR 3-channel image"
test("capture pan_tilt flip (no crash)", test_capture_flip_check)

def test_warm_capture_speed():
    """Second capture should be fast (camera already warm)."""
    # First capture warms the camera
    logos.vision.capture("top_down", verbosity=logos.Verbosity.SILENT)
    # Second should be near-instant
    t0 = time.time()
    result = logos.vision.capture("top_down", verbosity=logos.Verbosity.SILENT)
    elapsed = time.time() - t0
    assert result is not None
    assert elapsed < 1.0, f"Warm capture took {elapsed:.2f}s (expected < 1.0s)"
test("warm capture is fast (< 1s)", test_warm_capture_speed)

def test_bad_source():
    try:
        logos.vision.capture("nonexistent", verbosity=logos.Verbosity.SILENT)
        assert False, "Should have raised ValueError"
    except ValueError:
        pass
test("bad source raises ValueError", test_bad_source)


# ─── 5. VISION: SAVE / VIEW / CROP / META ────────────────────────────
print("\n── vision: artifacts ──")

def test_save_jpg():
    from pathlib import Path
    result = logos.vision.capture("pan_tilt", verbosity=logos.Verbosity.SILENT)
    path = result.save()
    assert path is not None
    assert path.endswith(".jpg"), f"Expected .jpg, got {path}"
    assert Path(path).exists(), f"File not found: {path}"
    assert result.photo_id is not None
    assert len(result.photo_id) == 7
    # Check sidecar
    meta_path = Path(path).with_suffix(".yaml")
    assert meta_path.exists(), f"Sidecar not found: {meta_path}"
test("save webcam as JPG + sidecar", test_save_jpg)

def test_save_view():
    """save(view=True) should print a <file> tag."""
    import io, sys
    result = logos.vision.capture("top_down", verbosity=logos.Verbosity.SILENT)
    old_stdout = sys.stdout
    sys.stdout = capture_out = io.StringIO()
    result.save(view=True)
    sys.stdout = old_stdout
    output = capture_out.getvalue()
    assert "<file path=" in output, f"Expected <file> tag, got: {output}"
test("save(view=True) prints <file> tag", test_save_view)

def test_crop():
    result = logos.vision.capture("pan_tilt", verbosity=logos.Verbosity.SILENT)
    cropped = result.crop([250, 250, 750, 750])  # center-ish crop
    assert isinstance(cropped, np.ndarray)
    h, w = cropped.shape[:2]
    orig_h, orig_w = result.resolution
    # Crop should be roughly half the image each dimension
    assert 0.3 < (h / orig_h) < 0.7, f"Crop height ratio unexpected: {h}/{orig_h}"
    assert 0.3 < (w / orig_w) < 0.7, f"Crop width ratio unexpected: {w}/{orig_w}"
test("crop with normalized coords", test_crop)

def test_crop_standalone():
    """Test the module-level crop() with a raw ndarray."""
    img = np.zeros((480, 640, 3), dtype=np.uint8)
    cropped = logos.vision.crop(img, [0, 0, 500, 500])
    assert cropped.shape[0] == 240  # 500/1000 * 480
    assert cropped.shape[1] == 320  # 500/1000 * 640
test("crop standalone (raw ndarray)", test_crop_standalone)

def test_crop_edge_cases():
    img = np.zeros((100, 100, 3), dtype=np.uint8)
    # Full image
    c1 = logos.vision.crop(img, [0, 0, 1000, 1000])
    assert c1.shape[:2] == (100, 100)
    # Tiny region
    c2 = logos.vision.crop(img, [0, 0, 10, 10])
    assert c2.shape[0] >= 1 and c2.shape[1] >= 1
test("crop edge cases", test_crop_edge_cases)

def test_add_meta():
    from pathlib import Path
    from ruamel.yaml import YAML
    result = logos.vision.capture("pan_tilt", verbosity=logos.Verbosity.SILENT)
    result.save()
    result.add_meta(
        caption="Test caption for integration test",
        detections=[{"box_2d": [100, 200, 300, 400], "label": "test_object"}],
        notes="This was added by add_meta()",
    )
    meta_path = Path(result.path).with_suffix(".yaml")
    yaml = YAML()
    with meta_path.open("r") as f:
        meta = yaml.load(f)
    assert "caption" in meta, f"caption not in sidecar: {list(meta.keys())}"
    assert "detections" in meta
    assert meta["notes"] == "This was added by add_meta()"
test("add_meta persists to sidecar YAML", test_add_meta)

def test_repr():
    result = logos.vision.capture("pan_tilt", verbosity=logos.Verbosity.SILENT)
    r = repr(result)
    assert "pan_tilt" in r
    assert "1280x960" in r or "960" in r
test("CaptureResult repr", test_repr)


# ─── 6. VISION: ASTRA ────────────────────────────────────────────────
print("\n── vision: astra ──")

def test_astra_rgb_only():
    result = logos.vision.capture(
        "astra", astra_feeds=("rgb",),
        verbosity=logos.Verbosity.SILENT,
    )
    assert result is not None, "Astra RGB capture returned None"
    assert result.source == "astra"
    assert isinstance(result.image, np.ndarray)
    assert result.depth is None, "rgb-only capture shouldn't have depth"
    assert result.depth_points is None, "rgb-only capture shouldn't have depth_points"
test("astra: RGB only", test_astra_rgb_only)

def test_astra_with_depth():
    result = logos.vision.capture(
        "astra", astra_feeds=("rgb", "depth"),
        verbosity=logos.Verbosity.SILENT,
    )
    assert result is not None
    assert result.depth is not None, "Expected depth data"
    assert result.depth.dtype == np.uint16 or result.depth.ndim == 2, \
        f"Unexpected depth format: dtype={result.depth.dtype}, ndim={result.depth.ndim}"
test("astra: RGB + depth", test_astra_with_depth)

def test_astra_with_depth_registered():
    result = logos.vision.capture(
        "astra", astra_feeds=("rgb", "depth_registered"),
        verbosity=logos.Verbosity.SILENT,
    )
    assert result is not None
    assert result.depth_points is not None, "Expected depth_points (HxWx3 array)"
    assert result.depth_points.ndim == 3, f"Expected 3D, got {result.depth_points.ndim}D"
    assert result.depth_points.shape[2] == 3, f"Expected 3 channels (XYZ), got {result.depth_points.shape[2]}"
    assert result.depth_points_msg is not None, "Expected raw PointCloud2 message"
test("astra: RGB + depth_registered (point cloud)", test_astra_with_depth_registered)

def test_astra_pixel_to_3d():
    result = logos.vision.capture(
        "astra", astra_feeds=("rgb", "depth_registered"),
        verbosity=logos.Verbosity.SILENT,
    )
    assert result is not None and result.depth_points is not None

    # Test center pixel — should have valid depth if pointing at something
    # point = result.pixel_to_3d(500, 500)

    # Sample over a 10x10 grid of pixels dispersed across the frame and average values if not NaN. If all NaN, return None.
    points = []
    for x in range(100, 901, 80):
        for y in range(100, 901, 80):
            p = result.pixel_to_3d(x, y)
            if p is not None and not np.isnan(p).any():
                points.append(p)
    if points:
        point = np.nanmean(points, axis=0)
    else:
        point = None

    if point is not None:
        x, y, z = point
        assert isinstance(x, float)
        # z should be positive (in front of camera) and reasonable (< 10m)
        assert 0.0 < z < 10.0, f"Center z={z} seems unreasonable"
        print(f"    Center pixel 3D: ({x:.2f}, {y:.2f}, {z:.2f})m")
    else:
        print("    Center pixel has no valid depth (NaN) — might be pointed at infinity")

    # Test a corner — more likely to be NaN (out of range)
    corner = result.pixel_to_3d(0, 0)
    print(f"    Corner pixel 3D: {corner}")
test("astra: pixel_to_3d projection", test_astra_pixel_to_3d)

def test_astra_camera_info():
    result = logos.vision.capture(
        "astra", astra_feeds=("rgb", "camera_info"),
        verbosity=logos.Verbosity.SILENT,
    )
    assert result is not None
    if result.camera_info is not None:
        ci = result.camera_info
        print(f"    Intrinsics: {ci.width}x{ci.height}, fx={ci.K[0]:.1f}, fy={ci.K[4]:.1f}")
    else:
        print("    camera_info returned None")
test("astra: camera_info intrinsics", test_astra_camera_info)

def test_astra_save_png():
    from pathlib import Path
    result = logos.vision.capture("astra", verbosity=logos.Verbosity.SILENT)
    path = result.save()
    assert path.endswith(".png"), f"Expected .png for astra, got {path}"
    assert Path(path).exists()
test("astra: save as PNG", test_astra_save_png)

def test_astra_save_depth_png():
    from pathlib import Path
    result = logos.vision.capture(
        "astra", astra_feeds=("rgb", "depth"),
        verbosity=logos.Verbosity.SILENT,
    )
    path = result.save()
    depth_path = Path(path).with_name(result.photo_id + "_depth.png")
    assert depth_path.exists(), f"Depth PNG not found: {depth_path}"
    print(f"    Depth saved to: {depth_path}")
test("astra: depth saved as 16-bit PNG", test_astra_save_depth_png)

def test_astra_all_feeds():
    result = logos.vision.capture(
        "astra", astra_feeds=("rgb", "depth", "depth_registered", "camera_info"),
        verbosity=logos.Verbosity.SILENT,
    )
    assert result is not None
    report = []
    report.append(f"rgb: {result.image.shape}")
    report.append(f"depth: {'yes ' + str(result.depth.shape) if result.depth is not None else 'None'}")
    report.append(f"depth_points: {'yes ' + str(result.depth_points.shape) if result.depth_points is not None else 'None'}")
    # report.append(f"ir: {'yes ' + str(result.ir.shape) if result.ir is not None else 'None'}")
    report.append(f"camera_info: {'yes' if result.camera_info is not None else 'None'}")
    print(f"    All feeds: {', '.join(report)}")
test("astra: capture all feeds simultaneously", test_astra_all_feeds)


# ─── 7. VISION: WARM-UP / KEEP-ALIVE / RELEASE ───────────────────────
print("\n── vision: lifecycle ──")

def test_warm_up():
    logos.vision.release("top_down", verbosity=logos.Verbosity.SILENT)
    time.sleep(0.5)
    logos.vision.warm_up("top_down", verbosity=logos.Verbosity.SILENT)
    # Should be warm now — capture should be fast
    t0 = time.time()
    result = logos.vision.capture("top_down", verbosity=logos.Verbosity.SILENT)
    elapsed = time.time() - t0
    assert result is not None
    assert elapsed < 0.5, f"Capture after warm_up took {elapsed:.2f}s (expected < 0.5s)"
test("warm_up() pre-warms for fast capture", test_warm_up)

def test_release():
    logos.vision.capture("top_down", verbosity=logos.Verbosity.SILENT)
    logos.vision.release("top_down", verbosity=logos.Verbosity.SILENT)
    # Manager should be deactivated
    mgr = logos.vision._managers.get("top_down")
    assert mgr is not None, "Manager should still exist"
    assert not mgr._active, "Manager should be inactive after release"
test("release() deactivates camera", test_release)

def test_release_all():
    logos.vision.capture("pan_tilt", verbosity=logos.Verbosity.SILENT)
    logos.vision.capture("top_down", verbosity=logos.Verbosity.SILENT)
    logos.vision.release(verbosity=logos.Verbosity.SILENT)
    for name, mgr in logos.vision._managers.items():
        assert not mgr._active, f"{name} still active after release_all"
test("release(None) deactivates all cameras", test_release_all)


# ─── 8. POSE ─────────────────────────────────────────────────────────
print("\n── pose ──")
print("  (Test this section both WITH and WITHOUT navigation running)")

def test_pose_structure():
    pose = logos.vision._get_pose()
    if pose is not None:
        assert "x" in pose and "y" in pose and "theta" in pose, \
            f"Pose missing keys: {pose}"
        print(f"    Pose: x={pose['x']:.2f}, y={pose['y']:.2f}, θ={pose['theta']:.2f}")
    else:
        print("    Pose: None (no TF available — is nav running?)")
test("pose from TF", test_pose_structure)

def test_pose_in_capture():
    result = logos.vision.capture("pan_tilt", verbosity=logos.Verbosity.SILENT)
    if result.pose is not None:
        print(f"    Capture pose: x={result.pose['x']:.2f}, y={result.pose['y']:.2f}")
    else:
        print("    Capture pose: None (expected if nav not running)")
test("pose stamped in CaptureResult", test_pose_in_capture)


# ─── 9. CROSS-MODULE INTEGRATION ─────────────────────────────────────
print("\n── integration ──")

def test_capture_then_look():
    """Capture → detect (simulated center point) → look_at_pixel."""
    logos.pantilt.home(verbosity=logos.Verbosity.SILENT)
    time.sleep(0.8)
    result = logos.vision.capture("pan_tilt", verbosity=logos.Verbosity.SILENT)
    assert result is not None
    # Simulate a detection at upper-right area
    fake_detection = [250, 750]  # [y, x] normalized
    logos.pantilt.look_at_pixel(fake_detection, source="pan_tilt")
    time.sleep(1.0)
    pan, tilt = logos.pantilt.get_position()
    # Should have panned right and tilted up
    assert pan > 5.0, f"Expected positive pan (right), got {pan}"
    assert tilt > 2.0, f"Expected positive tilt (up), got {tilt}"
    print(f"    After looking at [250, 750]: pan={pan:.1f}°, tilt={tilt:.1f}°")
test("capture → look_at_pixel pipeline", test_capture_then_look)

def test_capture_save_annotate():
    """Full pipeline: capture → save → add detections → verify sidecar."""
    from pathlib import Path
    from ruamel.yaml import YAML
    result = logos.vision.capture("pan_tilt", verbosity=logos.Verbosity.SILENT)
    result.save()
    result.add_meta(
        caption="Integration test scene",
        detections=[
            {"box_2d": [100, 200, 400, 500], "label": "chair"},
            {"point": [300, 600], "label": "light_switch"},
        ],
    )
    meta_path = Path(result.path).with_suffix(".yaml")
    yaml = YAML()
    with meta_path.open() as f:
        meta = yaml.load(f)
    assert len(meta["detections"]) == 2
    assert meta["caption"] == "Integration test scene"
    assert meta["photo_id"] == result.photo_id
test("capture → save → annotate full pipeline", test_capture_save_annotate)

def test_led_feedback_on_capture():
    """Flash notification LEDs when capturing — demo of composable behavior."""
    logos.leds.fill("notification", "cyan", verbosity=logos.Verbosity.SILENT)
    result = logos.vision.capture("pan_tilt", verbosity=logos.Verbosity.SILENT)
    logos.leds.off("notification", verbosity=logos.Verbosity.SILENT)
    assert result is not None
test("LED feedback during capture (composability demo)", test_led_feedback_on_capture)


# Return home for clean state
logos.pantilt.home(verbosity=logos.Verbosity.SILENT)


# ─── RESULTS ──────────────────────────────────────────────────────────
print("\n" + "=" * 60)
total = results["passed"] + results["failed"] + results["skipped"]
print(f"  RESULTS: {results['passed']}/{total} passed, "
      f"{results['failed']} failed, {results['skipped']} skipped")
if results["failed"] == 0:
    print("  🎉 ALL TESTS PASSED!")
else:
    print("  ⚠️  Some tests failed — review output above.")
print("=" * 60 + "\n")

loop_cognition = False
</py>