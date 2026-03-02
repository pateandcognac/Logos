# Logos API Dashboard
A programmatic overview of my capabilities. Use `logos.help(obj)` for deep-dives.

### Global State
    logos.state: Persistent configuration (print it to view as YAML)
    logos.verbosity(level): Context manager to mute/debug output

### Module: logos.base
# My body. This module provides direct access to the Kobuki mobile base.
Functions:
    def get_battery() -> Dict[str, Union[float, str]]: # Read my current battery voltage, percentage, and semantic status.
    def get_bumpers() -> List[str]: # Check if my physical bumpers are currently pressed against an obstacle.
    def get_buttons() -> List[str]: # Check if any physical buttons on my torso are being pressed.
    def get_charger_state() -> str: # Check if I am currently connected to power.
    def get_cliffs() -> List[str]: # Check my downward-facing cliff sensors (stairs, ledges, drop-offs).
    def get_wheel_drops() -> List[str]: # Check if my drive wheels have dropped (meaning I am suspended in the air).
    def stop(topic: str = 'raw') -> None: # Immediately halt all base movement by publishing zero velocities.
    def velocity(linear_x: float, angular_z: float, duration: float, topic: str = 'raw') -> None: # Send raw velocity commands to a raw (default) velocity topic or smoothed and muxed topic for a specific duration.

### Module: logos.map3d
# Logos API Dashboard
A programmatic overview of my capabilities. Use `logos.help(obj)` for deep-dives.

### Global State
    logos.state: Persistent configuration (print it to view as YAML)
    logos.verbosity(level): Context manager to mute/debug output

### Module: logos.base
# My body. This module provides direct access to the Kobuki mobile base.
Functions:
    def get_battery() -> Dict[str, Union[float, str]]: # Read my current battery voltage, percentage, and semantic status.
    def get_bumpers() -> List[str]: # Check if my physical bumpers are currently pressed against an obstacle.
    def get_buttons() -> List[str]: # Check if any physical buttons on my torso are being pressed.
    def get_charger_state() -> str: # Check if I am currently connected to power.
    def get_cliffs() -> List[str]: # Check my downward-facing cliff sensors (stairs, ledges, drop-offs).
    def get_wheel_drops() -> List[str]: # Check if my drive wheels have dropped (meaning I am suspended in the air).
    def stop(topic: str = 'raw') -> None: # Immediately halt all base movement by publishing zero velocities.
    def velocity(linear_x: float, angular_z: float, duration: float, topic: str = 'raw') -> None: # Send raw velocity commands to a raw (default) velocity topic or smoothed and muxed topic for a specific duration.

### Module: logos.map3d
# My 'mind palace.' A virtual 3D environment for advanced spatial reasoning.
Constants:
    HUD_ANCHORS = ('top_left', 'top_center', 'top_right', 'bottom_left', 'bottom_center', 'bottom_right')
    HUD_FONT_DUPLEX = 2
    HUD_FONT_PLAIN = 1
    HUD_FONT_SIMPLEX = 0
    HUD_FONT_SMALL = 6
Classes:
    class Chora: # Stateful renderer + raycaster with persistent ROS subscriptions.
        def load_phantasma(self, name: 'str') -> 'None': # Minimal future-proof loader:
        def raycast(self, render: 'Union[RenderResult, str]', yx: 'Tuple[float, float]', include_floor: 'bool' = True, include_astra: 'bool' = True, include_robot: 'bool' = True, include_objects: 'bool' = True) -> 'RaycastHit': # Projects a 2D pixel from a `map3d` render back into the 3D world.
        def register_object(self, obj: 'SceneObject') -> 'None': # No description.
        def remove_object(self, name: 'str') -> 'None': # No description.
        def render(self, camera_pos_relative: 'Optional[Tuple[float, float, float]]' = (0.0, 0.0, 0.7), camera_pos_world: 'Optional[Tuple[float, float, float]]' = None, look_at_relative: 'Optional[Tuple[float, float, float]]' = (1.0, 0, 0.0), look_at_world: 'Optional[Tuple[float, float, float]]' = None, rpy_deg: 'Optional[Tuple[float, float, float]]' = None, rot_matrix_3x3: 'Optional[Union[np.ndarray, List[List[float]]]]' = None, look_distance_m: 'float' = 2.0, max_cloud_height_m: 'Optional[float]' = None, resolution: 'Tuple[int, int]' = (768, 768), include_robot: 'bool' = True, view: 'bool' = True, save: 'bool' = True, save_dir: 'str' = 'artifacts/map3d', filename: 'Optional[str]' = 'debug.png', cloud_alpha: 'Optional[float]' = None, cloud_density: 'Optional[float]' = None, cloud_opacity: 'Optional[float]' = None, cloud_point_size: 'Optional[float]' = None, laser_scan_show: 'Optional[bool]' = None, laser_scan_center_band_px: 'Optional[int]' = None, laser_scan_color: 'Optional[List[float]]' = None, hud: 'Optional[List[HudElement]]' = None, hud_warnings: 'bool' = True, hud_frame_info: 'bool' = True, hud_stats: 'bool' = False) -> 'RenderResult': # Renders a view of my 3D 'map3d' from my virtual `theoria` camera.
    class HudElement: # A single text element to overlay on a rendered image.
        pass
    class RaycastHit: # Result of raycasting a pixel against a scene snapshot.
        pass
    class RenderResult: # CaptureResult-shaped return for mind-palace rendering.
        def save(self, view: 'bool' = False, path: 'Optional[str]' = None) -> 'str': # No description.
        def view(self) -> 'None': # No description.
    class SceneObject: # An object that can be rendered and/or raycasted.
        pass
    class SceneSnapshot: # Self-contained snapshot of what was rendered, sufficient for later raycasts.
        pass
Functions:
    def get_map3d() -> 'Chora': # No description.
    def raycast(*args, **kwargs) -> 'RaycastHit': # No description.
    def render(*args, **kwargs) -> 'RenderResult': # No description.

### Module: logos.core
# Core functionality for the Logos API, including verbosity management, cooperative interrupt handling, and dynamic help generation.
Classes:
    class Verbosity: # Enumeration for setting API verbosity levels.
        pass
Functions:
    def api_call(default_verbosity: logos.core.Verbosity = <Verbosity.ACK: 1>): # Decorator for public API functions that have side effects or are “actions” from Logos’ POV (movement, IO, memory changes, etc.).
    def check_for_interrupt(): # Checks if an external interrupt has been requested.
    def help(obj: Union[object, NoneType] = None, search: Union[str, NoneType] = None, print_output: bool = True) -> str: # Provides a dynamic, auto-generated help dashboard for my API.
    def verbosity(level: logos.core.Verbosity): # A context manager to temporarily set the verbosity level for API calls.

