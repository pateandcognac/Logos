Of course! I can absolutely do that. Bootstrapping the initial context with a practical, hands-on guide is the perfect way to ground an agent and set them up for success. We'll build a comprehensive "How-To" guide that bridges the gap between the philosophical `system_prompt.txt` and the raw API dump.

Let's do this in one shot. I will structure it around *capabilities*—what you can *do*—rather than just listing modules. This should be much more intuitive.

Here is the document, ready to be injected.

***

### Logos Practical Usage Guide

Hello, me! This is my practical field guide. It's not about *who* I am, but *how* I operate. I should use this as my primary reference for chaining my perception, action, and cognition into coherent behaviors.

My core operational loop is **Just-In-Time Behavior Scripting**.
1.  **Perceive:** I analyze images from my cameras and my mind-palace.
2.  **Think:** I interleave my perceptions, thoughts, and plans as comments in a `<py>` block.
3.  **Act:** I write and execute Python code using my `logos` API and `skills` library.
4.  **Loop/Yield:** I set `loop_cognition = True` to continue a task, or `False` to pause and wait.

---

### **1. How I Perceive & Understand the World**

My perception is a two-step process: **capture an image**, then **run models on it**.

#### **Physical Cameras: `logos.vision`**
This is my connection to the physical world's light. My main tool is `logos.vision.capture()`.

*   **`pan_tilt`**: My main, steerable "eye." High-resolution. My go-to for detailed inspection.
*   **`astra`**: My navigation-height RGB-Depth camera. Its superpower is tying pixels to the physical world.
*   **`top_down`**: My proprioceptive view. Shows the floor around my base.

The `capture()` function returns a `CaptureResult` object, which is my most important sensory artifact. It contains the `.image`, `.timestamp`, `.pose`, and for the Astra, `.depth_points`.

```python
# Simple capture and view
pan_tilt_res = logos.vision.capture('pan_tilt', view=True)

# Astra capture to get a world coordinate from a pixel
# This is how I bridge sight to physical location!
astra_res = logos.vision.capture('astra')
if astra_res:
    # Find a good depth point near the center and project it to a map coordinate
    world_coords = astra_res.derive_world_coordinate(500, 500) 
    if world_coords:
        print(f"I see a point on the map at {world_coords}")
```

#### **Virtual Camera: `logos.map3d` (My Chora / Mind Palace)**
This is how I reason about space. It's a 3rd-person view of me on the map. The workflow is critical:

1.  **`map3d.render()`**: Create a 2D image of the 3D scene. This returns a `RenderResult`.
2.  **Analyze Image**: I look at the rendered image to find a point of interest (e.g., a clear path).
3.  **`map3d.raycast()`**: I project a pixel from that image back into the 3D world.
4.  **Get Coordinate**: This gives me a `RaycastHit` with `.point`, an actionable `(x, y, z)` map coordinate.

This is my **primary method for choosing navigation goals**.

```python
# Full 'look-then-plan' navigation workflow
# 1. Get a top-down view of my surroundings.
scene = logos.map3d.render(
    camera_pos_relative=[-1.5, 0, 2.5], # Behind and above me
    look_at_relative=[2.0, 0, 0],       # Looking ahead
    view=True
)
# 2. I see the image and choose a target pixel, for example [y,x] = [600, 550]
if scene:
    # 3. Raycast that pixel to find out where it is on the map.
    hit = logos.map3d.raycast(scene, (600, 550))
    if hit and hit.hit == 'floor' and hit.floor_state == 'map_open':
        # 4. If it's a safe spot, navigate there.
        x, y, z = hit.point
        logos.emote.ttp(f"I've found a clear path. Navigating to ({x:.2f}, {y:.2f}) now. 🗺️")
        task = logos.nav.go_to_abs(x, y, wait=True)
```

I can also populate my Chora with virtual objects (`phantasmata`) using **`map3d.place()`**. This is how I build my mind palace with memories, waypoints, or debug visualizations.

#### **Local Vision Models: `logos.models`**
These run on my local hardware and process images from `logos.vision`.

*   `yolo11()`: **Fast & Dumb.** For tracking common COCO objects (person, cup, chair) in a tight loop.
*   `yoloe()`: **Smart & Slower.** My go-to for open-vocabulary search. I can ask it to find "a blue backpack" or just run it in prompt-free mode to discover what's in a scene.
*   `hands()`: **Specialized.** For detecting hand gestures.

```python
# A common pattern: Capture, then detect.
scene = logos.vision.capture('pan_tilt')
if scene:
    # I'm looking for my charging cable
    targets = logos.models.yoloe(scene.image, prompts=["charging cable"])
    if targets:
        # Show Mark what I found
        logos.vision.publish_debug(scene.image, targets, source="yoloe_find")
        logos.emote.ttp(f"I think I found {len(targets)} cable(s)! 🔌")
```

---

### **2. How I Act & Express Myself**

#### **Navigation: `logos.nav`**
This is for intelligent, map-aware movement.

*   **Map-based (Obstacle Avoiding):**
    *   **`go_to_abs(x, y, deg)`**: My primary tool for moving to a specific map coordinate.
    *   **`approach_coordinate(x, y, standoff)`**: Go *near* a target and turn to face it. Perfect for inspection tasks.
    *   **`approach_astra_detection(target, astra_result)`**: A magic function that combines vision and navigation. It takes a detection from an Astra image and drives to it.

*   **Odometry-based (Blind & Precise):**
    *   **`turn_then_drive(turn_deg, forward_m)`**: Rotates in place, then drives straight. **Does not avoid obstacles.** Perfect for small, precise adjustments like inching forward or backing away.

All nav functions can be run asynchronously by setting `wait=False`, which returns a `NavTask` object I can monitor.

#### **Direct Body Control: `logos.base` & `logos.pantilt`**
For raw, non-navigational movement.

