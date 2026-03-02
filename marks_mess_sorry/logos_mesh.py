"""
logos.map3d.logos_mesh

Replacement robot mesh for Map3d — a stylized 3D representation of
the Logos robot built from Open3D primitives.

Standalone usage:
    from logos.map3d.logos_mesh import build_logos_mesh
    mesh = build_logos_mesh()

Drop-in for Map3d._create_robot_mesh():
    Replace the body of _create_robot_mesh() with the contents of
    the patched version at the bottom of this file.
"""

from __future__ import annotations

from typing import Optional

import numpy as np

try:
    import open3d as o3d
except ImportError:
    o3d = None


def _paint(mesh, rgb):
    """Paint mesh a uniform RGB color (0-1 floats)."""
    mesh.paint_uniform_color(rgb)
    return mesh


def _translate(mesh, xyz):
    """Translate mesh by [x, y, z]."""
    mesh.translate(xyz, relative=True)
    return mesh


def build_logos_mesh() -> "o3d.geometry.TriangleMesh":
    """
    Build a complete Logos robot mesh at the origin, facing +X (ROS forward).

    Proportions from photo reference (all meters):
    - Two-tier circular base: r=0.175 / r=0.155, total h~0.08
    - Central column: r=0.035, h~0.48
    - Chest orb: r=0.06 at z=0.35
    - Oval face display: ~0.30w x 0.38h, centered at z=0.78
    - Corrugated arms with cute yellow hands
    - Camera block on top with red LED
    - Mic boom on left side

    Returns the merged TriangleMesh, ready for transform into map frame.
    """
    if o3d is None:
        raise RuntimeError("Open3D is required to build the Logos mesh.")

    parts = []

    # ---- Kobuki! ----
    base_lower = o3d.geometry.TriangleMesh.create_cylinder(
        radius=0.15, height=0.07, resolution=32
    )
    _paint(base_lower, [0.85, 0.85, 0.82])
    _translate(base_lower, [0.0, 0.0, 0.02])
    parts.append(base_lower)

    base_upper = o3d.geometry.TriangleMesh.create_cylinder(
        radius=0.155, height=0.04, resolution=32
    )
    _paint(base_upper, [0.90, 0.90, 0.87])
    _translate(base_upper, [0.0, 0.0, 0.07])
    parts.append(base_upper)

    # Green LED accent on front of base
    led_base = o3d.geometry.TriangleMesh.create_box(
        width=0.04, height=0.03, depth=0.02
    )
    _paint(led_base, [0.1, 0.9, 0.3])
    _translate(led_base, [0.13, -0.015, 0.04])
    parts.append(led_base)

    # ---- Central column ----
    column = o3d.geometry.TriangleMesh.create_cylinder(
        radius=0.04, height=0.48, resolution=20
    )
    _paint(column, [0.88, 0.88, 0.85])
    _translate(column, [0.0, 0.0, 0.32])
    parts.append(column)

    # ---- Chest orb ----
    orb = o3d.geometry.TriangleMesh.create_sphere(radius=0.06, resolution=20)
    _paint(orb, [0.5, 0.85, 1.0])
    _translate(orb, [0.0, 0.0, 0.35])
    parts.append(orb)

    orb_ring = o3d.geometry.TriangleMesh.create_cylinder(
        radius=0.045, height=0.015, resolution=20
    )
    _paint(orb_ring, [0.80, 0.80, 0.78])
    _translate(orb_ring, [0.0, 0.0, 0.30])
    parts.append(orb_ring)

    # ---- Shoulder hub ----
    shoulder_hub = o3d.geometry.TriangleMesh.create_cylinder(
        radius=0.055, height=0.03, resolution=20
    )
    _paint(shoulder_hub, [0.82, 0.82, 0.80])
    _translate(shoulder_hub, [0.0, 0.0, 0.50])
    parts.append(shoulder_hub)

    # ---- Neck ----
    neck = o3d.geometry.TriangleMesh.create_cylinder(
        radius=0.030, height=0.10, resolution=16
    )
    _paint(neck, [0.85, 0.85, 0.82])
    _translate(neck, [0.0, 0.0, 0.58])
    parts.append(neck)

    # ---- Face (squashed sphere → oval) ----
    face = o3d.geometry.TriangleMesh.create_sphere(radius=1.0, resolution=24)
    verts = np.asarray(face.vertices)
    verts[:, 0] *= 0.065   # depth (thin screen) .03
    verts[:, 1] *= 0.14   # half-width .15
    verts[:, 2] *= 0.175   # half-height .19
    face.vertices = o3d.utility.Vector3dVector(verts)
    _paint(face, [0.08, 0.08, 0.12])
    _translate(face, [0.01, 0.0, 0.82])
    parts.append(face)

    # Bezel
    bezel = o3d.geometry.TriangleMesh.create_sphere(radius=1.0, resolution=24)
    verts_b = np.asarray(bezel.vertices)
    verts_b[:, 0] *= 0.025
    verts_b[:, 1] *= 0.16
    verts_b[:, 2] *= 0.20
    bezel.vertices = o3d.utility.Vector3dVector(verts_b)
    _paint(bezel, [0.90, 0.90, 0.87])
    _translate(bezel, [-0.005, 0.0, 0.82])
    parts.append(bezel)

    # ---- Eyes ----
    for y_sign in [-1, 1]:
        eye = o3d.geometry.TriangleMesh.create_sphere(
            radius=0.035, resolution=12
        )
        _paint(eye, [0.2, 0.9, 0.95])
        _translate(eye, [0.04, y_sign * 0.05, 0.86])
        parts.append(eye)

    # ---- Camera module ----
    cam = o3d.geometry.TriangleMesh.create_box(
        width=0.05, height=0.075, depth=0.05
    )
    _paint(cam, [0.9, 0.9, 0.87])
    _translate(cam, [-0.0, -0.10, 0.97])
    parts.append(cam)

    cam_led = o3d.geometry.TriangleMesh.create_sphere(
        radius=0.006, resolution=8
    )
    _paint(cam_led, [0.9, 0.1, 0.1])
    _translate(cam_led, [0.015, 0.0, 1.005])
    parts.append(cam_led)

    # ---- Arms ----
    for side_sign in [-1, 1]:
        arm_parts = []
        n_seg = 6
        seg_len = 0.028
        seg_gap = 0.008

        for i in range(n_seg):
            r = 0.018 if i % 2 == 0 else 0.014
            seg = o3d.geometry.TriangleMesh.create_cylinder(
                radius=r, height=seg_len, resolution=10
            )
            _paint(seg, [0.82, 0.82, 0.78])
            _translate(seg, [0.0, 0.0, i * (seg_len + seg_gap)])
            arm_parts.append(seg)

        # Duck hand
        hand = o3d.geometry.TriangleMesh.create_sphere(
            radius=0.022, resolution=10
        )
        _paint(hand, [1.0, 0.75, 0.0])
        _translate(hand, [0.0, 0.0, n_seg * (seg_len + seg_gap)])
        arm_parts.append(hand)

        arm = arm_parts[0]
        for p in arm_parts[1:]:
            arm += p

        # Rotate outward and slightly forward
        R_out = arm.get_rotation_matrix_from_xyz(
            [np.radians(side_sign * -55), np.radians(-20), 0.0]
        )
        arm.rotate(R_out, center=[0, 0, 0])
        _translate(arm, [0.01, side_sign * 0.07, 0.49])
        parts.append(arm)

    # ---- Mic boom ----
    mic_boom = o3d.geometry.TriangleMesh.create_cylinder(
        radius=0.004, height=0.12, resolution=8
    )
    _paint(mic_boom, [0.2, 0.2, 0.2])
    R_mic = mic_boom.get_rotation_matrix_from_xyz([np.radians(-30), 0, 0])
    mic_boom.rotate(R_mic, center=[np.radians(90), 0, 0])
    _translate(mic_boom, [-0.02, -0.14, 0.88])
    parts.append(mic_boom)

    mic_tip = o3d.geometry.TriangleMesh.create_sphere(
        radius=0.008, resolution=8
    )
    _paint(mic_tip, [0.15, 0.15, 0.15])
    _translate(mic_tip, [-0.02, -0.19, 0.82])
    parts.append(mic_tip)

    # ---- Merge ----
    combined = parts[0]
    for p in parts[1:]:
        combined += p

    combined.compute_vertex_normals()
    return combined