### Module: logos.exceptions
# Defines core exceptions for my framework.
Classes:
    class Interrupt: # Raised when a cooperative interrupt is requested by an external system.
        def with_traceback(...): # Exception.with_traceback(tb) --

### Module: logos.files
# This module contains all my tools for interacting with the filesystem.
Functions:
    def append(path: str, content: str): # Appends content to the end of a file.
    def read(path: str) -> str: # Reads the entire content of a file.
    def show(path: str, max_chars: int = 2000, pattern: Union[str, NoneType] = None) -> str: # Prints (and returns) a possibly filtered, truncated view of a file.
    def tree(start_path: str = '.', max_depth: int = 3, show_hidden: bool = True, show_extensions: Union[List[str], NoneType] = None, inline_meta_masks: Union[List[str], NoneType] = None, ignore_globs: Union[List[str], NoneType] = None, files_per_dir_limit: int = 50) -> str: # Generates an intelligent, detailed tree view of the filesystem.
    def write(path: str, content: str): # Writes content to a file, overwriting it if it exists.

### Module: logos.hooks
# This module contains functions for me to introspect and modify my own cognitive hook configurations. Does *not* contain the hook code itself.
Functions:
    def remove(location: str, name: str): # Removes a hook from a specified configuration.
    def show(location: str) -> str: # Provides a concise summary of all hooks in a given [location]_hooks_config.yaml file.
    def upsert(location: str, name: str, *, description: Union[str, NoneType] = None, ttl: Union[int, NoneType] = None, code: Union[str, NoneType] = None, insert_before: Union[str, NoneType] = None) -> None: # Update an existing hook or create a new one in the requested configuration.

### Module: logos.leds
# Control for my RGB LED strips and laser pointer.
Functions:
    def fill(strip: str, color: Union[int, Tuple[int, int, int], str]) -> None: # Set all LEDs on a strip to the same color.
    def laser(brightness: float) -> None: # Set the laser pointer brightness.
    def off(strip: Union[str, NoneType] = None) -> None: # Turn off LEDs. If strip is None, turns off ALL strips and the laser.
    def set(strip: str, colors: Sequence[Union[int, Tuple[int, int, int], str]]) -> None: # Set individual LED colors on a strip.

### Module: logos.logos_mesh
# logos.map3d.logos_mesh
Functions:
    def build_logos_mesh() -> "'o3d.geometry.TriangleMesh'": # Build a complete Logos robot mesh at the origin, facing +X (ROS forward).

### Module: logos.memory
# This module contains tools for the current Hypomnemeta (io_buffer.jsonl) and historical records.
Functions:
    def recall(msg_id: str) -> Union[str, NoneType]: # Retrieves the full, original content of a message from the history log.
    def replace_cell_content(cell_index: int, new_content: str): # Directly replaces the content of a single cell in the io_buffer.
    def summarize_io_buffer(cell_indices: List[int], guidance: str = None): # Summarizes specific cells in the io_buffer using a specialized agent.

### Module: logos.models
# Wrappers for interacting with various ML / AI models.
Functions:
    def llm(prompt: str, model_alias: str = 'fast', temperature: float = 0.7) -> str: # A simple wrapper to prompt my core, stateless, LLM intelligence out-of-band. 
    def yolo11(image: numpy.ndarray, classes: Union[List[str], NoneType] = None, conf: float = 0.5) -> List[Dict[str, Any]]: # Run inference using the blazing fast YOLO11 Nano model.
    def yolo_world(image: numpy.ndarray, prompts: List[str], conf: float = 0.1) -> List[Dict[str, Any]]: # Run inference using the YOLO-World open-vocabulary model.

### Module: logos.nav
# Map-aware autonomous navigation.
Classes:
    class NavTask: # A handle for an asynchronous navigation task.
        def cancel(self) -> None: # Stops the robot and cancels this specific goal.
        def is_active(self) -> bool: # Returns True if the robot is currently trying to reach the goal.
        def progress(self) -> float: # Estimates how far along the path the robot is, from 0.0 to 1.0.
        def status(self) -> str: # Returns a human-readable status of the goal (e.g., 'ACTIVE', 'SUCCEEDED', 'ABORTED').
        def succeeded(self) -> bool: # Returns True if the robot successfully reached the goal.
        def wait(self, timeout: float = 120.0) -> bool: # Blocks execution until the goal is reached, fails, or times out.
Functions:
    def cancel_all() -> None: # Panic button. Immediately halts all map-based and relative navigation tasks.
    def go_to_abs(x: float, y: float, theta_deg: Union[float, NoneType] = None, wait: bool = True) -> logos.nav.NavTask: # Navigate to an absolute (x, y) coordinate on the ROS map using move_base.
    def move_relative(forward_m: float, turn_deg: float, wait: bool = True) -> logos.nav.NavTask: # Move a relative distance using odometry (turn first, then drive forward).

### Module: logos.pantilt
# Control for my pan/tilt servo periscope.
Constants:
    HOME = (0.0, 0.0)
    PAN_RANGE = (-80.0, 100.0)
    TILT_RANGE = (-60.0, 70.0)
Functions:
    def get_position() -> Tuple[float, float]: # Read the current pan/tilt position in degrees.
    def home() -> Tuple[float, float]: # Return the pan/tilt head to its centered home position (0°, 0°).
    def look_at_pixel(point_2d: Tuple[float, float], source: str = 'pan_tilt') -> Tuple[float, float]: # Shift gaze to center a detected point in the image.
    def move(pan_deg: float, tilt_deg: float) -> Tuple[float, float]: # Move the pan/tilt head to an absolute position in degrees.
    def nudge(d_pan: float, d_tilt: float) -> Tuple[float, float]: # Adjust the pan/tilt head by a relative offset from its current position.

### Module: logos.ros
# This module handles direct interactions with the ROS system.
Functions:
    def get_action_client(name: str, action_type, wait_time: float = 2.0): # Retrieves (or creates) a SimpleActionClient.
    def get_pose() -> Union[Dict[str, float], NoneType]: # Get the robot's current pose from TF.
    def get_tf_buffer(): # Lazy initialization of the TF buffer to prevent ROS startup race conditions.
    def init_subscribers(): # Initializes background subscribers for system state monitoring.
    def is_speaking() -> bool: # Returns True if I am currently outputting speech audio.
    def transform_point_to_map(x: float, y: float, z: float, source_frame: str, timestamp: float) -> Union[Tuple[float, float, float], NoneType]: # Transforms a 3D coordinate from a source frame to the 'map' frame.

