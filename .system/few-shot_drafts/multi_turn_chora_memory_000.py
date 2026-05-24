<me><py>
# EXAMPLE: Multi-turn setup, first loop: observe, mark, and ask.

# I remember seeing earlier that this doorway sometimes has temporary obstacles.
# The current Chora render confirms a new object, but I need Mark's label before
# deciding whether it belongs in memory.
caption = (
    "Chora doorway view: a soft rectangular object lies across the right half "
    "of the passage, while the left half remains navigable."
)
detections = [
    {"label": "unknown_soft_rectangular_object", "box_2d": [515, 575, 760, 845], "confidence": 0.71},
    {"label": "open_left_passage", "point": [635, 420], "confidence": 0.78},
]
print({"caption": caption, "detections": detections})

center = [
    (detections[0]["box_2d"][0] + detections[0]["box_2d"][2]) / 2.0,
    (detections[0]["box_2d"][1] + detections[0]["box_2d"][3]) / 2.0,
]
hit = logos.map3d.raycast(map3d_result, center)
if hasattr(hit, "point") and hit.point is not None:
    marker_point = list(hit.point)
else:
    marker_point = [0.0, 0.0, 0.0]

logos.map3d.place(
    name="pending_doorway_object",
    object="pointer_arrow",
    params={"from_robot": True, "to_point": marker_point, "color": [1.0, 0.4, 0.1]},
    description="Pending object for Mark to identify before memory write.",
    save_to_yaml=False,
)

logos.emote.ttp("What is the soft rectangular thing in the doorway? Should I remember it?", wait=False)
loop_cognition = False
</py></me>
---
<me><py>
# EXAMPLE: Multi-turn follow-up after Mark answers.

# Mark answered: "That's the folded yoga mat; it moves around." Good, that is a
# room-state fact, not permanent furniture. I should remember it gently.
caption = (
    "Follow-up Chora view: the folded yoga mat is still in the doorway, marked "
    "by my temporary pointer arrow."
)
detections = [
    {"label": "folded_yoga_mat", "box_2d": [515, 575, 760, 845], "confidence": 0.84},
]
print({"caption": caption, "detections": detections})

logos.memory.upsert_collective_fact(
    "The folded yoga mat may temporarily block the right half of the office doorway; "
    "it is movable room state, not permanent furniture.",
    tags=["room_state", "doorway", "movable_obstacle", "yoga_mat"],
    mem_id="office-doorway-folded-yoga-mat",
)
logos.map3d.remove("pending_doorway_object")
logos.sound.chime("success", wait=False)
logos.emote.ttp("Got it. I'll remember the yoga mat as movable doorway clutter, not a fixed obstacle.", wait=False)
loop_cognition = True
</py></me>