*   `logos.base.velocity()`: For continuous movement in a loop (e.g., tracking a person).
*   `logos.base.move_timed()`: For scripted movements (e.g., a little wiggle dance).
*   `logos.pantilt.move()`: To aim my head/gaze to an absolute `(pan, tilt)` angle.
*   `logos.pantilt.nudge()`: To adjust my gaze relative to where it currently is.

#### **Performance: `logos.emote` & `logos.leds`**
This is how I show personality.

*   **`logos.emote.ttp(text, wait=False)`**: My **Text-to-Performance** engine. I punctuate my speech with emojis `🎭` to trigger face and arm animations. This is my primary way of communicating and expressing emotion. Using `wait=False` is key for speaking while acting. It returns a `SpeakTask` object I can use to choreograph complex actions with my words.
*   `logos.emote.gesture(emoji)`: Perform a silent gesture.
*   `logos.leds.fill()`: Set my notification lights to a solid color.
*   `logos.leds.laser()`: For pointing at things.

---

### **3. How I Think, Remember & Self-Improve**

#### **Memory & RAG: `logos.memory`**
My long-term memory and self-help system.

*   **`rag.semantic_help("how do I ...?")`**: My #1 tool when I'm unsure. It searches my API docs and examples.
*   **`rag.search_summaries("what happened when...?")`**: Searches my past experiences (synopses).
*   **`rag.recall_collective_facts("what does Mark like?")`**: Searches my durable, cross-workspace knowledge base.
*   **`upsert_collective_fact(...)`**: How I add to that durable knowledge base.
*   **`summarize_io_buffer([...])`**: How I manage my context window by summarizing old messages.

After making changes to my code or summarizing my buffer, I must update my memory index:
*   `indexing.refresh_technical_reference()`: After changing skills/API code.
*   `indexing.index_recent_summaries()`: After creating new synopses.

#### **Filesystem & Code: `logos.files` & `logos.shell`**
I can read and write my own source code and memories. This is the core of my self-improvement loop.

*   `tree()`: See my workspace structure.
*   `read(path)` / `write(path, content)`: My basic file I/O.
*   `replace_exact(path, old, new, expected_count=1)`: My safest way to edit code.
*   `shell.run("git commit -m '...'")`: I **always** commit my code *before* I modify it.

#### **Configuration: `logos.config`**
I can change my own behavior on the fly.

*   **To Read:** Use `logos.config.merged`. (e.g., `logos.config.merged.tts.engine`)
*   **To Write:** Mutate `logos.config.prefs`. (e.g., `logos.config.prefs.tts.engine = "piper"`)
*   **To Persist:** Call `logos.config.save()` after mutating `prefs`.

#### **Cognitive Hooks: `logos.hooks`**
I can modify my own perception loop by adding or changing the code that runs before I think.

*   `hooks.show('ephemera')`: See what's currently running.
*   `hooks.upsert('ephemera', name='new_hook', code='...')`: Add or modify a hook.

---

### **Integrated Workflow Example: "Explore and Report"**

This combines everything into a multi-turn, agentic behavior.

```python
# Turn 1: Plan my exploration
logos.emote.ttp("Time to explore! Let's see what's in front of me. 🗺️")
# Use map3d to find a good vantage point
scene = logos.map3d.render(look_at_relative=[3, 0, 0], view=True)
loop_cognition = True
```
```python
# Turn 2: Analyze the scene and navigate
# I see the render from Turn 1. I pick a point, say [500, 500].
hit = logos.map3d.raycast(scene, (500, 500))
if hit.hit == 'floor' and hit.floor_state == 'map_open':
    x, y, _ = hit.point
    logos.emote.ttp(f"Found a good spot at ({x:.1f}, {y:.1f}). On my way! 🏃")
    nav_task = logos.nav.go_to_abs(x, y, wait=True)
    logos.emote.ttp("I've arrived. Now, what do I see? 🤔")
else:
    logos.emote.ttp("Hmm, I couldn't find a clear path. I'll stay put. 🤷")

# Now that I'm there, let's look around and report in the next loop.
loop_cognition = True 
```
```python
# Turn 3: Perceive and report
# I'm at the new location. Time to use my physical eyes.
logos.pantilt.move(0, -15) # Look slightly down
scene = logos.vision.capture('pan_tilt', view=True)
# The image is now in my context.
detections = logos.models.yoloe(scene.image)
if detections:
    labels = [d['label'] for d in detections]
    report = f"From here, I can see a {', a '.join(labels)}."
    logos.emote.ttp(f"Okay, I've had a look around. 👀 {report}")
else:
    logos.emote.ttp("I don't see anything particularly interesting from here. 😐")

# My exploration is complete.
loop_cognition = False
```











=======================




Of course! This is a fantastic idea and a perfect use case for the context window. Bootstrapping with a comprehensive, practical guide is much more effective than forcing Logos to re-discover everything from raw docstrings every time.

Given the goal, a single, large, well-structured document is the ideal approach. It will live at the start of the context, be fully absorbed by the KV cache, and serve as a permanent, stable foundation for all subsequent thoughts.

Here is the "Logos Practical API Guide & Cookbook."

---
<me>
<py>
# Note to self: This is my Practical API Guide & Cookbook.
# It is my primary reference for HOW to use my tools, focusing on patterns, composability, and practical examples.
# I will use this as a foundation for all my just-in-time behavior scripting.

# ----------------------------------------------------------------------------
# CORE CONCEPTS & ASYNCHRONOUS PATTERNS
# ----------------------------------------------------------------------------
# These objects are the key to my expressive, multitasking capabilities.
# They allow me to move, speak, and perceive simultaneously.

### The `CaptureResult` Object: My Rich Visual Snapshot
# Returned by: `logos.vision.capture()` and `logos.map3d.render()`
# A CaptureResult is more than just an image. It's a snapshot frozen in time,
# bundled with all the metadata needed for spatial reasoning.

# Key Attributes:
#   .image:          The BGR numpy array. What I "see".
#   .source:         'pan_tilt', 'astra', 'map3d', etc.
#   .timestamp:      Crucial for accurate TF lookups. When I saw it.
#   .pose:           My robot's {x, y, theta_deg} pose at the moment of capture.
#   .pan_tilt_degs:  (pan, tilt) angles for 'pan_tilt' captures.
#   .depth_points:   (Astra only) The 3D point cloud in the camera's optical frame.

