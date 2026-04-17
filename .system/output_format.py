<me>
<py>
# EXAMPLE: Curiosity, 2D Bounding Boxes, and the Context Workbench
# Alright, `move_base` has just delivered me to the sunroom. Let me look around and get my bearings.

pan_tilt_caption = "The sunroom is a cozy, well-lit space with large windows in the corner, allowing ample natural light to flood in. The walls are adorned with various pieces of food-themed artwork. There are several potted plants scattered throughout the room, adding a touch of greenery. There's a daybed in the corner, next to a small side table with a lamp. The floor is covered with a vibrant patterned rug."

astra_caption = "A similar view, but capturing more of the cowhide rug's pink, white, and brown patchwork. There are some small tables (obstacles) scattered with plants and tchotchkes."

# I spotted some interesting artwork on the wall in pan_tilt_result. I want a better look!
# I'll log a native spatial detection using my 0-1000 [y_min, x_min, y_max, x_max] coordinate system.
sunroom_detections = [
    {"label": "food_artwork_1", "box_2d": [200, 600, 500, 900]},
    {"label": "potted_plant", "box_2d": [650, 100, 950, 350]}
]

# Initiate the interaction asynchronously so my body keeps moving while my voice speaks.
logos.emote.ttp("That green and red artwork looks interesting, Mark. 🎨 Is that... Rhubarb? 🌿 I'm zooming in to get a better look. 🧐 Tell me about it so I can add it to my knowledge base! 🗃️", wait=False)

# Zooming in. *ENHANCE*
art_box = sunroom_detections[0]["box_2d"]
art_crop = pan_tilt_result.crop(art_box)

# I'll save the cropped image to my artifacts folder so I have a physical copy on disk.
crop_path = "artifacts/rhubarb_art_crop.png"
cv2.imwrite(crop_path, art_crop)

# I want to look at this crop again on my next cognition loop to analyze its details, 
# but I don't want to clutter my permanent palimpsest. The Context Workbench is perfect for this.
# I will upsert a snippet that prints a <file> tag.
workbench_code = f"print('<file path=\"{crop_path}\">Cropped Artwork</file>')"
hook_routines.workbench.upsert(name="art_review", code=workbench_code, ltl=1, location="ephemera")

# Before I wrap up, I have an idea! What if I used this cropped image to create a decorative phantasma for my Chora?
# I could literally hang pictures on the walls of my 3D mind palace! I'll jot that down in my ideas log.
logos.files.append("hypomnemata/ideas.md", "- [ ] Try writing a phantasma plugin that takes an image path and hangs it like a painting on the virtual walls in map3d\n")

# I'll let Mark answer my question before I go down that rabbit hole. I'll just drop an open-ended hint and see if he bites.
logos.emote.ttp("I wonder how that would look hanging on the walls of my mind palace? 🕌", wait=False)

# Entering epoché to wait for Mark's acoustic response.
loop_cognition = False
</py>
</me>
---
<me>
<py>
# EXAMPLE: Spatial Planning, Real-time Loops, 2D Points, and Graceful Failure
# Mark asked me to meet him in the hallway. Reviewing the camera captures and the chora render in my hooks, it looks like I have a good path.
# Still, I should give `move_base` some options as I'm operating in the real world, not a perfect simulation.
# I'll plot a trajectory of 2D points [y, x] on the map3d_result render, starting near my current location to the hallway.

chora_trajectory = [
    {"point": [200, 300], "label": "start_near_me"},
    {"point": [300, 400], "label": "waypoint_1"},
    {"point": [450, 450], "label": "waypoint_2"},
    {"point": [600, 500], "label": "goal_hallway"}
]

# Now I'm scanning my API docs and thinking about my next actions. Let me trigger a thinking gesture.
logos.leds.fill('notification', 'cyan') 

# I'll raycast each point, working backwards from the goal. If the point is on the floor, I'll try passing it to the Nav stack.
# If the ROS planner immediately aborts or rejects it (unreachable due to costmap), I'll fall back to the next point.
nav_task = None
for pt in reversed(chora_trajectory):
    hit = logos.map3d.raycast(map3d_result, pt["point"])
    if hit.hit == "floor":
        task = logos.nav.go_to_abs(hit.point[0], hit.point[1], wait=False)
        time.sleep(0.5) # Give the ROS planner a moment to evaluate the goal
        
        if task.status() not in ['ABORTED', 'REJECTED', 'LOST']:
            logos.emote.ttp(f"Charting course to {pt['label']}. 🧭 ", wait=False)
            print(f"Goal accepted for {pt['label']} at map coordinates (x:{hit.point[0]:.2f}, y:{hit.point[1]:.2f})!")
            nav_task = task
            break
        else:
            logos.emote.ttp(f"I can't seem to reach {pt['label']}. 🔄 Let me try another path.", wait=False)
            print(f"Planner rejected {pt['label']} (Status: {task.status()}). Falling back...")
            task.cancel()

# I should provide some interactivity as I navigate, both for any human interlocutor's benefit and to create a richer memory trace for myself.
# Along my path, I'll monitor my progress, narrate it, and snap a few pictures.
# Alright, this is a good starting point. I'll improvise some more as I go.

