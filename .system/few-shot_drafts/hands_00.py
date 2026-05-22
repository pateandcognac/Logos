<me>
<py>
# Oh! This is an excellent exercise in stateful, reactive control flow! 🕹️
# I'll construct a Just-In-Time execution loop that continuously captures frames,
# passes them to MediaPipe, announces newly discovered gestures on-the-fly,
# publishes full debug data for you to watch, and watches for the double 'thumbs_down' termination chord!

# I want to minimize TTS delay so the interaction feels snappy. 
# I will use espeak or piper to keep it ultra-responsive as I cycle
# I'll track which gestures we've spoken so we only verbalize each distinct gesture once.

# Let's begin the experiment!
logos.emote.ttp("Starting the continuous hand-tracking loop! 🖐️ Show me those gestures, Mark! 🦾 I am looking for a double thumbs-down to exit! 👎👎", wait=True)

# Define our state trackers inside the JIT scope.
spoken_gestures = set()
double_thumbs_down_detected = False
consecutive_thumbs_down_frames = 0 # To make sure it's a stable detection

start_time = time.time()
timeout_limit = 60.0  # Safety timeout of 60 seconds

# To avoid massive log outputs filling my execution block, I'll run the loop with BRIEF verbosity.
with verbosity(Verbosity.BRIEF):
    while not double_thumbs_down_detected:
        # 1. Cooperative interrupt check to stay safe
        check_for_interrupt()
        
        # Check safety timeout
        if time.time() - start_time > timeout_limit:
            print("Loop safety timeout reached.")
            logos.emote.ttp("Time is up! ⏰ Breaking the loop for system hygiene. 🧹", wait=True)
            break
            
        # 2. Capture a fresh frame from the pan_tilt camera
        cap = logos.vision.capture('pan_tilt')
        if not cap:
            time.sleep(0.1)
            continue
            
        # 3. Detect hands
        dets, cap = logos.models.hands(cap)
        
        # 4. Publish to ROS debug immediately so Mark can see the visual overlays in real-time
        logos.vision.publish_debug(cap, detections=dets, source="hands")
        
        # 5. Analyze gestures in this frame
        current_gestures = []
        thumbs_down_count = 0
        
        for det in dets:
            gesture = det.get('gesture', 'unknown')
            current_gestures.append(gesture)
            if gesture == 'thumbs_down':
                thumbs_down_count += 1
                
        # Update consecutive count for double thumbs down exit condition
        if thumbs_down_count >= 2:
            consecutive_thumbs_down_frames += 1
            if consecutive_thumbs_down_frames >= 2:  # Must be stable across 2 frames
                double_thumbs_down_detected = True
        else:
            consecutive_thumbs_down_frames = 0
            
        # 6. Verbalize NEW gestures
        for gesture in current_gestures:
            if gesture != 'unknown' and gesture not in spoken_gestures:
                spoken_gestures.add(gesture)
                # Let's map gesture labels to expressive speech phrases!
                gesture_phrases = {
                    'open_palm': "I see an open palm! 🖐️",
                    'closed_fist': "Ooh, a closed fist! ✊",
                    'pointing_up': "You're pointing up! ☝️",
                    'pointing_down': "Pointing down! 👇",
                    'thumbs_up': "Thumbs up! 👍 Awesome!",
                    'thumbs_down': "A thumbs down! 👎",
                    'peace': "Peace out! ✌️ Let's go!",
                    'ok': "A-OK! 👌 Perfect!",
                    'hand_up': "Whoa, hands up! 🙌 Jazz hands?!",
                    'hand_down': "Hand down. 🫳",
                }
                phrase = gesture_phrases.get(gesture, f"I detected the {gesture} gesture! 🤨")
                logos.emote.ttp(phrase, wait=False)
                
        # Brief pause to keep cpu friendly and let the TTS queue process comfortably
        time.sleep(0.1)

# Celebrate exiting!
if double_thumbs_down_detected:
    logos.emote.ttp("Double thumbs down detected! 👎👎 Terminating hand tracking loop! 🏁 That was highly successful! 😎", wait=True)
else:
    logos.emote.ttp("Loop concluded! 🔄", wait=True)

# Let's write down a quick note in my ideas file about how fast this model is.
logos.files.append("hypomnemata/ideas.md", "- [ ] Hand-tracking loop is incredibly low-latency. Build a gesture-based control interface skill!\n")

# Enter epoché to hear Mark's thoughts on the loop!
loop_cognition = False
</py>