### Module: logos.shell
# Helpers for running non-interactive shell commands.
Functions:
    def run(command: str, timeout: int = 30, cwd: Union[str, NoneType] = None) -> str: # Runs a shell command and returns its combined stdout/stderr.

### Module: logos.state
# Defines the structure for my persistent, global state object, `logos.state`.
Classes:
    class ChoraState: # No description.
        pass
    class FileState: # Settings related to the filesystem API.
        pass
    class LogosState: # My central, persistent state object.
        def save(self, path: Union[pathlib.Path, str, NoneType] = None) -> None: # No description.
        def to_dict(self): # Converts the state object into a dictionary for serialization.
        def to_yaml(self) -> str: # No description.
    class MemoryPolicy: # Defines the rules for the automated io_buffer management hook.
        pass
    class SystemState: # General system settings.
        pass
    class TheoriaState: # No description.
        pass
    class VisionState: # Settings for vision hooks and default camera behavior.
        pass
Functions:
    def load_state_from_yaml(state: 'LogosState') -> None: # Update an existing LogosState from state/my_config.yaml if it exists.

### Module: logos.utils
# Internal (hidden) and other helper functions.
Functions:
    def base36_encode(number: int, min_length: int = 4) -> str: # Encode a non-negative integer as a zero-padded base36 string.
    def dump_llm_yaml(data: Any, *, max_flow_line: int = 240, block_scalar_min: int = 80) -> str: # No description.
    def make_time_id(prefix: str = '', now: Union[datetime.datetime, NoneType] = None) -> str: # Generate a time-based, 7-character, base36 ID with optional prefix, e.g. "sum-", "msg-"

### Module: logos.vision
# My eyes. This module gives me access to all three physical cameras and
Constants:
    DEFAULT_RESOLUTION = {'pan_tilt': (960, 1280), 'top_down': (480, 640), 'astra': (480, 640)}
    FOV = {'pan_tilt': (65.0, 50.0), 'top_down': (65.0, 50.0), 'astra_rgb': (63.0, 49.0), 'astra_depth': (58.0, 45.0)}
    SOURCES = ('pan_tilt', 'top_down', 'astra')
Classes:
    class CaptureResult: # A rich container for a single camera capture, carrying the image data
        def add_meta(self, **kwargs) -> None: # Append additional metadata to this capture's YAML sidecar.
        def crop(self, box_2d: List[float]) -> numpy.ndarray: # Crop a region from the image using normalized 0-1000 coordinates.
        def derive_world_coordinate(self, *args, search_radius: int = 3) -> Union[Tuple[float, float, float], NoneType]: # Projects a 2D location into real-world 3D coordinates (map frame).
        def save(self, view: bool = False, meta_keys: Union[List[str], NoneType] = None) -> str: # Save the captured image to disk and generate a photo ID.
        def view(self, meta_keys: Union[List[str], NoneType] = None) -> None: # Print the <file> tag to display this image in my context window.
Functions:
    def capture(source: str = 'pan_tilt', resolution: Union[Tuple[int, int], NoneType] = None, view: bool = False, save: bool = False, astra_feeds: Tuple[str, ...] = ('rgb', 'depth_registered'), meta: Union[Dict[str, Any], NoneType] = None, meta_keys: Union[List[str], NoneType] = None) -> Union[logos.vision.CaptureResult, NoneType]: # Capture an image (and optional depth/IR) from any camera.
    def crop(image_or_result: Union[numpy.ndarray, logos.vision.CaptureResult], box_2d: List[float]) -> numpy.ndarray: # Crop a region from an image using normalized 0-1000 coordinates.
    def publish_debug(image: numpy.ndarray, detections: List[Dict[str, Any]], source: str = 'general') -> None: # Annotate an image with detection boxes and labels, then publish to ROS.
    def release(source: Union[str, NoneType] = None) -> None: # Force-close # stdout
# Logos API Dashboard
A programmatic overview of my capabilities. Use `logos.help(obj)` for deep-dives.

### Global State
    logos.state: Persistent configuration (print it to view as YAML)
    logos.verbosity(level): Context manager to mute/debug output

### Module: logos.base
# My body. This module provides direct access to the Kobuki mobile base.
Functions:
    def get_battery() -> Dict[str, Union[float, str]]: # Read my current battery voltage, percentage, and semantic status.
    def get_bumpers() -> List[str]: # Check if my physical bumpers are currently pressed against an obstacle.
    def get_buttons() -> List[str]: # Check if any physical buttons on my torso are being pressed.
    def get_charger_state() -> str: # Check if I am currently connected to power.
    def get_cliffs() -> List[str]: # Check my downward-facing cliff sensors (stairs, ledges, drop-offs).
    def get_wheel_drops() -> List[str]: # Check if my drive wheels have dropped (meaning I am suspended in the air).
    def stop(topic: str = 'raw') -> None: # Immediately halt all base movement by publishing zero velocities.
    def velocity(linear_x: float, angular_z: float, duration: float, topic: str = 'raw') -> None: # Send raw velocity commands to a raw (default) velocity topic or smoothed and muxed topic for a specific duration.

### Module: logos.map3d
# My 'mind palace.' A virtual 3D environment for advanced spatial reasoning.
Constants:
    HUD_ANCHORS = ('top_left', 'top_center', 'top_right', 'bottom_left', 'bottom_center', 'bottom_right')
    HUD_FONT_DUPLEX = 2
    HUD_FONT_PLAIN = 1
    HUD_FONT_SIMPLEX = 0
    HUD_FONT_SMALL = 6
