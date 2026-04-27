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