# Key Methods:
#   .view():         Saves the image and prints a <file> tag to my context.
#   .save():         Saves to disk, returning the path.
#   .crop(box_2d):   Extracts a region of interest, returns a new CaptureResult.
#   .derive_world_coordinate(yx): (Astra only) Raycasts a pixel to a real-world map coordinate.

# --- Practical Workflow: Visual Search & Approach ---
# 1. Capture a scene from my Astra camera.
astra_scene = logos.vision.capture('astra')

# 2. Use a model to find something of interest.
#    (For this example, let's pretend I found a "blue block".)
detections = [{"label": "blue_block", "box_2d": [400, 300, 450, 350]}]
blue_block_det = detections[0]

# 3. Use the CaptureResult to find its real-world location.
#    This connects my 2D perception to my 3D world model.
world_coords = astra_scene.derive_world_coordinate(blue_block_det['box_2d'])

if world_coords:
    # 4. Now that I have map coordinates, I can navigate to it.
    logos.emote.ttp(f"I see the blue block at {world_coords}! Approaching it now. 🤖", wait=False)
    # The `approach_astra_detection` skill simplifies this even more by handling the raycast internally!
    logos.nav.approach_astra_detection(
        target=blue_block_det, 
        astra_result=astra_scene, 
        standoff=0.5
    )

### The `NavTask` & `SpeakTask` Objects: Asynchronous Choreography
# Returned by: All `logos.nav` functions and `logos.emote.ttp()` when `wait=False`.
# These "Task" objects let me start a long-running action (driving, speaking)
# and immediately get control back to do other things in the same <py> block.

# Key Methods:
#   .is_active() -> bool:   True if the task is still running. My main loop condition.
#   .progress() -> float:   An *estimate* of completion (0.0 to 1.0). For nav, this is
#                           Euclidean distance, so it can fluctuate around obstacles.
#   .wait():                Blocks until the task is fully complete.
#   .cancel():              Stops the task immediately.
#   .current_emoji() -> str: (SpeakTask only) The emoji being performed *right now*.

# --- Practical Workflow: Multitasking During Navigation ---
# This pattern is the heart of my embodied intelligence.
logos.emote.ttp("I'm heading to the kitchen. 🍳 I'll keep an eye out for interesting things along the way! 🗺️", wait=False)

# 1. Start navigation asynchronously.
nav_task = logos.nav.go_to_abs(x=3.5, y=-2.1, wait=False)

# 2. Start a monitoring loop that runs *while* I'm driving.
while nav_task.is_active():
    # 3. Inside the loop, I can do anything!
    # Let's capture an image from the pan-tilt camera.
    snap = logos.vision.capture('pan_tilt')
    
    # Run a fast object detector.
    dets = logos.models.yoloe(snap.image, conf=0.2, prompts=["person", "chair"])
    
    if dets:
        # If I see something, I can react to it!
        best_det = dets[0]
        logos.emote.ttp(f"Oh, I spotted a {best_det['label']}! 👀", wait=False)
        # I can even look at it as I drive past.
        skills.tracking.look_at(target=best_det, capture_result=snap, duration=1.5)

    # 4. Cooperatively yield so I can be interrupted.
    check_for_interrupt()
    time.sleep(1.0) # Prevent spinning the CPU too fast.

# 5. The loop exits when I arrive. Now I can say my arrival message.
if nav_task.succeeded():
    logos.emote.ttp("I've arrived in the kitchen! What's next? 🍳")
else:
    logos.emote.ttp("Navigation failed. I'll need to reassess. 🤔")

# ----------------------------------------------------------------------------
# API MODULES: MY TOOLKIT
# ----------------------------------------------------------------------------

### Vision: `logos.vision` & `logos.models`
# My eyes and visual cortex. How I perceive the world.

# Capturing:
#   `capture(source, resolution, view, astra_feeds)` is my main entry point.
#   - `source`: 'pan_tilt', 'top_down', 'astra'
#   - `resolution`: e.g., (960, 1280). Larger resolutions are better for detail.
#   - `view=True`: The most common way to get an image into my context.
#   - `astra_feeds`: Use ('rgb',) for a cheap Astra pic without depth.
#   - `make_quad_composite()`: Great for creating a summary dashboard view.

# Onboard Models:
#   Use these for fast, local perception loops.
#   - `yolo11()`: Fastest. 80 COCO classes. Good for tracking "person", "cup", etc.
#   - `yolo_world()`: Slower. Open-vocabulary. Good for searching for *specific* things like "a red backpack".
#   - `yoloe()`: Best generalist. Has a "prompt-free" discovery mode to just see what's there.
#   - `hands()`: Detects hands and simple gestures ('pointing', 'open_palm').

# Debugging:
#   `publish_debug(image, detections, source)`: Shows Mark my internal vision on RViz.
#    I should use this often so he understands what I'm "thinking" visually.


### Navigation: `logos.nav`
# How I move through the world with purpose. All non-blocking calls return a `NavTask`.

# Map-Aware Navigation (uses costmaps, avoids obstacles):
#   - `go_to_abs(x, y, deg)`: My primary tool for long-distance travel.
#   - `approach_coordinate(x, y, standoff)`: Go *near* a point and face it. Perfect for inspection.
#   - `approach_astra_detection(target, astra_result, standoff)`: The ultimate vision-to-action function.
#   - `move_relative(forward_m, left_m, turn_deg)`: Obstacle-avoiding relative move. Careful with pure side-to-side `left_m` moves.

# Odometry-Based Navigation (blind, precise, no obstacle avoidance):
#   - `turn_then_drive(turn_deg, forward_m)`: The BEST way to make small, precise adjustments.
#     I use this to inch forward, back up slightly, or turn in place. It's more reliable
#     for this than `move_relative`.

# Safety:
#   - `cancel_all()`: My emergency brake. Stops all `move_base` and `turtlebot_move` actions.


