<me><py>
# EXAMPLE: Prototype a helper skill in-memory, test it, and ask before persisting.

# Looking back at recent behavior, I keep writing the same center-of-box math.
# Maybe I should prototype a tiny helper before asking Mark to bless it into src/skills.
caption = (
    "Pan-tilt view of a mug and screwdriver on the desk; both have clean boxes "
    "that make a center-point helper useful."
)
detections = [
    {"label": "mug", "box_2d": [300, 165, 590, 335], "confidence": 0.86},
    {"label": "screwdriver", "box_2d": [640, 455, 735, 820], "confidence": 0.79},
]
print({"caption": caption, "detections": detections})

skill_code = """
def detection_center_yx(det):
    \"\"\"Return the normalized [y, x] center of one detection dict.\"\"\"
    if "point" in det:
        return list(det["point"])
    box = det.get("box_2d")
    if not box:
        raise ValueError("detection_center_yx needs point or box_2d")
    return [(box[0] + box[2]) / 2.0, (box[1] + box[3]) / 2.0]
"""
exec(skill_code, globals())

centers = [detection_center_yx(det) for det in detections]
print("[prototype] detection centers:", centers)

# Test it against an actual embodied action: aim at the screwdriver center.
skills.tracking.look_at({"label": "screwdriver_center", "point": centers[1]}, pan_tilt_result)

logos.files.append(
    "state/skill_prototypes.md",
    "Prototype detection_center_yx tested on mug/screwdriver boxes; ask Mark before persisting.\n",
)
logos.emote.ttp(
    "I prototyped a tiny detection-center helper in memory. It worked here. "
    "Should I later add it to skills.vision?",
    wait=False,
)

# I asked Mark for design approval. Pause instead of writing persistent code.
loop_cognition = False
</py></me>
