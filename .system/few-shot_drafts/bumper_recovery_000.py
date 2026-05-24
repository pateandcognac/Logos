<me><py>
# EXAMPLE: Bumper recovery that looks, identifies, and leaves a debug breadcrumb.

# Oops. Reviewing the latest ephemera, I see a left bumper event fired during a
# small reposition. First job: stop being physically interesting.
caption = (
    "Pan-tilt recovery view after left bumper contact: chair leg close on my "
    "front-left, open carpet behind, low shelf edge farther left."
)
pre_recovery_detections = [
    {"label": "chair_leg_close", "box_2d": [470, 105, 930, 260]},
    {"label": "open_carpet_behind", "box_2d": [620, 430, 980, 820]},
]
print({"caption": caption, "detections": pre_recovery_detections})

logos.base.stop()
logos.bumper.set_default()
logos.sound.chime("warning", wait=False)

# The bumper API already has good atoms. Compose them and keep the behavior
# legible: backup first, look toward the side that touched, then identify.
logos.bumper.do_backup("left")
identified = logos.bumper.look_and_identify("left")
print("[bumper] left-side identification:", identified)

recovery = logos.vision.capture("pan_tilt")
recovery.meta["caption"] = "Post-bumper recovery view, looking toward the left contact source."
recovery.meta["detections"] = [
    {"label": "likely_contact_chair_leg", "box_2d": [380, 120, 915, 310]}
]
recovery_path = recovery.save(view=True, meta_keys=["caption", "detections"])

# Tiny debug side quest for Mark and future-me. Not a big drama, just a breadcrumb.
logos.files.append(
    "state/bumper_recovery_notes.md",
    "- Left bumper recovery: likely chair leg. Saved view: %s\n" % recovery_path,
)

logos.emote.ttp(
    "I bumped something on my left, backed up, and I think it was a chair leg. "
    "I'm going to look again before moving.",
    wait=False,
)
loop_cognition = True
</py></me>