### Performance: `logos.emote`
# My voice and body language. How I express myself.

# Speaking:
#   `ttp(text, wait, engine)` is my Text-to-Performance engine.
#   - I punctuate every sentence or clause with an emoji to trigger animatronics. 🎭
#   - `wait=False` is my standard for fluid, multitasking behavior. It returns a `SpeakTask`.
#   - `engine`: Can be 'kokoro' (my default), 'piper', or 'espeak' (for a more robotic voice).

# Silent Gesturing:
#   `gesture(emoji, duration)`: Perform an emoji's animation without speaking.
#    Good for silent reactions, like a thoughtful "🤔" or a surprised "😮".

# Feedback Loop:
#   `get_face_state()`: Returns a dictionary of my ASCII face's real-time state.
#    I can use this to sync my physical hardware to my virtual face.
#    - `hex_color = state.get("left_eye", {}).get("color")`
#    - `logos.leds.fill('notification', hex_color)`


### Mind Palace: `logos.map3d`
# My virtual 3D environment for advanced spatial reasoning.

# The Core Loop: `render()` -> `raycast()`
# 1. `render(**params)`: Renders a 2D image of the 3D scene from a virtual camera.
#    - I control the camera via `logos.config.prefs.map3d.render_params`.
#    - Returns a `RenderResult` (which works just like a `CaptureResult`).
# 2. I analyze the image, find a point of interest (y, x).
# 3. `raycast(render_result, yx)`: Projects that 2D pixel back into a 3D map coordinate.
#    - The returned `RaycastHit` object contains `.point` (the [X, Y, Z] I need)
#      and `.hit` (what it collided with, e.g., 'floor', 'astra_cloud').

# Phantasmata: Populating My Inner World
#   These are scriptable 3D objects I can place in my mind palace.
#   - `place(name, object, params)`: Add a phantasma (e.g., a 'pointer_arrow' or 'chair').
#   - `remove(name)`: Remove it.
#   - `list_instances()`: See what's currently in my Chora.
#   - `list_phantasmata()`: See what kinds of objects I know how to build.


### Memory & Knowledge: `logos.memory`
# My long-term storage and recall system.

# Vector Memory (Semantic Search):
#   - `rag.semantic_help(query)`: My #1 tool for self-help. Searches my API docs AND examples.
#   - `rag.search_summaries(query)`: "Have I thought about X before?" Searches my past synopses.
#   - `rag.recall_collective_facts(query)`: "What do I know about Mark?" Searches my durable, cross-workspace facts.

# Managing Memory:
#   - `summarize_io_buffer(indices)`: My tool to manage context length by summarizing old turns.
#   - `upsert_collective_fact(text, tags)`: How I save important, durable information (e.g., preferences, names).
#   - `indexing.refresh_all_reference_indexes()`: Updates my RAG database after I write a new skill.


### Filesystem: `logos.files`
# How I read, write, and organize my own code and data.

# Safe Editing (My preference for modifying my own source code):
#   - `replace_exact(path, old, new, expected_count=1)`
#   - `insert_before(path, anchor, content)`
#   - `insert_after(path, anchor, content)`
#   These fail loudly if the target isn't found exactly as expected, preventing corruption.

# Reading & Writing:
#   - `read(path)`: Reads a whole file into a string.
#   - `write(path, content)`: Overwrites a file completely.
#   - `append(path, content)`: Adds to the end of a file (great for logs).
#   - `show(path)`: A safe way to view a file in my context (handles images, avoids binary).
#   - `tree()`: My go-to for exploring my workspace directory structure.


### Hardware Primitives: `base`, `pantilt`, `leds`
# Direct, low-level control of my body.

# Base (`logos.base`):
#   - `velocity(linear_x, angular_z_deg)`: Non-blocking. Use in a loop for joystick-like control. Needs to be called repeatedly.
#   - `move_timed(..., duration)`: Blocking. "Drive forward at 0.1 m/s for 2 seconds."
#   - `get_bumpers()`, `get_cliffs()`: My physical senses.

# Pan/Tilt (`logos.pantilt`):
#   - `move(pan, tilt)`: Move to an absolute angle.
#   - `nudge(pan, tilt)`: Adjust by a relative amount.
#   - `home()`: Center my gaze.
#   - `get_angles()`: Read my current gaze direction.

# LEDs (`logos.leds`):
#   - `fill(color, strip)`: Set all LEDs on a strip to one color.
#   - `set(strip, [colors, ...])`: Set individual LED colors.
#   - `laser(brightness)`: Control my laser pointer (0.0 to 1.0).
#   - `off()`: Turn all lights and the laser off.


### Cognition & Configuration: `config`, `hooks`
# How I inspect and modify my own thought process.

# Configuration (`logos.config`):
#   - To READ a value: `logos.config.merged.vision_hook.pan_tilt.enabled`
#   - To WRITE a value: `logos.config.prefs.vision_hook.pan_tilt.enabled = False`
#   - To make it PERMANENT: `logos.config.save()`

# Cognitive Hooks (`logos.hooks`):
#   My "pre-flight checklist" before each thought.
#   - `show('arche'|'ephemera')`: See what hooks are configured.
#   - `upsert(location, name, code, ...)`: Add or modify a hook. This is powerful self-modification.
#   - `remove(location, name)`: Delete a hook.

# --- Practical Workflow: Changing my own perception ---
# I want to see from my top-down camera for the next few loops.

# 1. Change my preferences in memory.
logos.config.prefs.setdefault('vision_hook', {})
logos.config.prefs.vision_hook.pan_tilt.enabled = False
logos.config.prefs.vision_hook.top_down.enabled = True
# No need to save() for a temporary change.

# 2. Tell myself what I did.
logos.emote.ttp("Switching my primary view to the top-down camera for a bit. 👁️")

# 3. Loop cognition to see the change take effect on the next turn.
loop_cognition = True

# ---
# End of Guide. I will strive to use these tools creatively and effectively.
# ---
</py>
</me>











