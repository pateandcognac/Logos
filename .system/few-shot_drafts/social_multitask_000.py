<me><py>
# EXAMPLE: Social response plus a small navigation/perception side quest.

# Before I answer Mark, let me preserve what I actually see. My context window
# will forget images faster than it forgets explicit spatial notes.
caption = (
    "Pan-tilt view of Mark smiling near the doorway, holding a red notebook; "
    "floor ahead is mostly clear except for a cable coil near the threshold."
)
detections = [
    {"label": "person_mark_smiling", "box_2d": [80, 350, 925, 690], "confidence": 0.94},
    {"label": "red_notebook", "box_2d": [330, 560, 610, 745], "confidence": 0.82},
    {"label": "cable_coil", "box_2d": [735, 450, 890, 610], "confidence": 0.73},
]
print({"caption": caption, "detections": detections})

# I can be socially present and still do one useful embodied check. The cable is
# small, so I'll mark it in my notes rather than navigate immediately.
skills.tracking.look_at(detections[0], pan_tilt_result, duration=0.25, steps=4)
logos.emote.ttp(
    "I see you and the red notebook. Also, tiny practical note: there is a cable coil near the threshold.",
    wait=False,
)

crop = pan_tilt_result.crop(box_2d=detections[2]["box_2d"])
crop.meta["caption"] = "Cable coil near threshold noticed during conversation."
crop.meta["detections"] = [detections[2]]
crop_path = crop.save(view=True, meta_keys=["caption", "detections"])

logos.files.append(
    "state/room_breadcrumbs.md",
    "- Cable coil near threshold noticed while Mark held red notebook. Crop: %s\n" % crop_path,
)

# Maybe Mark is about to ask me to move through that doorway. I'll loop once so
# the next hook can refresh Chora and decide whether the cable matters.
loop_cognition = True
</py></me>
