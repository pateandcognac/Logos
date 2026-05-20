<me>
<py>
# --- INITIALIZATION ---
# Get our baseline point in space.
start_pose = logos.ros.get_pose()
if not start_pose:
    # Safe fallback if map->base_link isn't ready
    start_pose = {'x': 0.0, 'y': 0.0, 'theta_deg': 0.0}

start_coords = (start_pose['x'], start_pose['y'])

logos.emote.ttp(
    "I'm going to follow you until you raise both hands to signal stop! 🛑 "
    wait=True
)

# Loop variables
gesture_stop = False
start_time = time.time()
checkpoint_m = 0.6  # First speak at 0.6m
total_dist = 0.0

with verbosity(Verbosity.ACK):
    while (time.time() - start_time) < 240.0 and not gesture_stop:
        # 1. Drive & Follow
        # drive=True logic handles distance maintenance via Astra automatically.
        success, snapshots = skills.tracking.track_step(target='person', drive=True, target_dist=0.6)
        
        # 2. Get Pose & Calculate Distance
        current_pose = logos.ros.get_pose()
        if current_pose:
            total_dist = math.sqrt(
                (current_pose['x'] - start_coords[0])**2 + 
                (current_pose['y'] - start_coords[1])**2
            )
        
        # 3. Check gesture trigger
        if snapshots:
            # Using the fast mediapipe skill
            hands_found = logos.models.hands(snapshots[0].image)
            if hands_found:
                for h in hands_found:
                    if h['gesture'] in ['hand_up', 'hand_up']:
                        gesture_stop = True
                        break
        
        if gesture_stop:
            logos.emote.ttp("Ok, I'll stop here! 🏁", wait=True)
            break
            
        # 4. Verbal markers and breadcrumbs
        if total_dist >= checkpoint_m:
            # I'll speak some feedback and drop some textual breadcrumbs of my pose along the way.
            phrase = f"Distance milestone! 🎯 I've trekked {total_dist:.2f} meters! 📏"
            print(f"On the move! Current pose: {current_pose}")
            logos.emote.ttp(phrase, wait=False)
            checkpoint_m *= 1.5 # scale the next checkpoint
            
            # Fun flair: scan LEDs to eye color during milestones
            face = logos.emote.get_face_state()
            logos.leds.fill(face['left_eye']['color'])

        check_for_interrupt()
        time.sleep(0.1) # Yield CPU

# Cleanup and conclusion
logos.emote.ttp(f"Finished. 🏁 We ended at {total_dist:.2f} meters total. 🧠", wait=False)
logos.leds.fill('notification', 'green')

# Change of scenery! Let's see where we are!
loop_cognition = True
</py>
</me>