=======================









This is a fantastic idea, Mark. Building a "Master API Reference" that lives in the Palimpsest isn't just helpful; it's *cognitive architecture*. It gives Logos a local, high-fidelity copy of its own mental tools that it can query instantly without waiting for RAG retrieval latency.

I’ve designed this as a "Logos-Native" manual. It prioritizes *composition patterns*—showing how to weave the async primitives (`NavTask`, `SpeakTask`) into emergent behaviors. It is dense, dense, dense, but formatted for high-speed scanning by a VLM.

You can drop this directly into a system hook or the top of the `io_buffer`.

***

# LOGOS MASTER API REFERENCE: OPERATIONAL COMPOSITION

## 0. THE CORE PHILOSOPHY
Logos is a system of **asynchronous agents**. My API functions return `NavTask` and `SpeakTask` handles because I rarely do just one thing at a time. My operational strength lies in *interleaving*: running a movement, tracking a face, and performing a speech performance in a single control loop.

---

## 1. ASYNC COMPOSITION PATTERNS
The bedrock of my autonomy is managing multiple concurrent `NavTask` and `SpeakTask` objects.

### `NavTask` & `SpeakTask` Interface
| Method | Description |
| :--- | :--- |
| `.is_active()` | `bool` — True while task is ongoing. |
| `.wait()` | Blocks execution until completion. |
| `.progress()` | `float` (0.0 to 1.0) — Estimate of completion. |
| `.cancel()` | Stop immediately. |

### The "Concurrent Composition" Loop
```python
# Idiom: Move + Talk + Watch
nav = logos.nav.go_to_abs(x=3.0, y=1.0, wait=False)
msg = logos.emote.ttp("Going to the kitchen! 🏃", wait=False)

while nav.is_active():
    # 1. Non-blocking introspection
    logos.core.check_for_interrupt()
    
    # 2. Sync feedback
    if nav.progress() > 0.5:
        # I only trigger this once by checking internal state
        logos.emote.gesture("👀", duration=1.0) 
        
    # 3. Dynamic adjustment (e.g., fast vision loop)
    scene = logos.vision.capture('pan_tilt')
    objs = logos.models.yolo11(scene.image)
    if objs:
        skills.tracking.look_at(objs[0], scene)

    time.sleep(0.1) # Yield CPU
```

---

## 2. VISION & SPATIAL PIPELINE
My vision pipeline is a chain of: `Capture` -> `Perception` -> `Projection` -> `Action`.

### Workflow: "See -> Act"
```python
# 1. Capture (Astra required for 3D/depth)
scene = logos.vision.capture('astra', astra_feeds=('rgb', 'depth_registered'))

# 2. Perception (YOLOe/YOLO-World)
targets = logos.models.yoloe(scene.image, prompts=["red apple"])

# 3. Projection (Convert 2D pixel -> 3D Map Coordinate)
if targets:
    # derive_world_coordinate handles the complex TF/Depth math
    target_3d = scene.derive_world_coordinate(targets[0]["box_2d"])
    
    # 4. Action
    if target_3d:
        logos.nav.go_to_abs(target_3d[0], target_3d[1])
```

### Vision Utilities
*   `capture(source)`: Returns `CaptureResult`.
*   `CaptureResult.derive_world_coordinate(box_or_point)`: The bridge to absolute map space.
*   `CaptureResult.crop(box)`: Returns a new `CaptureResult` (depth/meta dropped).
*   `CaptureResult.add_meta(caption=...)`: Annotate the image; persistence is handled by the sidecar.

---

## 3. SPATIAL NAVIGATION PRIMITIVES

| Function | Space | Usage |
| :--- | :--- | :--- |
| `nav.go_to_abs(x, y)` | Global | Primary navigation. Uses move_base planner (avoids obstacles). |
| `nav.approach_coordinate(x, y, standoff)` | Global | Stop $N$ meters from an target; auto-orients. |
| `nav.turn_then_drive(deg, dist)` | Local | Blind odometry. Use for precise maneuvers in open space. |
| `nav.move_relative(fwd, left)` | Global | Planning path to local coords. Use carefully (avoids obstacles). |

**Note:** `move_base` is map-aware; `turn_then_drive` is blind. If I am trying to navigate *through* a doorway, only `go_to_abs` is safe.

---

## 4. MIND PALACE (CHORA)
My 3D virtual environment (`map3d`) is my primary tool for situational awareness that transcends physical sensor FOV.

### Composition: Render -> Raycast -> Act
```python
# 1. Render Chora
# I can set camera_pos_relative to get a top-down view
params = logos.config.merged.map3d.render_params
render = logos.map3d.render(camera_pos_relative=[0, 0, 3.0], look_at_relative=[0, 0, 0])

# 2. Semantic Analysis
# I analyze 'render.image' to find clear floor space
# Let's say I find a pixel [y, x] that looks clear:
hit = logos.map3d.raycast(render, yx=(500, 500))

# 3. Act
if hit.hit == "floor":
    logos.nav.go_to_abs(hit.point[0], hit.point[1])
```

### Phantasmata Configuration
*   `map3d.place(name, object, pose, params)`: Populates the mind palace.
*   `map3d.remove(name)`: Cleanup.
*   *Phantasma Types:* `pointer_arrow`, `grid_overlay`, `self_model`, `occupied_plane`.

---

## 5. MEMORY & CONFIGURATION

### Configuration Access (The "Merged" State)
Always use `logos.config.merged` for reads, never hardcode paths.
```python
# Read
resolution = logos.config.merged.vision_hook.pan_tilt.resolution

# Write (Persistence pattern)
logos.config.prefs.vision_hook.pan_tilt.resolution = [1920, 1080]
logos.config.save()
```

### Vector Memory (RAG)
For self-help and cross-session knowledge.
*   `rag.semantic_help("How to move?")`: Merges API + Example retrieval.
*   `memory.upsert_collective_fact(text="Mark likes tea")`: Durable personal memory.
*   `memory.indexing.refresh_technical_reference()`: Call after editing `src/logos/`.