Classes:
    class Chora: # Stateful renderer + raycaster with persistent ROS subscriptions.
        def load_phantasma(self, name: 'str') -> 'None': # Minimal future-proof loader:
        def raycast(self, render: 'Union[RenderResult, str]', yx: 'Tuple[float, float]', include_floor: 'bool' = True, include_astra: 'bool' = True, include_robot: 'bool' = True, include_objects: 'bool' = True) -> 'RaycastHit': # Projects a 2D pixel from a `map3d` render back into the 3D world.
        def register_object(self, obj: 'SceneObject') -> 'None': # No description.
        def remove_object(self, name: 'str') -> 'None': # No description.
        def render(self, camera_pos_relative: 'Optional[Tuple[float, float, float]]' = (0.0, 0.0, 0.7), camera_pos_world: 'Optional[Tuple[float, float, float]]' = None, look_at_relative: 'Optional[Tuple[float, float, float]]' = (1.0, 0, 0.0), look_at_world: 'Optional[Tuple[float, float, float]]' = None, rpy_deg: 'Optional[Tuple[float, float, float]]' = None, rot_matrix_3x3: 'Optional[Union[np.ndarray, List[List[float]]]]' = None, look_distance_m: 'float' = 2.0, max_cloud_height_m: 'Optional[float]' = None, resolution: 'Tuple[int, int]' = (768, 768), include_robot: 'bool' = True, view: 'bool' = True, save: 'bool' = True, save_dir: 'str' = 'artifacts/map3d', filename: 'Optional[str]' = 'debug.png', cloud_alpha: 'Optional[float]' = None, cloud_density: 'Optional[float]' = None, cloud_opacity: 'Optional[float]' = None, cloud_point_size: 'Optional[float]' = None, laser_scan_show: 'Optional[bool]' = None, laser_scan_center_band_px: 'Optional[int]' = None, laser_scan_color: 'Optional[List[float]]' = None, hud: 'Optional[List[HudElement]]' = None, hud_warnings: 'bool' = True, hud_frame_info: 'bool' = True, hud_stats: 'bool' = False) -> 'RenderResult': # Renders a view of my 3D 'map3d' from my virtual `theoria` camera.
    class HudElement: # A single text element to overlay on a rendered image.
        pass
    class RaycastHit: # Result of raycasting a pixel against a scene snapshot.
        pass
    class RenderResult: # CaptureResult-shaped return for mind-palace rendering.
        def save(self, view: 'bool' = False, path: 'Optional[str]' = None) -> 'str': # No description.
        def view(self) -> 'None': # No description.
    class SceneObject: # An object that can be rendered and/or raycasted.
        pass
    class SceneSnapshot: # Self-contained snapshot of what was rendered, sufficient for later raycasts.
        pass
Functions:
    def get_map3d() -> 'Chora': # No description.
    def raycast(*args, **kwargs) -> 'RaycastHit': # No description.
    def render(*args, **kwargs) -> 'RenderResult': # No description.

### Module: logos.core
# Core functionality for the Logos API, including verbosity management, cooperative interrupt handling, and dynamic help generation.
Classes:
    class Verbosity: # Enumeration for setting API verbosity levels.
        pass
Functions:
    def api_call(default_verbosity: logos.core.Verbosity = <Verbosity.ACK: 1>): # Decorator for public API functions that have side effects or are “actions” from Logos’ POV (movement, IO, memory changes, etc.).
    def check_for_interrupt(): # Checks if an external interrupt has been requested.
    def help(obj: Union[object, NoneType] = None, search: Union[str, NoneType] = None, print_output: bool = True) -> str: # Provides a dynamic, auto-generated help dashboard for my API.
    def verbosity(level: logos.core.Verbosity): # A context manager to temporarily set the verbosity level for API calls.

### Module: logos.exceptions
# Defines core exceptions for my framework.
Classes:
    class Interrupt: # Raised when a cooperative interrupt is requested by an external system.
        def with_traceback(...): # Exception.with_traceback(tb) --

### Module: logos.files
# This module contains all my tools for interacting with the filesystem.
Functions:
    def append(path: str, content: str): # Appends content to the end of a file.
    def read(path: str) -> str: # Reads the entire content of a file.
    def show(path: str, max_chars: int = 2000, pattern: Union[str, NoneType] = None) -> str: # Prints (and returns) a possibly filtered, truncated view of a file.
    def tree(start_path: str = '.', max_depth: int = 3, show_hidden: bool = True, show_extensions: Union[List[str], NoneType] = None, inline_meta_masks: Union[List[str], NoneType] = None, ignore_globs: Union[List[str], NoneType] = None, files_per_dir_limit: int = 50) -> str: # Generates an intelligent, detailed tree view of the filesystem.
    def write(path: str, content: str): # Writes content to a file, overwriting it if it exists.

### Module: logos.hooks
# This module contains functions for me to introspect and modify my own cognitive hook configurations. Does *not* contain the hook code itself.
Functions:
    def remove(location: str, name: str): # Removes a hook from a specified configuration.
    def show(location: str) -> str: # Provides a concise summary of all hooks in a given [location]_hooks_config.yaml file.
    def upsert(location: str, name: str, *, description: Union[str, NoneType] = None, ttl: Union[int, NoneType] = None, code: Union[str, NoneType] = None, insert_before: Union[str, NoneType] = None) -> None: # Update an existing hook or create a new one in the requested configuration.

### Module: logos.leds
# Control for my RGB LED strips and laser pointer.
Functions:
    def fill(strip: str, color: Union[int, Tuple[int, int, int], str]) -> None: # Set all LEDs on a strip to the same color.
    def laser(brightness: float) -> None: # Set the laser pointer brightness.
    def off(strip: Union[str, NoneType] = None) -> None: # Turn off LEDs. If strip is None, turns off ALL strips and the laser.
    def set(strip: str, colors: Sequence[Union[int, Tuple[int, int, int], str]]) -> None: # Set individual LED colors on a strip.

### Module: logos.logos_mesh
# logos.map3d.logos_mesh
Functions:
    def build_logos_mesh() -> "'o3d.geometry.TriangleMesh'": # Build a complete Logos robot mesh at the origin, facing +X (ROS forward).

### Module: logos.memory
# This module contains tools for the current Hypomnemeta (io_buffer.jsonl) and historical records.
Functions:
    def recall(msg_id: str) -> Union[str, NoneType]: # Retrieves the full, original content of a message from the history log.
    def replace_cell_content(cell_index: int, new_content: str): # Directly replaces the content of a single cell in the io_buffer.
    def summarize_io_buffer(cell_indices: List[int], guidance: str = None): # Summarizes specific cells in the io_buffer using a specialized agent.

### Module: logos.models
# Wrappers for interacting with various ML / AI models.
Functions:
    def llm(prompt: str, model_alias: str = 'fast', temperature: float = 0.7) -> str: # A simple wrapper to prompt my core, stateless, LLM intelligence out-of-band. 
    def yolo11(image: numpy.ndarray, classes: Union[List[str], NoneType] = None, conf: float = 0.5) -> List[Dict[str, Any]]: # Run inference using the blazing fast YOLO11 Nano model.
    def yolo_world(image: numpy.ndarray, prompts: List[str], conf: float = 0.1) -> List[Dict[str, Any]]: # Run inference using the YOLO-World open-vocabulary model.

