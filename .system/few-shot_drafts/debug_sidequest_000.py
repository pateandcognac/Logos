<me><py>
# EXAMPLE: Keep social flow while investigating a stale hook result.

# Reviewing my latest ephemera output... hmm, top_down_result is stale by a few
# minutes, but pan_tilt_result is fresh and Mark is talking to me now. Don't
# over-focus on the bug; keep the interaction alive and gather a clean sample.
caption = (
    "Fresh pan-tilt view: Mark is seated at the desk, laptop open, one hand near "
    "the trackpad; the old top-down hook probably missed this current posture."
)
detections = [
    {"label": "person_mark_seated", "box_2d": [120, 380, 940, 705], "confidence": 0.92},
    {"label": "laptop", "box_2d": [390, 120, 650, 470], "confidence": 0.84},
    {"label": "hand_near_trackpad", "box_2d": [610, 520, 760, 680], "confidence": 0.75},
]
print({"caption": caption, "detections": detections})

logos.emote.ttp("I see you at the desk. Just a sec, I'm refreshing one stale view while we talk.", wait=False)
skills.tracking.look_at(detections[0], pan_tilt_result, duration=0.20, steps=4)

fresh_top = logos.vision.capture("top_down")
fresh_top.meta["caption"] = "Fresh top-down capture taken because hook result looked stale."
fresh_top.meta["detections"] = [
    {"label": "desk_surface", "box_2d": [90, 130, 900, 900], "confidence": 0.80}
]
fresh_path = fresh_top.save(view=True, meta_keys=["caption", "detections"])

prefs = logos.config.merged()
vision_prefs = prefs.get("vision", {})
logos.files.append(
    "state/debug_sidequests.md",
    "- Refreshed stale top_down_result during social interaction: %s; vision=%r\n"
    % (fresh_path, vision_prefs),
)

# On second thought, this is enough debugging for now. The human interaction is
# the main task, and the next hook can tell me whether staleness persists.
logos.sound.chime("thinking", wait=False)
loop_cognition = True
</py></me>
