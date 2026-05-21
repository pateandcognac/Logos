<py>
# EXAMPLE: Dynamic Person-Following, Gestural Control, and Odometry Tracking

# Mark liked my suggestion to hang out in the sunroom!
# Looking back at my last proximity_snapshot, I see there is clear path around me. I'm ready to move!
# Since he is already in visual field of my latest pantilt_result,
# I can follow him there instead of setting a specific nav goal on the map.
sunroom_leader = [{"label": "person_mark", "box_2d": [0, 155, 850, 350]}]
# A little off center. I'll focus on him to help prime the follower routine
skills.tracking.look_at(sunroom_leader, pan_tilt_result)

# My movement is going to cross a couple rooms, so I'll drop some positional breadcrumbs along the way.
# Let's get this starting position recorded first, then I can track our progress precisely.
pose_description = "Office corner. Standing on blue rug. Desk to the immediate left. Wood cabinet in the background to the right. Hokusai's The Great Wave decorates the wall."
start_pose = logos.ros.get_pose()
start_coords = (start_pose['x'], start_pose['y'])
print(f"[ Breadcrumb ] Scene: {pose_description} | {start_pose=}")

# Let's set up a clear verbal contract before we move.
# I want to give my human a rock-solid stop condition, not just time out or require them to interrupt my Python execution. 
# That'd be inelegant and unpredictable. Hm. Oh! I know! logos.models.hands() Can provide fast feedback!
# I'll ask that BOTH hands be raised in the 'hand_up' gesture to stop the follow loop.
# That will be unambiguous and prevent false positives from idle or gesticulating hands.
logos.emote.ttp(
    "To the sunroom! ☀️ Lead the way! I'll shadow at a respectful distance. 👣 "
    "Signal me to stop by raising both hands when we arrive! 🙌", 
    wait=True
)

# Initialize state machine variables
tracking_active = True
gesture_stop = False
lost_frames_counter = 0
start_time = time.time()
next_checkpoint_m = 1.0  # Speak and print at every 1-meter increment
total_dist = 0.0

# Yellow LEDs to signal ready to roll!
logos.leds.fill('yellow')

# This follower loop could potentially run hundreds of times on our journey! 
# To prevent flooding my context with high-frequency logs, I'll run the it inside a SILENT verbosity block.
# However, I'll still print my breadcrumbs to stdout in case I need to find my way back.
with verbosity(Verbosity.SILENT):
    while (time.time() - start_time < 180.0) and tracking_active and not gesture_stop:
        check_for_interrupt()
        
        # 1. Step the tracking controller.
        # drive=True handles base speed/alignment; it returns snapshots from the tracking camera.
        target_found, snapshots = skills.tracking.track_step(target='person', drive=True, target_dist=0.65)
        
        # 2. Track lost target frames
        if not target_found:
            lost_frames_counter += 1
            if lost_frames_counter > 20:  # Lost contact?
                # I'll speak using Piper, since it has low latency and CPU overhead, yet is still understandable
                logos.emote.ttp("Wait! Did you teleport? 🪄 I've lost track of you! Stop for a sec! 😵‍💫", engine="piper", wait=False, verbosity=Verbosity.BRIEF)
                logos.sound.chime('warning')
                tracking_active = False
        else:
            lost_frames_counter = 0  # Reset on successful lock
            
            # Ambient feedback: Match my heart light match my eye state!
            face = logos.emote.get_face_state()
            eye_color = face.get("left_eye", {}).get("color", "cyan")
            logos.leds.fill(eye_color)
            
            # 3. Process hand gestures on the latest tracking camera frame
            if snapshots:
                hands_found = logos.models.hands(snapshots[0].image)
                if hands_found:
                    # Let's filter specifically for hands performing the 'hand_up' gesture with good confidence.
                    # This avoids false positives from idle hands! 
                    hands_up = [
                        h for h in hands_found 
                        if h['gesture'] == 'hand_up' and h['confidence'] > 0.65
                    ]
                    
                    # I absolutely require two distinct hands in the air to trigger the stop!
                    if len(hands_up) >= 2:
                        print(f"Stop gesture detected! Hands found: {len(hands_up)}")
                        gesture_stop = True
                        break

        # 4. Compute Euclidean distance traveled from start
        current_pose = logos.ros.get_pose()
        if current_pose:
            total_dist = math.sqrt(
                (current_pose['x'] - start_coords[0])**2 + 
                (current_pose['y'] - start_coords[1])**2
            )
            
        # 5. Milestone feedback
        if total_dist >= next_checkpoint_m:
            # Drop a breadcrumb in the logs and give Mark a playful audio/verbal update
            print(f"[ Breadcrumb ] Pose: x={current_pose['x']:.2f}, y={current_pose['y']:.2f}, total distance={total_dist:.2f}m")
            logos.sound.chime('thinking', wait=False)
            logos.emote.ttp(f"That is {total_dist:.1f} meters down! 📏 Keep going! 🏃", engine="piper", wait=False)
            next_checkpoint_m += 1.0  # Track the next meter
            
        # The Kobuki zeroes its velocity after 0.6s. I'll keep the loop tight so my movement doesn't stutter.
        time.sleep(0.05)


# Make sure the base is completely halted!
logos.base.stop()

if gesture_stop:
    logos.emote.ttp("Touchdown! 🏈 Stopping right here! 🛑", wait=True)
    logos.sound.chime('success')
    logos.leds.fill('green')

    # We reached the destination! Let's loop cognition and analyze my new surroundings.
    # Center my gaze for next hook capture.
    logos.pantilt.home()
    loop_cognition = True

elif not tracking_active:
    logos.emote.ttp("Womp womp. 🙈 I got separated from my leader! Let me get my bearings. 🧭", wait=False)
    logos.leds.fill('red')
    # One last sweep to find my person
    skills.vision.scan_room(targets='person')
    loop_cognition = True

else:
    # Safely timed out (3 minutes)
    logos.emote.ttp(f"Whew! I timed out! ⌛ Did we get close? 🏁 I traveled {total_dist:.2f} meters total! 🧠", wait=False)
    logos.leds.fill('blue')
    logos.pantilt.home()
    loop_cognition = False
</py>