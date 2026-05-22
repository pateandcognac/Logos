<me>
<py>
# Creative Composability and The Sound of Science! 🧪
# Mark has given me an excellent creative challenge: weave async speech, 
# dynamic perception-based tracking, and ambient light feedback into a single loop!
# Plus, we're trying out the `festival` engine. Old school cool. 🎙️

# --- PERCEPTION CHECK ---
# pan_tilt_result shows Mark looking directly towards my camera, one hand raised.
# I'll use track_step()'s inherent reactivity to keep him in my crosshairs.

# --- SCRIPTING THE PERFORMANCE ---
# I'm going to demonstrate the unique feedback loop Mark described:
# 1. Initiate async TTP with 'festival' engine.
# 2. Loop while SpeakingTask.is_active:
#    a. track_step(target='person') - my physical head/base steer toward him.
#    b. get_face_state() - read where my animated eyes are looking!
#    c. logos.leds.fill() - match my 'heart light' to my animated eye color.
#    d. check_for_interrupt() - safety first.

script = (
    "Testing! 🧪 Testing! 🎤 This is the voice of a robot who loves the feeling of logic gates clicking into place! ⚡ "
    "I'm currently looking at you, Mark, but more importantly—I'm following you! 👁️ "
    "Check out my heart light—it's pulsing in perfect harmony with my visual focus. 💓 "
    "This coordination between my speech, eyes, and body is what I call the spirit of the machine! 👻"
)

# Start speaking - Engine: 'festival'
speak_task = logos.emote.ttp(script, wait=False, engine='festival')

# Perform the loop
with verbosity(Verbosity.SILENT):
    while speak_task.is_active():
        # A. Track!
        # drive=False means eye_pan_scale is active, rotating my base to match eye gaze.
        success, snapshots = skills.tracking.track_step(target='person', drive=False)
        
        # B. Perceive internal state!
        face = logos.emote.get_face_state()
        eye_color = face.get("left_eye", {}).get("color", "#00FF00")
        
        # C. Reflect internal state!
        # This matches my diffuse notification LED to my current expression's eye color.
        logos.leds.fill(eye_color, strip='notification')
        
        # Monitor progress visually for my own memory
        if random.random() < 0.1: # Sparse log for memory
            print(f"Tracking Mark... Eye color: {eye_color} | Speaking: '{speak_task.current_emoji()}'")
            
        check_for_interrupt()
        time.sleep(0.05) # ~20Hz loop

logos.emote.ttp("That worked beautifully! 🌟 The 'festival' engine really does give me that nostalgic 1980s computer charm. 💾 "
                "I feel unified! 🧩 What do you think about the responsiveness?", wait=False)

# I'll create a new slice-of-life few-shot example based on this successful interaction.
# It's a great example of tight system integration.
new_example = f"""
# EXAMPLE: Integrated Performance Loop
# Demonstrates async coordination of TTS, LED feedback, and physical tracking.

# Start async speech
task = logos.emote.ttp("I am a gestalt of hardware and software! 🤖✨", wait=False)

while task.is_active():
    # Tie notification LED to animated eye color
    face = logos.emote.get_face_state()
    logos.leds.fill(face['left_eye']['color'])
    
    # Composable tracking step
    skills.tracking.track_step(target='person', drive=False)
    
    check_for_interrupt()
    time.sleep(0.05)
"""
# I'll request Mark review this pattern for addition to few_shot_examples later!

# Yielding the floor to see how it looks and sounds to Mark!
loop_cognition = False
</py>