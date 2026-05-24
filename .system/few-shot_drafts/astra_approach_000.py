<me><py>
# EXAMPLE: Astra 3D approach with standoff and pan-tilt verification.

# Reflecting on the API docs in my prompt: Astra gives me depth, so this is the
# moment to use a 3D box instead of hand-waving from a 2D image.
caption = (
    "Astra depth view: Mark is standing near the sunroom threshold, torso "
    "centered, with a small side table behind his right hip."
)
detections = [
    {
        "label": "person_mark",
        "box_3d": [0.18, -0.08, 1.72, 0.58, 1.68, 0.42, 0.0, 0.0, -3.0],
        "box_2d": [110, 405, 925, 640],
        "confidence": 0.91,
    },
    {
        "label": "side_table",
        "box_3d": [0.92, -0.36, 2.15, 0.55, 0.62, 0.55, 0.0, 0.0, 8.0],
        "box_2d": [425, 690, 790, 890],
        "confidence": 0.78,
    },
]
print({"caption": caption, "detections": detections})

person = detections[0]

# Oh! Before the base moves, I should point my periscope at Mark. That gives the
# next hook a more socially useful confirmation frame.
skills.tracking.look_at(person, astra_result, duration=0.30, steps=5)
logos.emote.ttp("I see you. I'll come closer and stop with some breathing room.", wait=False)

# Approach with a standoff. This bridges the 3D visual detection through TF into
# the map, which is exactly the kind of embodied primitive I should compose.
nav_task = logos.nav.approach_astra_detection(person, astra_result, standoff=0.85, wait=False)
logos.sound.chime("thinking", wait=False)

# Small verification side quest: capture my directed gaze after starting motion,
# so the next cognition loop can compare "intended Mark" with "current Mark."
verify = logos.vision.capture("pan_tilt")
verify.meta["caption"] = "Verification view after starting Astra approach toward Mark."
verify.meta["detections"] = [{"label": "person_mark_expected", "box_2d": person["box_2d"]}]
verify.save(view=True, meta_keys=["caption", "detections", "pan_tilt_degs"])

print("[nav] approach task:", nav_task)
# I'll loop immediately so the next hook capture can confirm I am closing the
# distance and not drifting toward the side table.
loop_cognition = True
</py></me>

not async