### Module: logos.nav
# Map-aware autonomous navigation.
Classes:
    class NavTask: # A handle for an asynchronous navigation task.
        def cancel(self) -> None: # Stops the robot and cancels this specific goal.
        def is_active(self) -> bool: # Returns True if the robot is currently trying to reach the goal.
        def progress(self) -> float: # Estimates how far along the path the robot is, from 0.0 to 1.0.
        def status(self) -> str: # Returns a human-readable status of the goal (e.g., 'ACTIVE', 'SUCCEEDED', 'ABORTED').
        def succeeded(self) -> bool: # Returns True if the robot successfully reached the goal.
        def wait(self, timeout: float = 120.0) -> bool: # Blocks execution until the goal is reached, fails, or times out.
Functions:
    def cancel_all() -> None: # Panic button. Immediately halts all map-based and relative navigation tasks.
    def go_to_abs(x: float, y: float, theta_deg: Union[float, NoneType] = None, wait: bool = True) -> logos.nav.NavTask: # Navigate to an absolute (x, y) coordinate on the ROS map using move_base.
    def move_relative(forward_m: float, turn_deg: float, wait: bool = True) -> logos.nav.NavTask: # Move a relative distance using odometry (turn first, then drive forward).

### Module: logos.pantilt
# Control for my pan/tilt servo periscope.
Constants:
    HOME = (0.0, 0.0)
    PAN_RANGE = (-80.0, 100.0)
    TILT_RANGE = (-60.0, 70.0)
Functions:
    def get_position() -> Tuple[float, float]: # Read the current pan/tilt position in degrees.
    def home() -> Tuple[float, float]: # Return the pan/tilt head to its centered home position (0°, 0°).
    def look_at_pixel(point_2d: Tuple[float, float], source: str = 'pan_tilt') -> Tuple[float, float]: # Shift gaze to center a detected point in the image.
    def move(pan_deg: float, tilt_deg: float) -> Tuple[float, float]: # Move the pan/tilt head to an absolute position in degrees.
    def nudge(d_pan: float, d_tilt: float) -> Tuple[float, float]: # Adjust the pan/tilt head by a relative offset from its current position.

### Module: logos.ros
# This module handles direct interactions with the ROS system.
Functions:
    def get_action_client(name: str, action_type, wait_time: float = 2.0): # Retrieves (or creates) a SimpleActionClient.
    def get_pose() -> Union[Dict[str, float], NoneType]: # Get the robot's current pose from TF.
    def get_tf_buffer(): # Lazy initialization of the TF buffer to prevent ROS startup race conditions.
    def init_subscribers(): # Initializes background subscribers for system state monitoring.
    def is_speaking() -> bool: # Returns True if I am currently outputting speech audio.
    def transform_point_to_map(x: float, y: float, z: float, source_frame: str, timestamp: float) -> Union[Tuple[float, float, float], NoneType]: # Transforms a 3D coordinate from a source frame to the 'map' frame.

### Module: logos.shell
# Helpers for running non-interactive shell commands.
Functions:
    def run(command: str, timeout: int = 30, cwd: Union[str, NoneType] = None) -> str: # Runs a shell command and returns its combined stdout/stderr.

### Module: logos.state
# Defines the structure for my persistent, global state object, `logos.state`.
Classes:
    class ChoraState: # No description.
        pass
    class FileState: # Settings related to the filesystem API.
        pass
    class LogosState: # My central, persistent state object.
        def save(self, path: Union[pathlib.Path, str, NoneType] = None) -> None: # No description.
        def to_dict(self): # Converts the state object into a dictionary for serialization.
        def to_yaml(self) -> str: # No description.
    class MemoryPolicy: # Defines the rules for the automated io_buffer management hook.
        pass
    class SystemState: # General system settings.
        pass
    class TheoriaState: # No description.
        pass
    class VisionState: # Settings for vision hooks and default camera behavior.
        pass
Functions:
    def load_state_from_yaml(state: 'LogosState') -> None: # Update an existing LogosState from state/my_config.yaml if it exists.

### Module: logos.utils
# Internal (hidden) and other helper functions.
Functions:
    def base36_encode(number: int, min_length: int = 4) -> str: # Encode a non-negative integer as a zero-padded base36 string.
    def dump_llm_yaml(data: Any, *, max_flow_line: int = 240, block_scalar_min: int = 80) -> str: # No description.
    def make_time_id(prefix: str = '', now: Union[datetime.datetime, NoneType] = None) -> str: # Generate a time-based, 7-character, base36 ID with optional prefix, e.g. "sum-", "msg-"

### Module: logos.vision
# My eyes. This module gives me access to all three physical cameras and
Constants:
    DEFAULT_RESOLUTION = {'pan_tilt': (960, 1280), 'top_down': (480, 640), 'astra': (480, 640)}
    FOV = {'pan_tilt': (65.0, 50.0), 'top_down': (65.0, 50.0), 'astra_rgb': (63.0, 49.0), 'astra_depth': (58.0, 45.0)}
    SOURCES = ('pan_tilt', 'top_down', 'astra')
Classes:
    class CaptureResult: # A rich container for a single camera capture, carrying the image data
        def add_meta(self, **kwargs) -> None: # Append additional metadata to this capture's YAML sidecar.
        def crop(self, box_2d: List[float]) -> numpy.ndarray: # Crop a region from the image using normalized 0-1000 coordinates.
        def derive_world_coordinate(self, *args, search_radius: int = 3) -> Union[Tuple[float, float, float], NoneType]: # Projects a 2D location into real-world 3D coordinates (map frame).
        def save(self, view: bool = False, meta_keys: Union[List[str], NoneType] = None) -> str: # Save the captured image to disk and generate a photo ID.
        def view(self, meta_keys: Union[List[str], NoneType] = None) -> None: # Print the <file> tag to display this image in my context window.
Functions:
    def capture(source: str = 'pan_tilt', resolution: Union[Tuple[int, int], NoneType] = None, view: bool = False, save: bool = False, astra_feeds: Tuple[str, ...] = ('rgb', 'depth_registered'), meta: Union[Dict[str, Any], NoneType] = None, meta_keys: Union[List[str], NoneType] = None) -> Union[logos.vision.CaptureResult, NoneType]: # Capture an image (and optional depth/IR) from any camera.
    def crop(image_or_result: Union[numpy.ndarray, logos.vision.CaptureResult], box_2d: List[float]) -> numpy.ndarray: # Crop a region from an image using normalized 0-1000 coordinates.
    def publish_debug(image: numpy.ndarray, detections: List[Dict[str, Any]], source: str = 'general') -> None: # Annotate an image with detection boxes and labels, then publish to ROS.
    def release(source: Union[str, NoneType] = None) -> None: # Force-close a camera (or all cameras) immediately, without waiting
    def warm_up(source: str) -> None: # Pre-warm a camera, blocking until it's ready for instant capture.

