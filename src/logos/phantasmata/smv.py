# src/logos/phantasmata/self_model.py

# ---- SCHEMA ----
# These parameters let me customize the appearance of my 3D rendering


SCHEMA = {
    # ---- Geometry toggles ----
    'show_base': {'type': 'bool', 'default': True, 'description': 'My Kobuki mobile base platform', },
    'show_column': {'type': 'bool', 'default': True, 'description': 'My central support column', },
    'show_face': {'type': 'bool', 'default': True, 'description': 'My oval display face with eyes', },
    'show_eyes': {'type': 'bool', 'default': True, 'description': 'My glowing cyan eyes on the face', },
    'show_arms': {'type': 'bool', 'default': True, 'description': 'My corrugated arms with yellow hands', },
    'show_orb': {'type': 'bool', 'default': True, 'description': 'My chest orb indicator', },
    'show_camera': {'type': 'bool', 'default': True, 'description': 'My pan-tilt camera module', },
    'show_mic': {'type': 'bool', 'default': True, 'description': 'My microphone boom', },

    # ---- Style ----
    'base_color': {'type': 'rgb', 'default': [0.85, 0.85, 0.82], 'description': 'Color of my base platform', },
    'body_color': {'type': 'rgb', 'default': [0.88, 0.88, 0.85], 'description': 'Color of my body column and neck', },
    'face_color': {'type': 'rgb', 'default': [0.08, 0.08, 0.12], 'description': 'Color of my face display', },
    'eye_color': {'type': 'rgb', 'default': [0.2, 0.9, 0.95], 'description': 'Color of my eyes (cyan glow)', },
    'hand_color': {'type': 'rgb', 'default': [1.0, 0.75, 0.0], 'description': 'Color of my duck-like yellow hands', },
    'orb_color': {'type': 'rgb', 'default': [0.5, 0.85, 1.0], 'description': 'Color of my chest orb',},
}


def build(params: Dict[str, Any], ctx: Any) -> Optional[SceneObject]:
    """Construct my 3D body at the origin. Map3d applies my robot TF pose after calling this, so I build everything centered at (0,0,0) facing +X (ROS forward)."""
    # ---- Kobuki Base ----
    if params.get('show_base', True):
        base_color = params.get('base_color', [0.85, 0.85, 0.82])

        # Lower base cylinder
        base_lower = o3d.geometry.TriangleMesh.create_cylinder(
            radius=0.15, height=0.07, resolution=32
        )
        _paint(base_lower, base_color)
        _translate(base_lower, [0.0, 0.0, 0.02])
        parts.append(base_lower)

        # Upper base cylinder (slightly larger)
        base_upper = o3d.geometry.TriangleMesh.create_cylinder(
            radius=0.155, height=0.04, resolution=32
        )
        _paint(base_upper, [c + 0.05 for c in base_color])
        _translate(base_upper, [0.0, 0.0, 0.07])
        parts.append(base_upper)

        # Green LED accent on front of base
        led_base = o3d.geometry.TriangleMesh.create_box(
            width=0.04, height=0.03, depth=0.02
        )
        _paint(led_base, [0.1, 0.9, 0.3])
        _translate(led_base, [0.13, -0.015, 0.04])
        parts.append(led_base)

    # ---- Central Column ----
    if params.get('show_column', True):
        body_color = params.get('body_color', [0.88, 0.88, 0.85])

        column = o3d.geometry.TriangleMesh.create_cylinder(
            radius=0.04, height=0.48, resolution=20
        )
        _paint(column, body_color)
        _translate(column, [0.0, 0.0, 0.32])
        parts.append(column)

        # Shoulder hub
        shoulder_hub = o3d.geometry.TriangleMesh.create_cylinder(
            radius=0.055, height=0.03, resolution=20
        )
        _paint(shoulder_hub, [c - 0.06 for c in body_color])
        _translate(shoulder_hub, [0.0, 0.0, 0.50])
        parts.append(shoulder_hub)

        # Neck
        neck = o3d.geometry.TriangleMesh.create_cylinder(
            radius=0.030, height=0.10, resolution=16
        )
        _paint(neck, body_color)
        _translate(neck, [0.0, 0.0, 0.58])
        parts.append(neck)

    # ---- Chest Orb ----
    if params.get('show_orb', True):
        orb_color = params.get('orb_color', [0.5, 0.85, 1.0])

        orb = o3d.geometry.TriangleMesh.create_sphere(radius=0.06, resolution=20)
        _paint(orb, orb_color)
        _translate(orb, [0.0, 0.0, 0.35])
        parts.append(orb)

        orb_ring = o3d.geometry.TriangleMesh.create_cylinder(
            radius=0.045, height=0.015, resolution=20
        )
        _paint(orb_ring, [0.80, 0.80, 0.78])
        _translate(orb_ring, [0.0, 0.0, 0.30])
        parts.append(orb_ring)

    # ---- Face (squashed sphere -> oval) ----
    if params.get('show_face', True):
        face_color = params.get('face_color', [0.08, 0.08, 0.12])

        face = o3d.geometry.TriangleMesh.create_sphere(radius=1.0, resolution=24)
        verts = np.asarray(face.vertices)
        verts[:, 0] *= 0.065   # depth (thin screen)
        verts[:, 1] *= 0.14    # half-width
        verts[:, 2] *= 0.175   # half-height
        face.vertices = o3d.utility.Vector3dVector(verts)
        _paint(face, face_color)
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
    if params.get('show_eyes', True) and params.get('show_face', True):
        eye_color = params.get('eye_color', [0.2, 0.9, 0.95])

        for y_sign in [-1, 1]:
            eye = o3d.geometry.TriangleMesh.create_sphere(
                radius=0.035, resolution=12
            )
            _paint(eye, eye_color)
            _translate(eye, [0.04, y_sign * 0.05, 0.86])
            parts.append(eye)

    # ---- Camera Module ----
    if params.get('show_camera', True):
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
    if params.get('show_arms', True):
        hand_color = params.get('hand_color', [1.0, 0.75, 0.0])

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
            _paint(hand, hand_color)
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

    # ---- Mic Boom ----
    if params.get('show_mic', True):
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

    # ---- Merge all parts ----
    if not parts:
        return None

    combined = parts[0]
    for p in parts[1:]:
        combined += p

    combined.compute_vertex_normals()

    return SceneObject(
        name='self',
        kind='mesh',
        geometry=combined,
        render_visible=True,
        raycast_visible=True,
        shader='defaultLit',
    )