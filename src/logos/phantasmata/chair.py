
import open3d as o3d
from logos.phantasmata.phantasma_convention import SceneObject, apply_pose_to_geometry

SCHEMA = {
    'seat_width': {'python_type': float, 'default': 0.42},
    'seat_depth': {'python_type': float, 'default': 0.40},
    'leg_height': {'python_type': float, 'default': 0.45},
    'color': {'python_type': list, 'default': [0.8, 0.7, 0.5]}, # Light wood/beige
}

def build(params, ctx):
    import numpy as np
    w = params.get('seat_width', 0.42)
    d = params.get('seat_depth', 0.40)
    lh = params.get('leg_height', 0.45)
    color = params.get('color', [0.8, 0.7, 0.5])

    # 1. Create Seat (a box)
    # create_box(width, height, depth) -> [X, Y, Z]
    # In my construction: X is width, Y is depth, Z is thickness
    seat = o3d.geometry.TriangleMesh.create_box(width=w, height=d, depth=0.04)
    # Center seat over origin and raise it to leg height
    seat.translate([-w/2, -d/2, lh])

    # 2. Create Backrest
    back_h = 0.40
    back = o3d.geometry.TriangleMesh.create_box(width=w, height=0.04, depth=back_h)
    # Position at the rear of the seat
    back.translate([-w/2, d/2 - 0.04, lh + 0.04])

    # 3. Create Legs (cylinders)
    chair_mesh = seat + back
    leg_radius = 0.015
    for lx in [-w/2 + 0.04, w/2 - 0.04]:
        for ly in [-d/2 + 0.04, d/2 - 0.04]:
            leg = o3d.geometry.TriangleMesh.create_cylinder(radius=leg_radius, height=lh)
            # Cylinder is created centered on Z, so translate up
            leg.translate([lx, ly, lh/2])
            chair_mesh += leg

    # Final touches
    chair_mesh.paint_uniform_color(color)
    chair_mesh.compute_vertex_normals()

    # Apply the instance pose from the mind palace config
    apply_pose_to_geometry(chair_mesh, ctx.instance_config.get('pose'))

    return SceneObject(name=ctx.instance_name, kind="chair", geometry=chair_mesh)