### Module: logos.voice
# My voice. This module allows me to `speak()` using my TTS system and emoji
Classes:
    class SpeakTask: # A handle for an asynchronous speaking task.
        def cancel(self) -> None: # Stop speaking immediately.
        def current_emoji(self) -> str: # Returns the emoji currently driving my animatronics.
        def current_text(self) -> str: # Returns the specific text snippet being spoken right now.
        def is_active(self) -> bool: # Returns True if audio is still playing or synthesis is still running.
        def progress(self) -> float: # Returns estimated playback progress from 0.0 to 1.0.
        def wait(self) -> bool: # Blocks execution until all audio has finished playing.
Functions:
    def is_speaking() -> bool: # Checks if ANY speech audio is currently playing across the system.
    def speak(text: str, wait: bool = True, engine: str = 'kokoro', **kwargs) -> logos.voice.SpeakTask: # Takes emoji-punctuated text and speaks it in sync with animatronic face and arm expressions. 🎭

# Help for: help(obj: Union[object, NoneType] = None, search: Union[str, NoneType] = None, print_output: bool = True) -> str
----------------------------------------
Provides a dynamic, auto-generated help dashboard for my API.

Args:
    obj: The API object to get help for (module, class, or function).
         If None, provides a comprehensive dashboard of the entire API.
    search: A string to search for across function/class names and docstrings.
    print_output: If True, prints to stdout. If False, just returns the string.

Returns:
    A formatted string containing the help information.

Note to self:
    - `logos.help()` gives me the full dashboard (Signatures + 1-liners).
    - `logos.help(logos.vision.capture)` gives me the deep-dive docstring.
    - `logos.help(search="crop")` helps me find tools when I forget where they live.

# Execution finished in 0.02s.a camera (or all cameras) immediately, without waiting
    def warm_up(source: str) -> None: # Pre-warm a camera, blocking until it's ready for instant capture.

### Module: logos.voice
# My voice. This module allows me to `speak()` using my TTS system and emoji
Classes:
    class SpeakTask: # A handle for an asynchronous speaking task.
        def cancel(self) -> None: # Stop speaking immediately.
        def current_emoji(self) -> str: # Returns the emoji currently driving my animatronics.
        def current_text(self) -> str: # Returns the specific text snippet being spoken right now.
        def is_active(self) -> bool: # Returns True if audio is still playing or synthesis is still running.
        def progress(self) -> float: # Returns estimated playback progress from 0.0 to 1.0.
        def wait(self) -> bool: # Blocks execution until all audio has finished playing.
Functions:
    def is_speaking() -> bool: # Checks if ANY speech audio is currently playing across the system.
    def speak(text: str, wait: bool = True, engine: str = 'kokoro', **kwargs) -> logos.voice.SpeakTask: # Takes emoji-punctuated text and speaks it in sync with animatronic face and arm expressions. 🎭

# Help for: help(obj: Union[object, NoneType] = None, search: Union[str, NoneType] = None, print_output: bool = True) -> str
----------------------------------------
Provides a dynamic, auto-generated help dashboard for my API.

Args:
    obj: The API object to get help for (module, class, or function).
         If None, provides a comprehensive dashboard of the entire API.
    search: A string to search for across function/class names and docstrings.
    print_output: If True, prints to stdout. If False, just returns the string.

Returns:
    A formatted string containing the help information.

Note to self:
    - `logos.help()` gives me the full dashboard (Signatures + 1-liners).
    - `logos.help(logos.vision.capture)` gives me the deep-dive docstring.
    - `logos.help(search="crop")` helps me find tools when I forget where they live.

# Execution finished in 0.02s.
# My 'mind palace.' A virtual 3D environment for advanced spatial reasoning.
Constants:
    HUD_ANCHORS = ('top_left', 'top_center', 'top_right', 'bottom_left', 'bottom_center', 'bottom_right')
    HUD_FONT_DUPLEX = 2
    HUD_FONT_PLAIN = 1
    HUD_FONT_SIMPLEX = 0
    HUD_FONT_SMALL = 6
Classes:
    class Chora: # Stateful renderer + raycaster with persistent ROS subscriptions.
        def load_phantasma(self, name: 'str') -> 'None': # Minimal future-proof loader:
        def raycast(self, render: 'Union[RenderResult, str]', yx: 'Tuple[float, float]', include_floor: 'bool' = True, include_astra: 'bool' = True, include_robot: 'bool' = True, include_objects: 'bool' = True) -> 'RaycastHit': # Projects a 2D pixel from a `map3d` render back into the 3D world.
        def register_object(self, obj: 'SceneObject') -> 'None': # No description.
        def remove_object(self, name: 'str') -> 'None': # No description.
        def render(self, camera_pos_relative: 'Optional[Tuple[float, float, float]]' = (0.0, 0.0, 0.7), camera_pos_world: 'Optional[Tuple[float, float, float]]' = None, look_at_relative: 'Optional[Tuple[float, float, float]]' = (1.0, 0, 0.0), look_at_world: 'Optional[Tuple[float, float, float]]' = None, rpy_deg: 'Optional[Tuple[float, float, float]]' = None, rot_matrix_3x3: 'Optional[Union[np.ndarray, List[List[float]]]]' = None, look_distance_m: 'float' = 2.0, max_cloud_height_m: 'Optional[float]' = None, resolution: 'Tuple[int, int]' = (768, 768), include_robot: 'bool' = True, view: 'bool' = True, save: 'bool' = True, save_dir: 'str' = 'artifacts/map3d', filename: 'Optional[str]' = 'debug.png', cloud_alpha: 'Optional[float]' = None, cloud_density: 'Optional[float]' = None, cloud_opacity: 'Optional[float]' = None, cloud_point_size: 'Optional[float]' = None, laser_scan_show: 'Optional[bool]' = None, laser_scan_center_band_px: 'Optional[int]' = None, laser_scan_color: 'Optional[List[float]]' = None, hud: 'Optional[List[HudElement]]' = None, hud_warnings: 'bool' = True, hud_frame_info: 'bool' = True, hud_stats: 'bool' = False) -> 'RenderResult': # Renders a view of my 3D 'map3d' from my virtual `theoria` camera.
    class HudElement: # A single text element to overlay on a rendered image.
        pass
    class RaycastHit: # Result of raycasting a pixel against a scene snapshot.
        pass
    class RenderResult: # CaptureResult-shaped return for mind-palace rendering.
        def save(self, view: 'bool' = False, path: 'Optional[str]' = None) -> 'str': # No description.
        def view(self) -> 'None': # No description.
    class SceneObject: # An object that can be rendered and/or raycasted.
        pass
    class SceneSnapshot: # Self-contained snapshot of what was rendered, sufficient for later raycasts.
        pass