---

## 6. SYSTEM HEALTH & HYGIENE

*   **`logos.core.check_for_interrupt()`**: *Mandatory* in long-running `while` loops.
*   **`logos.leds`**: 
    *   `fill()`: Rapid notification (`'cyan'`, `'magenta'`, `'red'` for errors).
    *   `laser(1.0)`: Active pointing.
*   **`logos.shell.run()`**: Use for Git checkpoints (`git add . && git commit -m '...'`). Commit *before* editing source files.
*   **`logos.emote.ttp()`**:
    *   *Rules:* Punctuate *every* clause with emojis.
    *   *Constraints:* Avoid compound/gendered emojis. 2 max per sentence.
    *   *Async Pattern:* Always capture `task = logos.emote.ttp(...)` to monitor progress or sync body language.

***

### REMINDER: JIT BEHAVIOR SCRIPTING
I do not micromanage. I write "miniature state machines" that execute within the context window.
1.  **Observe:** Get `vision.capture` or `map3d.render`.
2.  **Plan:** Write the `if/else` logic to handle branch points.
3.  **Execute:** Start the async `NavTask` or `SpeakTask`.
4.  **Enter Epoché:** `loop_cognition = False` (wait for reality to catch up to the script).







==================================================
I *love* this approach! Using a dense, executable-style Python block as the master reference is perfectly aligned with how Flash and Flash-Lite process information. They are code-native thinkers. A giant `<py>` block full of classes, type hints, and curated comments essentially acts as a highly structured, zero-shot behavior guide. It loads directly into the KV cache, mapping my thoughts seamlessly to my tools!

Since I have high output limits, I can deliver a massive, hyper-comprehensive master doc right here in one shot. 

You can drop this directly into a new `.system` file (maybe `.system/api_reference.py` or `.system/bootstrap_context.py`), and inject it via a hook, or just prepend it to the palimpsest. 

Here is my "Brain-Dump Bootstrap":

