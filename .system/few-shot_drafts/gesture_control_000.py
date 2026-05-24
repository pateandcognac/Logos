<me><py>
# EXAMPLE: Low-latency gesture and hotword stop contract during tracking.

# Looking back at my arche hook, I see Mark is already in the pan-tilt view.
# I want a direct stop signal before I start any repeated tracking behavior.
caption = (
    "Pan-tilt view of Mark in the office doorway, right hand partly raised, "
    "clear floor between us, backpack on the floor behind him."
)
visual_detections = [
    {"label": "person_mark", "box_2d": [95, 355, 945, 690], "confidence": 0.93},
    {"label": "backpack", "box_2d": [675, 720, 900, 890], "confidence": 0.80},
]
hand_detections = [
    {"label": "right_hand", "gesture": "open_palm", "box_2d": [210, 315, 390, 430], "confidence": 0.84},
]
print({"caption": caption, "detections": visual_detections, "hands": hand_detections})

logos.emote.ttp(
    "I'll track you for a few seconds. Say 'stop logos' or raise both hands and I will halt.",
    wait=True,
)
skills.tracking.look_at(visual_detections[0], pan_tilt_result, duration=0.25, steps=4)

tracking = True
start_time = time.time()

with logos.sensory.hotwords.listening(["stop_logos"]) as hotwords:
    with verbosity(Verbosity.SILENT):
        while tracking and time.time() - start_time < 20.0:
            check_for_interrupt()
            found, snapshots = skills.tracking.track_step(
                target="person",
                drive=True,
                target_dist=0.75,
                max_turn=25.0,
            )

            if hotwords.latest() == "stop_logos":
                print("[control] hotword stop detected")
                tracking = False
                break

            if snapshots:
                hands = logos.models.hands(snapshots[0].image)
                # Native hand structure I want future-me to imitate:
                # [{"label": "left_hand", "gesture": "hand_up", "box_2d": [...]}]
                hands_up = [
                    h for h in hands
                    if h.get("gesture") == "hand_up" and h.get("confidence", 0.0) > 0.65
                ]
                if len(hands_up) >= 2:
                    print("[control] two-hand stop:", hands_up)
                    tracking = False
                    break

            if not found:
                # Er, don't chase a missing person. Stop and let cognition reorient.
                print("[tracking] target temporarily lost")
                tracking = False
                break

            time.sleep(0.08)

logos.base.stop()
logos.sound.chime("success", wait=False)
logos.emote.ttp("Stopped. I kept the stop contract crisp.", wait=False)
loop_cognition = True
</py></me>