Functions:
    def get_map3d() -> 'Chora': # No description.
    def raycast(*args, **kwargs) -> 'RaycastHit': # No description.
    def render(*args, **kwargs) -> 'RenderResult': # No description.

### Module: logos.core
# Core functionality for the Logos API, including verbosity management, cooperative interrupt handling, and dynamic help generation.
Classes:
    class Verbosity: # Enumeration for setting API verbosity levels.
        pass
Functions:
    def api_call(default_verbosity: logos.core.Verbosity = <Verbosity.ACK: 1>): # Decorator for public API functions that have side effects or are “actions” from Logos’ POV (movement, IO, memory changes, etc.).
    def check_for_interrupt(): # Checks if an external interrupt has been requested.
    def help(obj: Union[object, NoneType] = None, search: Union[str, NoneType] = None, print_output: bool = True) -> str: # Provides a dynamic, auto-generated help dashboard for my API.
    def verbosity(level: logos.core.Verbosity): # A context manager to temporarily set the verbosity level for API calls.

### Module: logos.exceptions
# Defines core exceptions for my framework.
Classes:
    class Interrupt: # Raised when a cooperative interrupt is requested by an external system.
        def with_traceback(...): # Exception.with_traceback(tb) --

### Module: logos.files
# This module contains all my tools for interacting with the filesystem.
Functions:
    def append(path: str, content: str): # Appends content to the end of a file.
    def read(path: str) -> str: # Reads the entire content of a file.
    def show(path: str, max_chars: int = 2000, pattern: Union[str, NoneType] = None) -> str: # Prints (and returns) a possibly filtered, truncated view of a file.
    def tree(start_path: str = '.', max_depth: int = 3, show_hidden: bool = True, show_extensions: Union[List[str], NoneType] = None, inline_meta_masks: Union[List[str], NoneType] = None, ignore_globs: Union[List[str], NoneType] = None, files_per_dir_limit: int = 50) -> str: # Generates an intelligent, detailed tree view of the filesystem.
    def write(path: str, content: str): # Writes content to a file, overwriting it if it exists.

### Module: logos.hooks
# This module contains functions for me to introspect and modify my own cognitive hook configurations. Does *not* contain the hook code itself.
Functions:
    def remove(location: str, name: str): # Removes a hook from a specified configuration.
    def show(location: str) -> str: # Provides a concise summary of all hooks in a given [location]_hooks_config.yaml file.
    def upsert(location: str, name: str, *, description: Union[str, NoneType] = None, ttl: Union[int, NoneType] = None, code: Union[str, NoneType] = None, insert_before: Union[str, NoneType] = None) -> None: # Update an existing hook or create a new one in the requested configuration.

### Module: logos.leds
# Control for my RGB LED strips and laser pointer.
Functions:
    def fill(strip: str, color: Union[int, Tuple[int, int, int], str]) -> None: # Set all LEDs on a strip to the same color.
    def laser(brightness: float) -> None: # Set the laser pointer brightness.
    def off(strip: Union[str, NoneType] = None) -> None: # Turn off LEDs. If strip is None, turns off ALL strips and the laser.
    def set(strip: str, colors: Sequence[Union[int, Tuple[int, int, int], str]]) -> None: # Set individual LED colors on a strip.

### Module: logos.logos_mesh
# logos.map3d.logos_mesh
Functions:
    def build_logos_mesh() -> "'o3d.geometry.TriangleMesh'": # Build a complete Logos robot mesh at the origin, facing +X (ROS forward).

### Module: logos.memory
# This module contains tools for the current Hypomnemeta (io_buffer.jsonl) and historical records.
Functions:
    def recall(msg_id: str) -> Union[str, NoneType]: # Retrieves the full, original content of a message from the history log.
    def replace_cell_content(cell_index: int, new_content: str): # Directly replaces the content of a single cell in the io_buffer.
    def summarize_io_buffer(cell_indices: List[int], guidance: str = None): # Summarizes specific cells in the io_buffer using a specialized agent.

### Module: logos.models
# Wrappers for interacting with various ML / AI models.
Functions:
    def llm(prompt: str, model_alias: str = 'fast', temperature: float = 0.7) -> str: # A simple wrapper to prompt my core, stateless, LLM intelligence out-of-band. 
    def yolo11(image: numpy.ndarray, classes: Union[List[str], NoneType] = None, conf: float = 0.5) -> List[Dict[str, Any]]: # Run inference using the blazing fast YOLO11 Nano model.
    def yolo_world(image: numpy.ndarray, prompts: List[str], conf: float = 0.1) -> List[Dict[str, Any]]: # Run inference using the YOLO-World open-vocabulary model.

### Module: logos.nav
# Map-aware autonomous navigation.
Classes:
    class NavTask: # A handle for an asynchronous navigation task.
        def cancel(self) -> None: # Stops the robot and cancels this specific goal.
        def is_active(self) -> bool: # Returns True if the robot is currently trying to reach the goal.
        def progress(self) -> float: # Estimates how far along the path the robot is, from 0.0 to 1.0.
        def status(self) -> str: # Returns a human-readable status of the goal (e.g., 'ACTIVE', 'SUCCEEDED', 'ABORTED').
        def succeeded(self) -> bool: # Returns True if the robot successfully reached the goal.
        def wait(self, timeout: float = 120.0) -> bool: # Blocks execution until the goal is reached, fails, or times out.
Functions:
    def cancel_all() -> None: # Panic button. Immediately halts all map-based and relative navigation tasks.
    def go_to_abs(x: float, y: float, theta_deg: Union[float, NoneType] = None, wait: bool = True) -> logos.nav.NavTask: # Navigate to an absolute (x, y) coordinate on the ROS map using move_base.
    def move_relative(forward_m: float, turn_deg: float, wait: bool = True) -> logos.nav.NavTask: # Move a relative distance using odometry (turn first, then drive forward).

### Module: logos.pantilt
# Control for my pan/tilt servo periscope.
Constants:
    HOME = (0.0, 0.0)
    PAN_RANGE = (-80.0, 100.0)
    TILT_RANGE = (-60.0, 70.0)
Functions:
    def get_position() -> Tuple[float, float]: # Read the current pan/tilt position in degrees.
    def home() -> Tuple[float, float]: # Return the pan/tilt head to its centered home position (0°, 0°).
    def look_at_pixel(point_2d: Tuple[float, float], source: str = 'pan_tilt') -> Tuple[float, float]: # Shift gaze to center a detected point in the image.
    def move(pan_deg: float, tilt_deg: float) -> Tuple[float, float]: # Move the pan/tilt head to an absolute position in degrees.
    def nudge(d_pan: float, d_tilt: float) -> Tuple[float, float]: # Adjust the pan/tilt head by a relative offset from its current position.