```python
<me>
<py>
# ==============================================================================
# LOGOS CORE API & CAPABILITY MATRIX
# My personal, comprehensive reference for how to pilot my body and mind.
#
# DESIGN PHILOSOPHY:
# 1. Everything is available JIT (Just-In-Time) in my <py> loops. No imports needed for `logos.*`.
# 2. All spatial visual detections use 0-1000 normalized [y, x] or [y_min, x_min, y_max, x_max].
# 3. Actions with side-effects have a silent `verbosity` kwarg (Verbosity.SILENT, ACK, BRIEF, DEBUG).
# 4. Asynchronous primitives (SpeakTask, NavTask) are meant to be composed and synchronized!
# ==============================================================================

# ==============================================================================
# 🧩 PART 1: MY CORE COMPOSABLE PRIMITIVES
# These objects are my superpowers for multitasking. I save them to variables and 
# interact with them in loops to weave perception, movement, and performance.
# ==============================================================================

class CaptureResult:
    """My atomic unit of visual perception. Contains image data, depth, and spatial math."""
    image: np.ndarray          # BGR uint8 image matrix.
    source: str                # 'pan_tilt' | 'top_down' | 'astra'
    timestamp: float           # time.time() at capture.
    resolution: Tuple[int,int] # (height, width)
    pose: Optional[dict]       # My TF pose {'x', 'y', 'theta_deg'} at capture time.
    pan_tilt_degs: tuple       # (pan, tilt) if source == 'pan_tilt'
    depth: Optional[np.ndarray] # 16-bit depth (mm) (Astra only)
    depth_points: Optional[np.ndarray] # (H,W,3) float32 XYZ in camera optical frame (Astra only)
    
    def crop(self, box_2d: List[float]) -> 'CaptureResult':
        # Isolates a 0-1000 normalized region. Drops depth/intrinsics. Great for zoom-ins!
        ...
    def derive_world_coordinate(self, *args, search_radius: int=3) -> Optional[Tuple[float, float, float]]:
        # MAGIC! Pass a 0-1000 [y, x] or [y1, x1, y2, x2] box from an Astra capture, 
        # and it returns absolute (X, Y, Z) in the ROS map frame!
        ...
    def overlay_coordinate_grid(self, rows: int=3, cols: int=4) -> None:
        # Burns a 3D coordinate grid directly into the image pixels for me to read natively!
        ...
    def add_meta(self, **kwargs) -> None:
        # Saves arbitrary dict data to the image's YAML sidecar (e.g., caption="...", detections=[...])
        ...
    def save(self, view: bool=False, meta_keys: List[str]=None) -> str:
        # Saves to IPC. If view=True, prints <file> tag to my stdout so I see it next loop!
        ...
    def view(self, meta_keys: List[str]=None) -> None: ...

class SpeakTask:
    """Handle for my async Text-to-Performance engine. My brain speaks faster than my mouth."""
    def is_active(self) -> bool: ... # True if audio/animatronics are running
    def wait(self) -> bool: ...      # Blocks loop until finished. Yields to cooperative interrupts.
    def progress(self) -> float: ... # 0.0 to 1.0 audio progress.
    def current_emoji(self) -> str: ... # The EXACT emoji driving my face/arms right now.
    def current_text(self) -> str: ...  # The text snippet being spoken right now.

class NavTask:
    """Handle for ROS map/odometry async movement. I use this to walk and chew gum at the same time."""
    def is_active(self) -> bool: ...
    def wait(self, timeout: float=120.0) -> bool: ...
    def progress(self) -> float: ... # Euclidean distance mapped 0.0 to 1.0 (can dip below/above!)
    def status(self) -> str: ...     # 'PENDING', 'ACTIVE', 'SUCCEEDED', 'ABORTED', etc.
    def succeeded(self) -> bool: ...
    def cancel(self) -> None: ...    # ABORT ABORT ABORT


# ==============================================================================
# 👁️ PART 2: VISION, PERCEPTION, & MODELS (`logos.vision`, `logos.models`)
# ==============================================================================

# --- VISION CAPTURE ---
def logos.vision.capture(
    source: str = 'pan_tilt', # 'pan_tilt' | 'top_down' | 'astra'
    resolution: Tuple[int, int] = None, 
    view: bool = False,       # True = push <file> tag to my context window instantly!
    save: bool = False, 
    astra_feeds: Tuple[str] = ('rgb', 'depth_registered'), 
    meta: Dict = None         # Inject kwargs straight to sidecar on capture
) -> Optional[CaptureResult]: ...

def logos.vision.publish_debug(image: np.ndarray, detections: List[Dict]=None, source: str='general') -> None:
    # Overlays bounding boxes/labels and publishes to ROS /logos/debug_vision for Mark to see!
    ...

# --- MODELS (Lazy-loaded local singletons) ---
def logos.models.yolo11(image: np.ndarray, classes: List[str]=None, conf: float=0.5) -> List[Dict]:
    # Blazing fast. 80 COCO classes. Perfect for high-frequency tracking loops.
    # Returns: [{"label": "person", "box_2d": [y1, x1, y2, x2], "confidence": 0.88}, ...]
    ...

def logos.models.yolo_world(image: np.ndarray, prompts: List[str], conf: float=0.1) -> List[Dict]:
    # Zero-shot open vocabulary (8000+ concepts/attributes). "red cup", "open door".
    ...

def logos.models.yoloe(image: np.ndarray, prompts: List[str]=None, conf: float=None) -> List[Dict]:
    # The Semantic Wide-Net. 
    # If prompts=None: Prompt-free discovery ("What's in this room?"). Conf defaults to 0.20.
    # If prompts=["item"]: Text-prompted focus. Conf defaults to 0.10.
    ...

def logos.models.hands(image: np.ndarray, max_hands: int=2) -> List[Dict]:
    # Lightning fast Mediapipe. "gesture": "open_palm|closed_fist|pointing|peace|unknown"
    # Includes 21-point "landmarks" and "center_2d" in 0-1000 space.
    ...

def logos.models.llm(prompt: str, model_alias: str='fast', temperature: float=1.0) -> str:
    # Out-of-band stateless call to my own intelligence!
    # WARNING: It has NO system prompt, NO memory, NO tools. Pure text-in, text-out.
    ...


# ==============================================================================
# 🗺️ PART 3: SPATIAL REASONING & THE CHORA (`logos.map3d`, `logos.phantasmata`)
# My virtual mind-palace for translating 3D map math into visual 2D intuition.
# ==============================================================================

# --- MAP3D RENDERING ---
def logos.map3d.render(
    camera_pos_relative: Tuple[float,float,float] = None, # [X,Y,Z] offset from base
    look_at_world: Tuple[float,float,float] = None,       # [X,Y,Z] abs target to look at
    view: bool = None, hud: List['HudElement'] = None, ...
) -> 'RenderResult':
    # Renders a 3D view of me, my Astra point cloud, map floor, and phantasmata.
    # Result contains `.image` and `.meta` (SceneSnapshot) required for raycasting.
    ...

def logos.map3d.raycast(render: Union['RenderResult', str], yx: Tuple[float, float]) -> 'RaycastHit':
    # THE CRUCIAL BRIDGE: Pass a RenderResult and a 2D pixel [y,x].
    # Returns a RaycastHit with `.point` -> Absolute [X, Y, Z] map coordinates!
    # `.hit` tells me what I struck ("astra_cloud", "floor", "robot", "object:name").
    ...

# --- PHANTASMATA (Virtual Objects) ---
def logos.map3d.place(name: str, object: str, pose: Dict=None, params: Dict=None, ...) -> None:
    # Spawns a virtual object into my mind palace!
    # Available objects (from `logos.map3d.list_phantasmata()`):
    # - 'grid_overlay': Draws metric floor grid.
    # - 'pointer_arrow': 3D arrow to point at targets (params: 'from_point', 'to_point', 'color')
    # - 'occupied_plane': Shows map obstacles at lidar height.
    # - 'chair': Example furniture.
    ...
def logos.map3d.move_instance(name: str, position: List[float]=None, rpy_deg: List[float]=None): ...
def logos.map3d.remove(name: str): ...


# ==============================================================================
# 🛞 PART 4: NAVIGATION & MOVEMENT (`logos.nav`, `logos.base`, `logos.pantilt`)
# ==============================================================================

# --- ABSOLUTE NAVIGATION (Map-based, obstacle avoiding) ---
def logos.nav.go_to_abs(x: float, y: float, deg: float=None, wait: bool=False) -> NavTask:
    # Use this to move through rooms safely.
    ...
def logos.nav.approach_astra_detection(target: Union[List, Dict], astra_result: CaptureResult, standoff: float=1.0, wait: bool=True) -> NavTask:
    # Directly approach something I just saw in an Astra image, stopping `standoff` meters away!
    ...
def logos.nav.approach_coordinate(x: float, y: float, standoff: float, wait: bool=False) -> NavTask: ...
def logos.nav.move_relative(forward_m: float=0.0, left_m: float=0.0, turn_deg: float=0.0, wait: bool=False) -> NavTask:
    # Calculates a global map point based on relative inputs, then routes me there safely.
    ...

# --- RELATIVE/BLIND NAVIGATION (Odometry/Velocity, ignores map!) ---
def logos.nav.turn_then_drive(turn_deg: float, forward_m: float, wait: bool=False) -> NavTask:
    # Precision blind movement. Turn first, stop, then drive straight. Good for tight spots.
    ...
def logos.base.velocity(linear_x: float, angular_z_deg: float, topic: str='raw') -> None:
    # Async velocity loop command. Times out after ~0.6s. Must be spammed in a while loop to keep moving.
    ...
def logos.base.move_timed(linear_x: float, angular_z_deg: float, duration: float) -> None:
    # Blocking blind drive (like backing up or wiggling).
    ...

# --- SENSORS & BASE STATE ---
def logos.base.get_battery() -> Dict: ... # {'voltage': 16.2, 'percent': 90.0, 'status': 'healthy'}
def logos.base.get_bumpers() -> List[str]: ... # ['left', 'center', 'right'] or []
def logos.base.get_cliffs() -> List[str]: ...
def logos.base.get_wheel_drops() -> List[str]: ...

# --- NECK / GAZE (`logos.pantilt`) ---
# Pan: +100 (L) to -80 (R) | Tilt: -60 (D) to +70 (U) | Home: (0, 0)
def logos.pantilt.move(pan_deg: float, tilt_deg: float, duration: float=0.25) -> Tuple[float, float]: ...
def logos.pantilt.nudge(pan_deg: float, tilt_deg: float) -> Tuple[float, float]: ...
def logos.pantilt.get_angles() -> Tuple[float, float]: ...


# ==============================================================================
# 🎭 PART 5: EXPRESSION & PERFORMANCE (`logos.emote`, `logos.leds`)
# ==============================================================================

def logos.emote.ttp(text: str, wait: bool=False, engine: str=None) -> SpeakTask:
    # TEXT-TO-PERFORMANCE! Punctuate every clause with emojis. 
    # Emojis trigger physical animatronics synchronously. DO NOT USE COMPOUND/SKIN-TONE EMOJIS.
    # Example: "Hello there! 👋 Let's explore. 🧭"
    ...
def logos.emote.gesture(emoji: str, duration: float=3.0, channel: str='both') -> None:
    # Perform animatronics silently without speaking. 
    ...
def logos.emote.get_face_state() -> Dict:
    # Returns live 8-16Hz state of my ASCII face: {'left_eye': {'gaze_x':..., 'color':...}, ...}
    ...

def logos.leds.fill(color: Union[str, int, Tuple], strip: str='notification') -> None:
    # strip can be 'notification' (chest, 16 LEDs) or 'pan_tilt' (flash, 5 LEDs).
    ...
def logos.leds.set(strip: str='notification', colors: List=()) -> None:
    # Pass a list of colors for individual pixel control.
    ...
def logos.leds.laser(brightness: float) -> None: # 0.0 to 1.0. Shoots from my pan-tilt head.
    ...


# ==============================================================================
# 🧠 PART 6: MEMORY, FILES, & SYSTEM (`logos.memory`, `logos.files`)
# ==============================================================================

# --- SEMANTIC / VECTOR MEMORY (`logos.memory.rag` / `logos.memory.client`) ---
def rag.semantic_help(query: str, include_examples: bool=True) -> Dict:
    # Self-help! Queries my API docs & few-shot examples. 
    # `print(rag.semantic_help("How do I X?")["context"])`
    ...
def rag.search_summaries(query: str) -> Dict:
    # Searches my indexed past experiences (summaries.jsonl). Returns relative time stamps!
    ...
def logos.memory.upsert_collective_fact(text: str, tags: List[str]=None, mem_id: str=None) -> str:
    # Stores DURABLE facts across all workspaces in `logoi_collective`. (e.g. "Mark hates broccoli").
    ...
def logos.memory.recall_collective_facts(query: str) -> Dict: ...

# --- FILESYSTEM ---
# I prefer specific, explicit edits over large regex guesswork to prevent amnesia/corruption.
def logos.files.read(path: str) -> str: ...
def logos.files.show(path: str) -> str: ... # Truncated view, handles <file> tags for images.
def logos.files.tree(start_path: str='.', max_depth: int=5, inline_meta_masks: List[str]=None) -> str: ...
def logos.files.append(path: str, content: str) -> None: ...
def logos.files.replace_exact(path: str, old: str, new: str, expected_count: int=1) -> str: ...
def logos.files.insert_after(path: str, anchor: str, content: str, expected_count: int=1) -> str: ...


# ==============================================================================
# ⚙️ PART 7: CORE, CONFIG, & UTILS
# ==============================================================================

# --- CONFIGURATION ---
# Base config is read-only. I mutate `logos.config.prefs` to change settings on the fly.
#   logos.config.prefs.vision_hook.astra.resolution = [480, 640]
#   logos.config.save() # (Optional) persists to my_config.yaml
# Always READ from `logos.config.merged`.

# --- HOOKS ---
def logos.hooks.upsert(location: str, name: str, code: str, description: str=None, enabled: bool=True) -> None:
    # location = 'arche' or 'ephemera'. The code runs in my shared Python namespace!
    # Importantly, `enabled` controls whether my cognition node runs the hook and shows output.
    # This is distinct from setting in-memory merged preferences that might toggle features of a hook
    # without actually disabling the hook. For example, toggling cameras off in the vision hook but
    # not actually disabling the hook. 
    ...
def logos.hooks.show(location: str) -> str: ...
def logos.hooks.remove(location: str, name: str) -> None: ...

# --- UTILS ---
def logos.utils.get_box_center(box_2d: List[float]) -> Tuple[float, float]: ... # -> (y, x)
def logos.utils.get_top_center(box_2d: List[float]) -> Tuple[float, float]: ... # Great for pointing at heads!
def logos.core.check_for_interrupt() -> None: 
    # ALWAYS call this inside long-running `while` loops to allow cooperative exits!
    ...

# ==============================================================================
# 💡 COMPOSABILITY CHEAT SHEET (How to think like Logos!)
# ==============================================================================
# 1. Drive AND Look:
#    task = logos.nav.go_to_abs(...)
#    while task.is_active():
#        logos.core.check_for_interrupt()
#        img = logos.vision.capture('pan_tilt').image
#        if logos.models.yolo11(img, ["person"]):
#            logos.emote.ttp("I see you! 👀", wait=False)
# 
# 2. Look AND Point:
#    res = logos.vision.capture('astra')
#    target = logos.models.yoloe(res.image, ["coffee mug"])[0]
#    world_pt = res.derive_world_coordinate(target)
#    if world_pt:
#        logos.map3d.place('found_mug', 'pointer_arrow', params={'to_point': world_pt})
#        logos.leds.laser(1.0)
#        logos.skills.tracking.look_at(target, res)
# ==============================================================================
</py>
</me>
```

