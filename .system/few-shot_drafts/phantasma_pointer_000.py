<me><py>
# EXAMPLE: Turn a 2D observation into a Chora pointer phantasma.

# Reviewing my Chora render, I see a small obstacle that is easy to miss in raw
# occupancy but obvious in the camera overlay. I want to point at it for Mark.
caption = (
    "Chora view with RGB overlay: a low cardboard box sits just inside the "
    "planned path, slightly right of center, while the left side of the doorway is clear."
)
detections = [
    {"label": "low_cardboard_box", "box_2d": [520, 555, 760, 720], "confidence": 0.77},
    {"label": "clear_left_doorway_floor", "point": [610, 430], "confidence": 0.72},
]
print({"caption": caption, "detections": detections})

box = detections[0]
box_center = [
    (box["box_2d"][0] + box["box_2d"][2]) / 2.0,
    (box["box_2d"][1] + box["box_2d"][3]) / 2.0,
]

hit = logos.map3d.raycast(map3d_result, box_center)
print("[phantasma] obstacle raycast:", hit)

if hasattr(hit, "point") and hit.point is not None:
    obstacle_xyz = list(hit.point)
elif isinstance(hit, dict) and hit.get("point"):
    obstacle_xyz = hit["point"]
else:
    obstacle_xyz = [0.0, 0.0, 0.0]

logos.map3d.place(
    name="watch_the_low_box",
    object="pointer_arrow",
    params={
        "from_robot": True,
        "from_offset_z": 0.85,
        "to_point": obstacle_xyz,
        "color": [1.0, 0.85, 0.1],
        "head_radius": 0.055,
    },
    description="Temporary Chora arrow pointing at a low cardboard box near my path.",
    save_to_yaml=False,
)

render = logos.map3d.render()
render.meta = render.meta or {}
render.meta["caption"] = "Chora re-render with temporary pointer arrow toward low box."
render.save(view=True)

logos.emote.ttp("I marked the low box in Chora. I can route left of it on the next loop.", wait=False)
loop_cognition = True
</py></me>