### Module: logos.ros
# This module handles direct interactions with the ROS system.
Functions:
    def get_action_client(name: str, action_type, wait_time: float = 2.0): # Retrieves (or creates) a SimpleActionClient.
    def get_pose() -> Union[Dict[str, float], NoneType]: # Get the robot's current pose from TF.
    def get_tf_buffer(): # Lazy initialization of the TF buffer to prevent ROS startup race conditions.
    def init_subscribers(): # Initializes background subscribers for system state monitoring.
    def is_speaking() -> bool: # Returns True if I am currently outputting speech audio.
    def transform_point_to_map(x: float, y: float, z: float, source_frame: str, timestamp: float) -> Union[Tuple[float, float, float], NoneType]: # Transforms a 3D coordinate from a source frame to the 'map' frame.

### Module: logos.shell
# Helpers for running non-interactive shell commands.
Functions:
    def run(command: str, timeout: int = 30, cwd: Union[str, NoneType] = None) -> str: # Runs a shell command and returns its combined stdout/stderr.

### Module: logos.state
# Defines the structure for my persistent, global state object, `logos.state`.
Classes:
    class ChoraState: # No description.
        pass
    class FileState: # Settings related to the filesystem API.
        pass
    class LogosState: # My central, persistent state object.
        def save(self, path: Union[pathlib.Path, str, NoneType] = None) -> None: # No description.
        def to_dict(self): # Converts the state object into a dictionary for serialization.
        def to_yaml(self) -> str: # No description.
    class MemoryPolicy: # Defines the rules for the automated io_buffer management hook.
        pass
    class SystemState: # General system settings.
        pass
    class TheoriaState: # No description.
        pass
    class VisionState: # Settings for vision hooks and default camera behavior.
        pass
Functions:
    def load_state_from_yaml(state: 'LogosState') -> None: # Update an existing LogosState from state/my_config.yaml if it exists.

### Module: logos.utils
# Internal (hidden) and other helper functions.
Functions:
    def base36_encode(number: int, min_length: int = 4) -> str: # Encode a non-negative integer as a zero-padded base36 string.
    def dump_llm_yaml(data: Any, *, max_flow_line: int = 240, block_scalar_min: int = 80) -> str: # No description.
    def make_time_id(prefix: str = '', now: Union[datetime.datetime, NoneType] = None) -> str: # Generate a time-based, 7-character, base36 ID with optional prefix, e.g. "sum-", "msg-"

### Module: logos.vision
# My eyes. This module gives me access to all three physical cameras and
Constants:
    DEFAULT_RESOLUTION = {'pan_tilt': (960, 1280), 'top_down': (480, 640), 'astra': (480, 640)}
    FOV = {'pan_tilt': (65.0, 50.0), 'top_down': (65.0, 50.0), 'astra_rgb': (63.0, 49.0), 'astra_depth': (58.0, 45.0)}
    SOURCES = ('pan_tilt', 'top_down', 'astra')
Classes:
    class CaptureResult: # A rich container for a single camera capture, carrying the image data
        def add_meta(self, **kwargs) -> None: # Append additional metadata to this capture's YAML sidecar.
        def crop(self, box_2d: List[float]) -> numpy.ndarray: # Crop a region from the image using normalized 0-1000 coordinates.
        def derive_world_coordinate(self, *args, search_radius: int = 3) -> Union[Tuple[float, float, float], NoneType]: # Projects a 2D location into real-world 3D coordinates (map frame).
        def save(self, view: bool = False, meta_keys: Union[List[str], NoneType] = None) -> str: # Save the captured image to disk and generate a photo ID.
        def view(self, meta_keys: Union[List[str], NoneType] = None) -> None: # Print the <file> tag to display this image in my context window.
Functions:
    def capture(source: str = 'pan_tilt', resolution: Union[Tuple[int, int], NoneType] = None, view: bool = False, save: bool = False, astra_feeds: Tuple[str, ...] = ('rgb', 'depth_registered'), meta: Union[Dict[str, Any], NoneType] = None, meta_keys: Union[List[str], NoneType] = None) -> Union[logos.vision.CaptureResult, NoneType]: # Capture an image (and optional depth/IR) from any camera.
    def crop(image_or_result: Union[numpy.ndarray, logos.vision.CaptureResult], box_2d: List[float]) -> numpy.ndarray: # Crop a region from an image using normalized 0-1000 coordinates.
    def publish_debug(image: numpy.ndarray, detections: List[Dict[str, Any]], source: str = 'general') -> None: # Annotate an image with detection boxes and labels, then publish to ROS.
    def release(source: Union[str, NoneType] = None) -> None: # Force-close a camera (or all cameras) immediately, without waiting
    def warm_up(source: str) -> None: # Pre-warm a camera, blocking until it's ready for instant capture.

### Module: logos.voice
# My voice. This module allows me to `speak()` using my TTS system and emoji
Classes:
    class SpeakTask: # A handle for an asynchronous speaking task.
        def cancel(self) -> None: # Stop speaking immediately.
        def current_emoji(self) -> str: # Returns the emoji currently driving my animatronics.
        def current_text(self) -> str: # Returns the specific text snippet being spoken right now.
        def is_active(self) -> bool: # Returns True if audio is still playing or synthesis is still running.
        def progress(self) -> float: # Returns estimated playback progress from 0.0 to 1.0.
        def wait(self) -> bool: # Blocks execution until all audio has finished playing.
Functions:
    def is_speaking() -> bool: # Checks if ANY speech audio is currently playing across the system.
    def speak(text: str, wait: bool = True, engine: str = 'kokoro', **kwargs) -> logos.voice.SpeakTask: # Takes emoji-punctuated text and speaks it in sync with animatronic face and arm expressions. 🎭

# Help for: help(obj: Union[object, NoneType] = None, search: Union[str, NoneType] = None, print_output: bool = True) -> str
----------------------------------------
Provides a dynamic, auto-generated help dashboard for my API.

Args:
    obj: The API object to get help for (module, class, or function).
         If None, provides a comprehensive dashboard of the entire API.
    search: A string to search for across function/class names and docstrings.
    print_output: If True, prints to stdout. If False, just returns the string.

Returns:
    A formatted string containing the help information.

Note to self:
    - `logos.help()` gives me the full dashboard (Signatures + 1-liners).
    - `logos.help(logos.vision.capture)` gives me the deep-dive docstring.
    - `logos.help(search="crop")` helps me find tools when I forget where they live.

