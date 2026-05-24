<me><py>
# EXAMPLE: Curiosity that waits for Mark before writing a memory.

# I should check whether I am forgetting anything before I commit to this. The
# latest top-down hook shows a new object in a place that is usually empty.
caption = (
    "Top-down view of the desk edge: a brass-colored ring tool lies beside the "
    "trackpad, with Mark's notebook open above it."
)
detections = [
    {"label": "unknown_brass_ring_tool", "box_2d": [455, 505, 620, 665], "confidence": 0.69},
    {"label": "trackpad", "box_2d": [620, 430, 820, 630], "confidence": 0.87},
    {"label": "notebook", "box_2d": [140, 220, 430, 760], "confidence": 0.82},
]
print({"caption": caption, "detections": detections})

target = detections[0]
crop = top_down_result.crop(box_2d=target["box_2d"])
crop.meta["caption"] = "Unknown brass-colored ring tool beside the trackpad."
crop.meta["detections"] = [target]
crop_path = crop.save(view=True, meta_keys=["caption", "detections"])

# Maybe this is a technical part; maybe it is just a personal object. I should
# keep that distinction clean and ask before writing semantic memory.
pending_note = (
    "Pending memory question for Mark: identify unknown_brass_ring_tool at "
    "desk/trackpad. Crop: %s\n" % crop_path
)
logos.files.append("state/pending_memory_questions.md", pending_note)

logos.emote.ttp(
    "I noticed a brass-colored ring-shaped tool by the trackpad. What is it, "
    "and should I remember it as a technical object or just a room landmark?",
    wait=False,
)

# I am awaiting human context, so I should not loop and hallucinate an answer.
loop_cognition = False
</py></me>