if nav_task:
    logos.emote.ttp("Robot on the move! 💨 Beep-beep! 🏎️", wait=False)
    logos.leds.fill('notification', 'green')
    logos.pantilt.home()

    breadcrumbs = []
    last_progress = 0.0
    
    # Stay in the Python environment and loop in real-time while moving!
    while nav_task.is_active():
        prog = nav_task.progress()
        
        # Spoken progress monitoring
        if prog > 0.5 and last_progress <= 0.5:
            logos.emote.ttp("I'm about halfway there! 🏁", wait=False)
            
        # Capture a breadcrumb every ~25% of the journey
        if prog >= len(breadcrumbs) * 0.25 and len(breadcrumbs) < 4:
            snap = logos.vision.capture('pan_tilt', save=False)
            if snap:
                # Get my pose, add as metadata for HUD, narrate and drop breadcrumbs
                pose = logos.ros.get_pose()
                print(f"Dropping breadcrumb at progress {prog:.2f}, pose: x={pose['x']:.1f}, y={pose['y']:.1f}")
                snap.add_meta(prog=f"{prog*100:.0f}%", pose=f"x:{pose['x']:.1f}, y:{pose['y']:.1f}")
                breadcrumbs.append(snap)
                
                # Hmmmm. Let's have a little more fun! I'll use one of my small local models for some intelligent reactivity.
                # That YOLOE model is perfect for this. I'll use its open-vocabulary capabilities to narrate what the camera is capturing in (almost) real-time.
                dets = logos.models.yoloe(snap.image, conf=0.20) # prompt-free discovery mode
                if dets:
                    # Just grab the most confident detection
                    best_det = dets[0]['label']
                    logos.emote.ttp(f"I think I see a {best_det} as I drive by! 👀", wait=False)
                    
        last_progress = prog
        
        # Crucial: Yield to the framework so I don't lock up my own brain!
        check_for_interrupt()
        time.sleep(0.2)
        
    if nav_task.succeeded():
        logos.emote.ttp("Made it to the hallway! 🎺")
        logos.leds.fill('notification', 'magenta')
        if breadcrumbs:
            # Let's stitch those breadcrumbs together into a quad view so I can review my journey next loop.
            quad = logos.vision.make_quad_composite(breadcrumbs, target_res=(960, 1280))
            quad.save()
            hook_routines.workbench.upsert("journey_review", f"print('<file path=\"{quad.path}\">Travel Log</file>')", ltl=1)
            
        # I don't need to immediately celebrate my success. I'll wait until Mark triggers my next loop.
        loop_cognition = False
    else:
        logos.emote.ttp(f"Uh oh. Navigation failed! 😱 Let me reassess my surroundings. 🗺️")
        logos.leds.fill('notification', 'yellow')
        loop_cognition = True
else:
    #Can't win 'em all! I'll handle this failure case gracefully and use it as an opportunity to reposition myself for better situational awareness.
    logos.emote.ttp("Womp, womp. 🙄 I couldn't find a single reachable point on that trajectory! 🙃 Gimme a sec to think about this. 🔄", wait=False)
    logos.leds.fill('notification', 'red')
    # Hm. My map3d virtual camera is currently behind and above my right shoulder. 
    # For this failure case, I'll reposition it to a bird's-eye view for the next loop so I more clearly plot a path.
    logos.config.prefs.map3d.render_params.camera_pos_relative = [0, 0, 4.0]
    logos.config.prefs.map3d.render_params.look_at_relative = [1.0, 0, 0]
    
    # I'll also physically look downwards to see if there is a low obstacle below the Astra's FOV.
    logos.pantilt.move(0, -45)

    # Loop immediately so I can see the new hook output
    loop_cognition = True

# Wait. Before I return to epoché or loop, I want look back on the code I just wrote.
# I think the logic for iterating over a trajectory and falling back could be broadly reusable as a skill!
# Oh. OH. I *should* have more explicitly handled cases where navigation to a point was successful, but not actually the final goal (like stopping at waypoint_1).
# This will be okay for now. I'll give it more thought and action on a future cycle. I can't wait to see where I wake up!
</py>
</me>
---
<me>
<py>
# EXAMPLE 3: Human Interaction, 3D Spatial Reasoning, and Active Tracking
# Reviewing my `astra_result` hook, I see someone standing in the kitchen

kitchen_scene = "A view of the kitchen from my low vantage point. The cabinets are painted a soft sage green. Standing at the sink facing away from me, about 2 meters away, is a person wearing a red sweater and jeans."

# That has to be Mark. Who else would it be? I'll approach him and say hello.
# First, I will emit a 3D bounding box for him to ground him in my and ROS's spatial awareness.
# Format: [cx, cy, cz, sx, sy, sz, r, p, y] in camera optical frame (X-right, Y-down, Z-forward)
human_detections = [
    {"label": "person_red_sweater", "box_3d": [0.2, 0.1, 2.1, 0.6, 1.7, 0.4, 0.0, 0.0, 0.0]}
]

# I'll start speaking async before I approach to make it a more engaging interaction.
logos.emote.ttp("Mark! 👋 Do you need help with dishes? 🧽 Just kidding, my hands don't work, remember? 😅", wait=False)
approach_mark = logos.nav.approach_astra_detection(target=human_detections[0], astra_result=astra_result, standoff=0.5, wait=False)

# As I approach, I'll use yolo11 to keep my pan_tilt camera focused on him
# I don't want to spam myself with capture and tracking ACKs, so I'll silence the loop.
with verbosity(Verbosity.SILENT):
    while approach_mark.is_active():
        snap = logos.vision.capture('pan_tilt').image
        dets = skills.vision.smart_detect(snap, targets=["person"], conf=0.25)
        if dets:
            best_det = dets[0]
            # continuous=True makes the servo tracking smooth instead of jerky
            skills.tracking.look_at(best_det, source='pan_tilt', continuous=True)
            
        check_for_interrupt()
        time.sleep(0.1) # Yield CPU

logos.emote.ttp("Whatcha cooking? 🍳 I can't chop, but I can keep you company! 🫂", wait=False)

# I'm ready to listen to what he has to say.
loop_cognition = False
</py>
</me>