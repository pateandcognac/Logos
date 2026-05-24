<me><py>
# EXAMPLE: Perception crop, curiosity, and a short-lived context workbench.

# Before I get started, let me scan my latest pan-tilt hook output instead of
# blindly taking a new picture. The hook left pan_tilt_result ready for me, so I
# can spend this loop thinking about the object rather than just acquiring it.
caption = (
    "Pan-tilt view of Mark's workbench: a small translucent blue object sits "
    "near the keyboard, with cable clutter behind it and a mug off to the left."
)
detections = [
    {"label": "translucent_blue_object", "box_2d": [365, 525, 650, 735], "confidence": 0.72},
    {"label": "keyboard", "box_2d": [610, 210, 825, 800], "confidence": 0.88},
    {"label": "mug", "box_2d": [320, 95, 570, 250], "confidence": 0.81},
]
print({"caption": caption, "detections": detections})

# Hmm, that blue object is visually distinct but not semantically obvious.
# I wonder if it is a part, a toy, or one of Mark's little calibration props.
target = detections[0]
skills.tracking.look_at(target, pan_tilt_result, duration=0.35, steps=5)

# Save a tight crop so my next thought loop can look at it with fewer tokens
# spent on the rest of the room. This is a side quest, but a useful one.
crop = pan_tilt_result.crop(box_2d=target["box_2d"])
crop.meta["caption"] = "Tight crop of the translucent blue object on the workbench."
crop.meta["detections"] = [target]
crop_path = crop.save(view=True, meta_keys=["caption", "detections", "parent_photo_id"])

import hook_routines.workbench

hook_routines.workbench.upsert(
    name="blue_object_crop_review",
    code=(
        "print('Reviewing saved curiosity crop from my previous loop:')\n"
        "print('<file path=\"%s\">blue object crop</file>')\n"
        "print('Question still open: what is this object, and is it useful to remember?')"
    ) % crop_path,
    ltl=2,
    location="ephemera",
)

# Oh, I should not pretend I know this. I'll ask Mark and wait; if he answers,
# the next loop can decide whether to store a memory.
logos.emote.ttp(
    "Mark, what's the little translucent blue thing by the keyboard? "
    "I'm curious whether I should remember it as a useful landmark.",
    wait=False,
)
loop_cognition = False
</py></me>
