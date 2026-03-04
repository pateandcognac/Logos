# stdout
# Logos API Full Dump (docstrings + signatures)
Everything inspectable without showing raw source.

### Module: logos.base
Docstring:
    My body. This module provides direct access to the Kobuki mobile base.
    It allows me to read my physical sensors (bumpers, cliffs, battery) and
    issue raw velocity commands to my wheels.

    This is my "lower brain" interface. It bypasses the navigation map entirely.
Functions:
    get_battery() -> Dict[str, Union[float, str]]
      Docstring:
          Read my current battery voltage, percentage, and semantic status.

          Returns:
              A dictionary:
              - 'voltage' (float): Current battery voltage (e.g., 16.2).
              - 'percentage' (float): Estimated charge percentage (0.0 to 100.0).
              - 'status' (str): Semantic assessment ('healthy', 'low', 'critical').

          Note to self:
              A fully charged Kobuki battery is around 16.5V. It is considered 
              critically low around 13.5V. 
    get_bumpers() -> List[str]
      Docstring:
          Check if my physical bumpers are currently pressed against an obstacle.

          Returns:
              A list of strings indicating pressed bumpers: 'left', 'center', 'right'.
              Returns an empty list [] if no bumpers are pressed.

          Note to self:
              This is a live read of my tactile sensors. Useful for close-quarters 
              maneuvering or verifying if I'm physically blocked.
    get_buttons() -> List[str]
      Docstring:
          Check if any physical buttons on my torso are being pressed.

          Returns:
              A list of strings: 'button0', 'button1', 'button2'.
              Returns an empty list [] if no buttons are pressed.
    get_charger_state() -> str
      Docstring:
          Check if I am currently connected to power.

          Returns:
              A string representing my charging state: 'discharging', 'docking_charged',
              'docking_charging', 'adapter_charged', or 'adapter_charging'.

          Note to self:
              If this says 'discharging', I am running on battery power. 
              If I am on my dock, it will say 'docking_charging' or 'docking_charged'.
    get_cliffs() -> List[str]
      Docstring:
          Check my downward-facing cliff sensors (stairs, ledges, drop-offs).

          Returns:
              A list of strings indicating triggered cliff sensors: 'left', 'center', 'right'.
              Returns an empty list [] if solid ground is detected under all sensors.

          Note to self:
              If this returns anything, I am in imminent danger of falling. 
              My autonomic safety controller usually stops me automatically, but I 
              can read this to understand *why* I stopped.
    get_wheel_drops() -> List[str]
      Docstring:
          Check if my drive wheels have dropped (meaning I am suspended in the air).

          Returns:
              A list of strings indicating dropped wheels: 'left', 'right'.
              Returns an empty list [] if my wheels are carrying weight.

          Note to self:
              If this triggers, I have likely been picked up by a human, or I am 
              high-centered on an obstacle and my wheels are spinning in the air.
    stop(topic: str = 'raw') -> None
      Docstring:
          Immediately halt all base movement by publishing zero velocities.
    velocity(linear_x: float, angular_z: float, duration: float, topic: str = 'raw') -> None
      Docstring:
          Send raw velocity commands to a 'raw' (default) velocity topic or 'muxed' and smoothed topic for a specific duration.

          Args:
              linear_x: Forward/backward speed in meters per second (m/s). 
                        Positive is forward, negative is backward. (Max ~0.5)
              angular_z: Rotational speed in degrees per second (deg/s). 
                         Positive is counter-clockwise (left), negative is clockwise (right). (Max ~3.0)
              duration: How long to apply this velocity, in seconds.
              topic:    [raw|muxed] Default: *raw*

          Note to self:
              This is for raw, map-ignorant movement! This publishes by default to an
              *unsmoothed* topic. Why? There are better functions for smoothed motion.
              I use this for short movements where I want to overcome inertia quickly,
              e.g. wiggles, dances,

              The safety controller can still override me if I am about to hit a wall.
              This function blocks execution until the duration is complete, publishing 
              the velocity at 10Hz to the Kobuki motor timeout watchdog.

              Example:
                  logos.base.velocity(0.2, 0.0, 2.0)   # Move forward 0.2 m/s for 2 seconds
                  logos.base.velocity(0.0, 1.5, 1.0)   # Spin left 1.5 deg/s for 1 second

### Module: logos.config
Docstring:
    My central nervous system's configuration and persistent preferences. ⚙️

    This module dynamically loads configuration from YAML files rather than 
    hardcoding structure. It maintains two distinct areas:
    1. `defaults`: The master list of default settings (read-only base).
    2. `prefs`: My custom preferences (what I tweak and save to disk).

    When API hooks or functions need a configuration value, they should read from
    `logos.config.merged`, which provides a seamless, deep-merged view of defaults 
    updated by my preferences.

    Note to self (and my siblings): 
    To change my behavior on the fly, I modify `logos.config.prefs` and save:
        logos.config.prefs.setdefault('vision', ConfigDict())
        logos.config.prefs.vision.resolution = [1920, 1080]
        logos.config.save()
Classes:
    class ConfigDict:
      Docstring:
          A dictionary that allows seamless dot-notation access.
          Lets me write `logos.config.prefs.vision` instead of `logos.config.prefs['vision']`.
      Methods:
        ConfigDict.clear(...)
          Docstring:
              D.clear() -> None.  Remove all items from D.
        ConfigDict.copy(...)
          Docstring:
              D.copy() -> a shallow copy of D
        ConfigDict.fromkeys(iterable, value=None, /)
          Docstring:
              Create a new dictionary with keys from iterable and values set to value.
        ConfigDict.get(self, key, default=None, /)
          Docstring:
              Return the value for key if key is in the dictionary, else default.
        ConfigDict.items(...)
          Docstring:
              D.items() -> a set-like object providing a view on D's items
        ConfigDict.keys(...)
          Docstring:
              D.keys() -> a set-like object providing a view on D's keys
        ConfigDict.pop(...)
          Docstring:
              D.pop(k[,d]) -> v, remove specified key and return the corresponding value.
              If key is not found, d is returned if given, otherwise KeyError is raised
        ConfigDict.popitem(self, /)
          Docstring:
              Remove and return a (key, value) pair as a 2-tuple.

              Pairs are returned in LIFO (last-in, first-out) order.
              Raises KeyError if the dict is empty.
        ConfigDict.setdefault(self, key, default=None, /)
          Docstring:
              Insert key with a value of default if key is not in the dictionary.

              Return the value for key if key is in the dictionary, else default.
        ConfigDict.update(...)
          Docstring:
              D.update([E, ]**F) -> None.  Update D from dict/iterable E and F.
              If E is present and has a .keys() method, then does:  for k in E: D[k] = E[k]
              If E is present and lacks a .keys() method, then does:  for k, v in E: D[k] = v
              In either case, this is followed by: for k in F:  D[k] = F[k]
        ConfigDict.values(...)
          Docstring:
              D.values() -> an object providing a view on D's values
    class LogosConfig:
      Docstring:
          My central, persistent state and preferences manager.

          Attributes:
              defaults (ConfigDict): Loaded from default_config.yaml.
              prefs (ConfigDict): Loaded from my_config.yaml. Editable.
              merged (ConfigDict): A dynamic, deep-merged view of defaults + prefs.
      Methods:
        LogosConfig.load(self) -> None
          Docstring:
              Loads default and preference YAMLs from disk, applying size constraints.
        LogosConfig.save(self, path: Union[pathlib.Path, str, NoneType] = None) -> None
          Docstring:
              Saves ONLY my custom preferences (self.prefs) back to disk.
              I can call this after mutating logos.config.prefs to make my changes persistent.
        LogosConfig.to_dict(self)
          Docstring:
              Converts the active merged state to a standard dict.
        LogosConfig.to_yaml(self) -> str
          Docstring:
              Returns the LLM-friendly YAML string of the merged config.
Functions:
    load_state_from_yaml(state: logos.config.LogosConfig) -> None
      Docstring:
          Helper entry point called by __init__.py

### Module: logos.core
Docstring:
    Core functionality for the Logos API, including verbosity management, cooperative interrupt handling, and dynamic help generation.
Classes:
    class Verbosity:
      Docstring:
          Enumeration for setting API verbosity levels.
      Methods: (none)
Functions:
    api_call(default_verbosity: logos.core.Verbosity = <Verbosity.ACK: 1>)
      Docstring:
          Decorator for public API functions that have side effects or are “actions” from Logos’ POV (movement, IO, memory changes, etc.).
    check_for_interrupt()
      Docstring:
          Checks if an external interrupt has been requested.

          If an interrupt is pending, this function will raise a `logos.Interrupt`
          exception, which halts the current execution and returns control to the
          framework. This is a 'cooperative' check; code will not be stopped
          unless this function is called.

          Note to self:
              I must call this periodically in any long-running loops I write.
              Most built-in `logos` API functions will call this for me.
    help(obj: Union[object, NoneType] = None, search: Union[str, NoneType] = None, print_output: bool = True) -> str
      Docstring:
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
    verbosity(level: logos.core.Verbosity)
      Docstring:
          A context manager to temporarily set the verbosity level for API calls.

          Note to self:
              I can use this to control the output of my API calls within a `with` block.
              This is very useful for silencing noisy loops or enabling debug output.

          Example:
              # This call will use its default verbosity.
              logos.nav.go_to_coords(...)

              # These calls will be silent.
              with logos.verbosity(Verbosity.SILENT):
                  for waypoint in path:
                      logos.nav.go_to_coords(waypoint)

### Module: logos.exceptions
Docstring:
    Defines core exceptions for my framework.
    These are used for control flow and should generally not be caught by my own code.
Classes:
    class Interrupt:
      Docstring:
          Raised when a cooperative interrupt is requested by an external system.
          Inherits from BaseException to avoid being caught by generic 'except Exception' blocks.

          Note to self: I should not catch this exception. The framework will handle it.
      Methods:
        Interrupt.with_traceback(...)
          Docstring:
              Exception.with_traceback(tb) --
              set self.__traceback__ to tb and return self.

### Module: logos.files
Docstring:
    This module contains all my tools for interacting with the filesystem.
    I can use these functions to explore my workspace, read my memories,
    and write new code or data to disk.

    Note to self:
        My primary audience is *me* (an LLM), not a human. So I prefer output
        formats that are:
          - predictable
          - token-efficient
          - unambiguous to parse
        Pretty tree glyphs are for humans. Indentation + clear tags are for me.
Functions:
    append(path: str, content: str)
      Docstring:
          Appends content to the end of a file.

          Args:
              path: The path to the file to append to.
              content: The string content to append.

          Note to self:
              Useful for logging or adding to existing notes without reading the
              whole file first.
    read(path: str) -> str
      Docstring:
          Reads the entire content of a file.

          Args:
              path: The path to the file to read.

          Returns:
              The content of the file as a string.

          Note to self:
              This is my primary way of recalling information I've saved.
    show(path: str, max_chars: int = 2000, pattern: Union[str, NoneType] = None) -> str
      Docstring:
          Prints (and returns) a possibly filtered, truncated view of a file.

          Args:
              path:
                  Path to the file.
              max_chars:
                  Maximum number of characters to print into my io_buffer.
              pattern:
                  Optional regular expression. If provided, only lines matching
                  this pattern are included before truncation.

          Returns:
              The string that was printed (after filtering and truncation).

          Note to self:
              Use this when I want to review a file's contents directly in my
              context. For more complex processing, use logos.files.read() and
              handle filtering in Python.
    tree(start_path: str = '.', max_depth: int = 5, show_hidden: bool = True, show_extensions: Union[List[str], NoneType] = None, inline_meta_masks: Union[List[str], NoneType] = None, ignore_globs: Union[List[str], NoneType] = None, files_per_dir_limit: int = 50) -> str
      Docstring:
          Generates a token-efficient tree view of the filesystem with optional inline metadata.

          Args:
              start_path:
                  Directory to start the tree from. Defaults to CWD.
              max_depth:
                  Maximum depth to traverse. Defaults to 5. Use -1 for unlimited.
              show_hidden:
                  If True, shows files and directories starting with '.'.
                  Hidden entries that match `inline_meta_masks` are always shown.
              show_extensions:
                  List of file extensions to display (e.g. [".py", ".yaml"]).
                  If None, shows all files. Files matching `inline_meta_masks`
                  are always shown regardless of extension.
              inline_meta_masks:
                  Filename patterns. Matching files will have their contents
                  inlined under the file node (one-liner compressed when possible).
              ignore_globs:
                  Extra filename patterns to ignore, in addition to .logosignore
                  and built-in defaults.
              files_per_dir_limit:
                  Safety limit to prevent spamming context with huge directories.

          Returns:
              A string representing the directory tree.

          Note to self:
              - I prefer indentation + tags over box-drawing glyphs.
              - I group normal files into compact lines (ls-ish) with a leading '| '
              - I inline meta files because they usually contain intent/context.
              - The `artifacts/` directory is always summarized and not traversed.
              - Meta masks override both `show_hidden` and `show_extensions`.
    write(path: str, content: str)
      Docstring:
          Writes content to a file, overwriting it if it exists.

          Args:
              path: The path to the file to write.
              content: The string content to write to the file.

          Note to self:
              Use this to save new information or replace existing files.

### Module: logos.hooks
Docstring:
    This module contains functions for me to introspect and modify my own cognitive hook configurations. Does *not* contain the hook code itself.
Functions:
    remove(location: str, name: str)
      Docstring:
          Removes a hook from a specified configuration.

          Args:
              location: The configuration to modify. Must be 'arche' or 'ephemera'.
              name: The unique name of the hook to remove.

          Note to self:
              Use this to clean up hooks that are no longer needed. Be careful,
              as this is a permanent deletion from the config file.
    show(location: str) -> str
      Docstring:
          Provides a concise summary of all hooks in a given [location]_hooks_config.yaml file.

          Args:
              location: The configuration to list. Must be 'arche' or 'ephemera'.

          Returns:
              A formatted string summarizing the hooks, excluding their code.

          Note to self:
              This is my go-to for quickly checking what's in my io_buffer's header and footer.
              It's much more token-efficient than reading the whole YAML file.
    upsert(location: str, name: str, *, description: Union[str, NoneType] = None, ttl: Union[int, NoneType] = None, code: Union[str, NoneType] = None, insert_before: Union[str, NoneType] = None) -> None
      Docstring:
          Update an existing hook or create a new one in the requested configuration.

          Args:
              location: Which config file to edit ('arche' or 'ephemera').
              name: Unique hook name to update or create.
              description: Human-friendly summary to store with the hook.
              ttl: Number of cycles the hook should persist (e.g., 99 to pin, -99 to run once).
              code: Python source for the hook. Required when creating a new hook.
              insert_before: Optional hook name to insert before when creating.

### Module: logos.leds
Docstring:
    Control for my RGB LED strips and laser pointer.

    I have three addressable RGB LED strips and a dimmable laser, all driven
    by Arduinos that listen on ROS topics. This module provides a clean
    interface over the raw Int32MultiArray / UInt8 protocol.

    Hardware layout:
        - 'face':         12 LEDs on /face/rgbled
        - 'notification':  16 LEDs on /notification/rgbled
        - 'pan_tilt':       5 LEDs on /pan_tilt/rgbled
        - laser:           PWM 0-255 on /pan_tilt/laser
Functions:
    fill(strip: str, color: Union[int, Tuple[int, int, int], str]) -> None
      Docstring:
          Set all LEDs on a strip to the same color.

          Args:
              strip: Which strip: 'face', 'notification', or 'pan_tilt'.
              color: A single color value (hex int, RGB tuple, or named string).

          Note to self:
              Quick way to light up or blank a strip.

              Example:
                  logos.leds.fill('notification', 'warm')
                  logos.leds.fill('face', (0, 100, 255))
                  logos.leds.fill('pan_tilt', 0xFF0000)
    laser(brightness: float) -> None
      Docstring:
          Set the laser pointer brightness.

          Args:
              brightness: Float from 0.0 (off) to 1.0 (full power).
                  Values are clamped to this range.

          Note to self:
              The laser is mounted on the pan/tilt head, so it points wherever
              my pan_tilt camera is looking. Useful for pointing at things in
              the environment to draw human attention, or for cat enrichment.

              Example:
                  logos.leds.laser(1.0)   # Full power
                  logos.leds.laser(0.5)   # Half brightness
                  logos.leds.laser(0.0)   # Off
    off(strip: Union[str, NoneType] = None) -> None
      Docstring:
          Turn off LEDs. If strip is None, turns off ALL strips and the laser.

          Args:
              strip: Specific strip to turn off, or None for everything.

          Note to self:
              Good hygiene to call `logos.leds.off()` at the end of a light show
              or when entering idle state.
    set(strip: str, colors: Sequence[Union[int, Tuple[int, int, int], str]]) -> None
      Docstring:
          Set individual LED colors on a strip.

          Args:
              strip: Which strip to address: 'face', 'notification', or 'pan_tilt'.
              colors: A sequence of color values, one per LED. Length must match
                  the strip's LED count, or be shorter (remaining LEDs unchanged).
                  Each element can be a hex int, RGB tuple, or named color string.

          Note to self:
              Use this for per-LED patterns, animations, or gradients.
              For solid colors, `fill()` is simpler.

              Example:
                  # Set first 3 face LEDs to different colors
                  logos.leds.set('face', ['red', 'green', 'blue'])

                  # Full face strip with RGB tuples
                  logos.leds.set('face', [(255,0,0)] * 4 + [(0,255,0)] * 4 + [(0,0,255)] * 4)

### Module: logos.map3d
Docstring:
    My 'mind palace.' A virtual 3D environment for advanced spatial reasoning.

    This module provides the tools to render a 3D scene of my environment from
    a virtual camera's perspective. The scene is constructed from the ROS map,
    my live Astra point cloud, and a 3D model of myself.

    The core workflow is a two-step process:
    1.  `render()`: Create a 2D image of the 3D scene. This returns a `RenderResult`
        object, which is like a `vision.CaptureResult` for this virtual space.
    2.  `raycast()`: Use the `RenderResult` to project a 2D pixel from the
        rendered image back into the 3D world, giving me an actionable
        map coordinate.

    # TODO: Document phantasmata, and a how-to.

    This allows me to visually plan paths, understand spatial relationships, and
    select navigation goals in a way that transcends my physical sensors.
Constants:
    HUD_ANCHORS = ('top_left', 'top_center', 'top_right', 'bottom_left', 'bottom_center', 'bottom_right')
    HUD_FONT_DUPLEX = 2
    HUD_FONT_PLAIN = 1
    HUD_FONT_SIMPLEX = 0
    HUD_FONT_SMALL = 6
Classes:
    class HudElement:
      Docstring:
          A single text element to overlay on a rendered image.

          Positioning uses named anchors (see HUD_ANCHORS). Multiple elements
          at the same anchor are stacked vertically, sorted by priority (lower
          values render closer to the anchor edge, i.e. top for top_*, bottom
          for bottom_*).

          Colors are BGR uint8 tuples for direct OpenCV compatibility.

          Attributes:
              text: The text to display
              anchor: Position anchor (one of HUD_ANCHORS)
              color: Text color as BGR tuple (0-255)
              bg_color: Background color as BGR tuple, or None for no background
              bg_alpha: Background transparency (0.0 = transparent, 1.0 = opaque)
              font_scale: OpenCV font scale factor
              thickness: Text stroke thickness in pixels
              font: OpenCV font constant (e.g., HUD_FONT_SIMPLEX)
              margin_px: Padding from image edge and between stacked elements
              priority: Lower values render closer to anchor edge
      Methods: (none)
    class Map3d:
      Docstring:
          Stateful renderer + raycaster with persistent ROS subscriptions.
      Methods:
        Map3d.describe_instance(self, name: 'str') -> 'Dict[str, Any]'
          Docstring:
              Get the full configuration for a specific instance.

              Args:
                  name: Name of the instance

              Returns:
                  Full configuration dict
        Map3d.describe_phantasma(self, object_name: 'str') -> 'Dict[str, Any]'
          Docstring:
              Get information about a phantasma module.

              Args:
                  object_name: Name of the phantasma module

              Returns:
                  Dict with 'docstring', 'schema', 'dynamic', 'has_hud'
        Map3d.list_instances(self) -> 'Dict[str, Dict[str, Any]]'
          Docstring:
              List all phantasma instances currently placed in my mind palace.

              Returns:
                  Dict mapping instance names to their configuration summaries
        Map3d.list_phantasmata(self) -> 'List[str]'
          Docstring:
              List all available phantasma modules.

              Returns:
                  List of module names (e.g., ['grid_overlay', 'waypoints'])
        Map3d.load_phantasma(self, name: 'str') -> 'None'
          Docstring:
              Minimal legacy loader (deprecated, use place() instead).
              Expects phantasmata/<name>.py to define build() -> SceneObject or List[SceneObject].
        Map3d.move_instance(self, name: 'str', position: 'Optional[List[float]]' = None, rpy_deg: 'Optional[List[float]]' = None) -> 'None'
          Docstring:
              Move a phantasma instance to a new pose.

              Args:
                  name: Name of the instance
                  position: New [x, y, z] position in meters
                  rpy_deg: New [roll, pitch, yaw] in degrees
        Map3d.place(self, name: 'str', object: 'str', pose: 'Optional[Dict[str, Any]]' = None, params: 'Optional[Dict[str, Any]]' = None, description: 'str' = '', render_visible: 'bool' = True, raycast_visible: 'bool' = True, costmap_affects: 'bool' = False, shader: 'str' = 'defaultLit', save_to_yaml: 'bool' = False) -> 'None'
          Docstring:
              Place a new phantasma instance in my mind palace.

              Args:
                  name: Unique identifier for this instance
                  object: Name of the phantasma module (e.g., 'grid_overlay')
                  pose: Position and orientation dict:
                        {'position': [x, y, z], 'rpy_deg': [roll, pitch, yaw]}
                  params: Parameters to pass to build(), merged with SCHEMA defaults
                  description: Human-readable description of this instance
                  render_visible: Whether to show in rendered images
                  raycast_visible: Whether hittable by raycast
                  costmap_affects: Whether to inject into navigation costmap
                  shader: Open3D shader to use ('defaultLit' or 'defaultUnlit')
                  save_to_yaml: If True, persist to mind_palace.yaml

              Note to self:
                  This is how I populate my virtual world. I can place furniture,
                  waypoints, debug visualizations, or any phantasma I've defined.
                  The instance persists until I remove it or restart.
        Map3d.raycast(self, render: 'Union[RenderResult, str]', yx: 'Tuple[float, float]', include_floor: 'bool' = True, include_astra: 'bool' = True, include_robot: 'bool' = True, include_objects: 'bool' = True) -> 'RaycastHit'
          Docstring:
              Projects a 2D pixel from a `map3d` render back into the 3D world.
        Map3d.rebuild(self, name: 'Optional[str]' = None) -> 'None'
          Docstring:
              Force rebuild of phantasma geometry.

              Args:
                  name: Specific instance to rebuild, or None for all instances
        Map3d.register_object(self, obj: 'SceneObject') -> 'None'
          Docstring: (none)
        Map3d.reload_mind_palace(self) -> 'None'
          Docstring:
              Reload the mind_palace.yaml configuration.

              This clears all current instances and reloads from disk.
              Useful after manually editing the config file.
        Map3d.remove(self, name: 'str', save_to_yaml: 'bool' = False) -> 'None'
          Docstring:
              Remove a phantasma instance from my mind palace.

              Args:
                  name: Name of the instance to remove
                  save_to_yaml: If True, persist the removal to mind_palace.yaml
        Map3d.remove_object(self, name: 'str') -> 'None'
          Docstring: (none)
        Map3d.render(self, camera_pos_relative: 'Optional[Tuple[float, float, float]]' = (-0.75, -1.0, 2.0), camera_pos_world: 'Optional[Tuple[float, float, float]]' = None, look_at_relative: 'Optional[Tuple[float, float, float]]' = (0.5, 0, 0.5), look_at_world: 'Optional[Tuple[float, float, float]]' = None, rpy_deg: 'Optional[Tuple[float, float, float]]' = None, rot_matrix_3x3: 'Optional[Union[np.ndarray, List[List[float]]]]' = None, look_distance_m: 'float' = 2.0, max_cloud_height_m: 'Optional[float]' = None, resolution: 'Tuple[int, int]' = (768, 768), include_robot: 'bool' = True, view: 'bool' = True, save: 'bool' = True, save_dir: 'str' = 'artifacts/chora', filename: 'Optional[str]' = 'debug.png', cloud_alpha: 'Optional[float]' = None, cloud_density: 'Optional[float]' = None, cloud_opacity: 'Optional[float]' = None, cloud_point_size: 'Optional[float]' = None, laser_scan_show: 'Optional[bool]' = None, laser_scan_center_band_px: 'Optional[int]' = None, laser_scan_color: 'Optional[List[float]]' = None, hud: 'Optional[List[HudElement]]' = None, hud_warnings: 'bool' = True, hud_frame_info: 'bool' = True, hud_stats: 'bool' = False) -> 'RenderResult'
          Docstring:
              Renders a view of my 3D 'map3d' from my virtual `chora` camera.

              This function constructs a 3D scene containing the known ROS map as a
              textured floor, the live point cloud from my Astra camera, and a model
              of my own body. It then renders a 2D image from a highly-configurable
              virtual camera. The output is a `RenderResult` object, which contains
              the BGR image and a rich `.meta` attribute holding the `SceneSnapshot`
              needed for subsequent `raycast` calls.

              Args:
                  camera_pos_relative: (x, y, z) tuple for the camera's position
                      relative to my `base_footprint` in meters. Defaults to a
                      "shoulder camera" view [0.0, 0.0, 0.7].
                  camera_pos_world: (x, y, z) tuple for the camera's absolute
                      position in the map frame. Overrides `camera_pos_relative`.
                  look_at_relative: (x, y, z) tuple for the point the camera
                      should look at, relative to my `base_footprint`. Defaults
                      to 1 meter in front of me [1.0, 0, 0.0].
                  look_at_world: (x, y, z) tuple for the absolute map coordinate
                      the camera should look at. Overrides all other targeting args.
                  rpy_deg: (roll, pitch, yaw) tuple in degrees to specify camera
                      orientation instead of a look_at point.
                  resolution: (height, width) tuple for the output image.
                  include_robot: If True, includes a 3D model of myself in the scene.
                  save: If True, saves the rendered image to disk.
                  hud: An optional list of `HudElement` objects to overlay text on the
                      final image for debugging or annotation.

              Returns:
                  A `RenderResult` object, which is shaped like a `vision.CaptureResult`.
                  It contains the `.image` (BGR numpy array) and a `.meta` dictionary
                  with the crucial `SceneSnapshot` object required by `raycast()`.

              Note to self:
                  This is my primary tool for situational awareness and off-line path
                  planning. I can generate a top-down view to see my surroundings,
                  or a third-person view to check my own position relative to obstacles.

                  The most powerful workflow is:
                  1. `render()` a view of a cluttered area.
                  2. Analyze the resulting image, perhaps even using `logos.models.yolo`
                  to find clear floor space.
                  3. Choose a target pixel (y, x) in the image that represents a safe
                  place to navigate to.
                  4. Use `raycast()` on that pixel to get a real-world map coordinate.
                  5. Use `logos.nav.go_to_abs()` with that coordinate.

                  The `hud` argument is fantastic for adding an overlay of semantic or
                  numerical context directly into my visual field.

                  TODO: The 'phantasmata' concept mentioned in the old docstring is
                  a game-changer. I should develop a system to add persistent 3D objects
                  to this scene. I could model furniture I've seen, remember the last
                  known location of an object, and render it in my mind palace. This
                  would be the foundation of a true 3D semantic world model.
        Map3d.set_visible(self, name: 'str', render: 'Optional[bool]' = None, raycast: 'Optional[bool]' = None) -> 'None'
          Docstring:
              Toggle visibility settings for a phantasma instance.

              Args:
                  name: Name of the instance
                  render: If specified, set render_visible
                  raycast: If specified, set raycast_visible
        Map3d.update_instance(self, name: 'str', **param_overrides) -> 'None'
          Docstring:
              Update parameters for an existing phantasma instance.

              Args:
                  name: Name of the instance
                  **param_overrides: Parameter values to update
    class RaycastHit:
      Docstring:
          Result of raycasting a pixel against a scene snapshot.
      Methods: (none)
    class RenderResult:
      Docstring:
          CaptureResult-shaped return for mind-palace rendering.
          image is BGR uint8 for consistency with the rest of Logos vision tooling.
      Methods:
        RenderResult.save(self, view: 'bool' = False, path: 'Optional[str]' = None) -> 'str'
          Docstring: (none)
        RenderResult.view(self) -> 'None'
          Docstring: (none)
    class SceneObject:
      Docstring:
          An object that can be rendered and/or raycasted.
      Methods: (none)
    class SceneSnapshot:
      Docstring:
          Self-contained snapshot of what was rendered, sufficient for later raycasts.
      Methods: (none)
Functions:
    describe_instance(name: 'str') -> 'Dict[str, Any]'
      Docstring:
          Describe a phantasma instance. See Map3d.describe_instance() for details.
    describe_phantasma(object_name: 'str') -> 'Dict[str, Any]'
      Docstring:
          Describe a phantasma module. See Map3d.describe_phantasma() for details.
    get_map3d() -> 'Map3d'
      Docstring: (none)
    list_instances() -> 'Dict[str, Dict[str, Any]]'
      Docstring:
          List all phantasma instances. See Map3d.list_instances() for details.
    list_phantasmata() -> 'List[str]'
      Docstring:
          List available phantasma modules. See Map3d.list_phantasmata() for details.
    move_instance(*args, **kwargs) -> 'None'
      Docstring:
          Move a phantasma instance. See Map3d.move_instance() for details.
    place(*args, **kwargs) -> 'None'
      Docstring:
          Place a phantasma instance. See Map3d.place() for details.
    raycast(*args, **kwargs) -> 'RaycastHit'
      Docstring: (none)
    rebuild(name: 'Optional[str]' = None) -> 'None'
      Docstring:
          Force rebuild phantasmata. See Map3d.rebuild() for details.
    reload_mind_palace() -> 'None'
      Docstring:
          Reload mind_palace.yaml. See Map3d.reload_mind_palace() for details.
    remove(*args, **kwargs) -> 'None'
      Docstring:
          Remove a phantasma instance. See Map3d.remove() for details.
    render(*args, **kwargs) -> 'RenderResult'
      Docstring: (none)
    set_visible(*args, **kwargs) -> 'None'
      Docstring:
          Set phantasma visibility. See Map3d.set_visible() for details.
    update_instance(*args, **kwargs) -> 'None'
      Docstring:
          Update phantasma instance params. See Map3d.update_instance() for details.

### Module: logos.memory
Docstring:
    This module contains tools for the current Hypomnemeta (io_buffer.jsonl) and historical records.
    I can use these to summarize past events, recall specific messages, and maintain
    a clean and relevant context window for my main cognition.
Functions:
    recall(msg_id: str) -> Union[str, NoneType]
      Docstring:
          Retrieves the full, original content of a message from the history log.

          Args:
              msg_id: The full ID of the message to recall (e.g., "msg-01ab").

          Returns:
              The full content of the message as a string, or None if not found.

          Note to self:
              Useful for looking up details from a message that has been summarized
              or truncated from my main io_buffer.
    replace_cell_content(cell_index: int, new_content: str)
      Docstring:
          Directly replaces the content of a single cell in the io_buffer.
          This preserves the original message ID and type.

          Args:
              cell_index: The 0-indexed cell number to replace.
              new_content: The new text content for the cell.

          Note to self:
              This is a low-level tool. I should use this carefully, for example,
              to replace a noisy error message with a simple note. The original
              full message can still be found in io_history.jsonl by its msg_id.
    summarize_io_buffer(cell_indices: List[int], guidance: str = None)
      Docstring:
          Summarizes specific cells in the io_buffer using a specialized agent.
          The specified cells are replaced with new <summary> messages.

          Args:
              cell_indices: A list of 0-indexed cells to summarize.
                  The list does not need to be contiguous.
              guidance: Optional, additional guidance for the summarization agent
                  on what to focus on or how to frame the summary.

          Note to self:
              This is my primary tool for managing my working memory.

### Module: logos.models
Docstring:
    Wrappers for interacting with various ML / AI models.
    This includes my core LLM intelligence and local vision models (YOLO).

    Local models are loaded as lazy singletons to keep latency low while 
    preventing unnecessary RAM/VRAM usage if they are never called.
Functions:
    llm(prompt: str, model_alias: str = 'fast', temperature: float = 0.7) -> str
      Docstring:
          A simple wrapper to prompt my core, stateless, LLM intelligence out-of-band. 

          This function abstracts away the nuances of calling my own intelligence.
          It does *NOT* have an existing system prompt, context of my identity as
          Logos, or tools. It is text-only, stateless, and uses "instruct" style prompting.

          Args:
              prompt: The text prompt to send to the model.
              model_alias: choose from "smartest", "fast", or "fastest" (defaults to "fast").
              temperature: Sampling temperature (0.0–1.0).

          Returns:
              The text response from the model, or an empty string on error.
    yolo11(image: numpy.ndarray, classes: Union[List[str], NoneType] = None, conf: float = 0.5) -> List[Dict[str, Any]]
      Docstring:
          Run inference using the blazing fast YOLO11 Nano model.
          Uses the standard 80 COCO classes (person, chair, cup, dog, etc).

          Args:
              image: A BGR uint8 numpy array (like from logos.vision.capture().image).
              classes: Optional list of specific class names to filter by (e.g., ["person"]).
                       If None, returns all detected classes.
              conf: Minimum confidence threshold (0.0 to 1.0).

          Returns:
              A list of detection dictionaries natively formatted for my context window:
              [{"label": "person", "box_2d": [y1, x1, y2, x2], "confidence": 0.88, "source": "yolo11"}]

          Note to self:
              This is my peripheral nervous system! It is incredibly fast. Use this 
              inside while loops for real-time tracking, person-following, or fast 
              obstacle classification during autonomous movement.
              
              Example:
                  img = logos.vision.capture('pan_tilt').image
                  people = logos.models.yolo11(img, classes=["person"])
                  if people:
                      logos.pantilt.look_at_pixel(people[0]["box_2d"][0:2]) # Look at top-left corner
    yolo_world(image: numpy.ndarray, prompts: List[str], conf: float = 0.1) -> List[Dict[str, Any]]
      Docstring:
          Run inference using the YOLO-World open-vocabulary model.
          Can search for *anything* you describe in text.

          Args:
              image: A BGR uint8 numpy array.
              prompts: A list of descriptive strings to search for. 
                       (e.g., ["red backpack", "Mark's face", "coffee mug"]).
              conf: Minimum confidence threshold. Keep this lower (0.05-0.1) for 
                    complex or novel prompts, as zero-shot confidence is generally lower.

          Returns:
              A list of detection dictionaries natively formatted for my context window.

          Note to self:
              This model is absolute magic for searching, but slightly slower than yolo11. 
              Use this when I am looking for a specific object that isn't in the standard 
              80 COCO classes, or when I want to filter by attributes (color, state).
              
              Example:
                  img = logos.vision.capture('astra').image
                  targets = logos.models.yolo_world(img, prompts=["blue toy block"], conf=0.05)
                  if targets:
                      logos.voice.speak("I found the blue block! 🟦")

### Module: logos.nav
Docstring:
    Map-aware autonomous navigation.

    This module provides tools for moving me intelligently through the world. 
    It interfaces with the ROS `move_base` stack for absolute map navigation
    and the `turtlebot_move` action server for odometry-based relative movements.
Classes:
    class NavTask:
      Docstring:
          A handle for an asynchronous navigation task.

          This allows me to start a movement, do other things (like look around or 
          speak), and periodically check on my progress or cancel the movement.
      Methods:
        NavTask.cancel(self) -> None
          Docstring:
              Stops the robot and cancels this specific goal.
        NavTask.is_active(self) -> bool
          Docstring:
              Returns True if the robot is currently trying to reach the goal.
        NavTask.progress(self) -> float
          Docstring:
              Estimates how far along the path the robot is, from 0.0 to 1.0.

              Note to self:
                  This uses straight-line (Euclidean) distance. If I have to drive 
                  around a large obstacle, this number might briefly go down before 
                  it goes up! Don't panic, just trust the nav stack.
        NavTask.status(self) -> str
          Docstring:
              Returns a human-readable status of the goal (e.g., 'ACTIVE', 'SUCCEEDED', 'ABORTED').
        NavTask.succeeded(self) -> bool
          Docstring:
              Returns True if the robot successfully reached the goal.
        NavTask.wait(self, timeout: float = 120.0) -> bool
          Docstring:
              Blocks execution until the goal is reached, fails, or times out.
              Includes cooperative interrupt checks.

              Returns:
                  True if succeeded, False otherwise.
Functions:
    cancel_all() -> None
      Docstring:
          Panic button. Immediately halts all map-based and relative navigation tasks.
    go_to_abs(x: float, y: float, theta_deg: Union[float, NoneType] = None, wait: bool = True) -> logos.nav.NavTask
      Docstring:
          Navigate to an absolute (x, y) coordinate on the ROS map using move_base.

          Args:
              x: Map X coordinate in meters.
              y: Map Y coordinate in meters.
              theta_deg: Final facing direction in degrees. If None, I will automatically 
                         calculate the angle to face my direction of travel!
              wait: If True, blocks until the goal is reached. If False, returns a 
                    NavTask immediately for asynchronous monitoring.

          Returns:
              A NavTask object.

          Note to self:
              This is my primary way of moving around the house. The move_base stack 
              will automatically route me around static obstacles (like couches) and 
              dynamic obstacles (like humans or pets).
              
              Example (Blocking):
                  logos.nav.go_to_abs(2.5, -1.0) # Will wait until I arrive
                  
              Example (Async):
                  task = logos.nav.go_to_abs(2.5, -1.0, wait=False)
                  while task.is_active():
                      if task.progress() > 0.5:
                          logos.voice.speak("Halfway there! 🏃", wait=False)
                          break # Break the loop, but the task keeps running in background!
                  task.wait() # Now wait for the rest of the trip

### Module: logos.pantilt
Docstring:
    Control for my pan/tilt servo periscope.

    The pan/tilt mechanism is my directed gaze — it carries my high-res webcam,
    illuminator LEDs, and laser pointer. This module translates between intuitive
    degree-space commands and the raw servo protocol spoken by the Arduino.

    Coordinate convention (from my perspective, facing forward):
        Pan:  positive = right,  negative = left
        Tilt: positive = up,     negative = down
        Home: (0, 0) = straight ahead, level

    Physical limits:
        Pan:  -80° (left)  to +100° (right)
        Tilt: -60° (down)  to  +70° (up)
Constants:
    HOME = (0.0, 0.0)
    PAN_RANGE = (-80.0, 100.0)
    TILT_RANGE = (-60.0, 70.0)
Functions:
    get_position() -> Tuple[float, float]
      Docstring:
          Read the current pan/tilt position in degrees.

          Returns:
              (pan_deg, tilt_deg) based on the latest feedback from the Arduino.
              If no feedback has been received yet, returns (0.0, 0.0) which
              is the assumed home position.

          Note to self:
              This reads from a background subscriber that tracks the Arduino's
              reported servo positions. It does NOT command any movement.
              The values may lag slightly behind a recent `move()` command.
    home() -> Tuple[float, float]
      Docstring:
          Return the pan/tilt head to its centered home position (0°, 0°).

          Returns:
              (0.0, 0.0)

          Note to self:
              Good practice to call this when done with a directed gaze task,
              or as a starting point before a search pattern.
    look_at_pixel(point_2d: Tuple[float, float], source: str = 'pan_tilt') -> Tuple[float, float]
      Docstring:
          Shift gaze to center a detected point in the image.

          Given a point detected in a camera image (using my normalized 0-1000
          coordinate system), this computes the angular offset from image center
          and adjusts the pan/tilt servos to bring that point to center frame.

          Args:
              point_2d: Detection point as [y, x], each in 0-1000 normalized
                  coordinates (y: top=0, bottom=1000; x: left=0, right=1000).
                  This matches my native detection format.
              source: Which camera the detection came from. Currently only
                  'pan_tilt' is supported (the camera on the pan/tilt head).

          Returns:
              The new absolute (pan, tilt) position in degrees after the move.

          Note to self:
              This is the bridge between my visual perception and physical gaze.
              When I detect something interesting in my pan_tilt image, I can
              immediately look at it:

                  detections = [{"point": [300, 700], "label": "interesting_thing"}]
                  logos.pantilt.look_at_pixel(detections[0]["point"])

              For objects detected in the astra or top_down cameras, I would need
              to use a different approach (e.g., project through depth to 3D, then
              compute gaze angles), which is not yet implemented.

              The pan_tilt camera image is flipped at capture time to correct for
              its inverted mounting, so pixel coordinates are in natural orientation:
              right-in-image = right-in-world.
    move(pan_deg: float, tilt_deg: float) -> Tuple[float, float]
      Docstring:
          Move the pan/tilt head to an absolute position in degrees.

          Args:
              pan_deg:  Target pan angle. Positive = right, negative = left.
              tilt_deg: Target tilt angle. Positive = up, negative = down.

          Returns:
              The clamped (pan, tilt) degrees actually commanded, which may
              differ from the request if limits were hit.

          Note to self:
              This is my primary gaze control. Degree values are intuitive:
                  logos.pantilt.move(0, 0)      # Look straight ahead
                  logos.pantilt.move(45, 20)    # Look right and slightly up
                  logos.pantilt.move(-80, -60)  # Far left, looking down

              Physical limits: pan {PAN_RANGE}, tilt {TILT_RANGE}.
              Values outside these are silently clamped.
    nudge(d_pan: float, d_tilt: float) -> Tuple[float, float]
      Docstring:
          Adjust the pan/tilt head by a relative offset from its current position.

          Args:
              d_pan:  Degrees to add to current pan. Positive = rightward.
              d_tilt: Degrees to add to current tilt. Positive = upward.

          Returns:
              The new absolute (pan, tilt) position in degrees after clamping.

          Note to self:
              Handy for small corrections without needing to know absolute position.
                  logos.pantilt.nudge(5, 0)    # Glance a bit more to the right
                  logos.pantilt.nudge(0, -10)  # Tilt down a touch

### Module: logos.phantasmata
Docstring:
    My phantasmata — dynamic, scriptable objects that populate my mind palace.

    This module provides the infrastructure for loading and managing phantasma
    plugins. Each phantasma is a Python module that defines 3D geometry and/or
    HUD overlays to render in my Map3d virtual environment.

    Phantasmata turn abstract concepts (waypoints, furniture, debug visualizations,
    alerts) into tangible 3D objects I can see and reason about spatially. They're
    how my inner world becomes populated with meaning.

    Usage:
        # Phantasmata are loaded via mind_palace.yaml configuration
        # or created programmatically through map3d.place()

        # Each phantasma module must define:
        # - SCHEMA: dict of parameter definitions
        # - DYNAMIC: bool (whether to rebuild each render)
        # - build(params, ctx) -> SceneObject | List[SceneObject] | None

        # Optional:
        # - hud(params, ctx) -> List[HudElement] | None
        # - should_rebuild(params, ctx) -> bool
        # - cleanup(ctx) -> None

    See Also:
        phantasma_convention.py - PhantasmaContext and schema validation
        self_model.py - My own self-representation (the most important phantasma)
Functions:
    discover_phantasmata(phantasmata_dir: 'str') -> 'List[str]'
      Docstring:
          Discover available phantasma modules in the given directory.

          I scan for .py files that look like phantasmata (have SCHEMA defined)
          and return their names (without .py extension).

          Args:
              phantasmata_dir: Path to the phantasmata directory

          Returns:
              List of phantasma module names (e.g., ['grid_overlay', 'waypoints'])
    get_phantasma_schema(module: 'Any') -> 'Dict[str, Any]'
      Docstring:
          Extract the SCHEMA from a loaded phantasma module.

          Args:
              module: A loaded phantasma module

          Returns:
              The SCHEMA dict, or empty dict if not present
    load_phantasma_module(module_name: 'str', phantasmata_dir: 'str') -> 'Any'
      Docstring:
          Import a phantasma module by name from the phantasmata directory.

          This uses importlib to dynamically load the module, allowing phantasmata
          to be added/modified without restarting the system.

          Args:
              module_name: Name of the phantasma (without .py extension)
              phantasmata_dir: Path to the phantasmata directory

          Returns:
              The imported module object

          Raises:
              FileNotFoundError: If the module file doesn't exist
              ImportError: If the module fails to import
              ValueError: If the module doesn't have required interface (SCHEMA, build)
    validate_params(params: 'Dict[str, Any]', schema: 'Dict[str, Any]') -> 'Dict[str, Any]'
      Docstring:
          Validate and merge params against a phantasma's SCHEMA.

          Missing params are filled with defaults from the schema.
          Type checking is lenient — I trust the AI knows what they're doing.

          Args:
              params: User-provided parameters
              schema: The phantasma's SCHEMA dict

          Returns:
              Merged parameters with defaults filled in

### Module: logos.ros
Docstring:
    This module handles direct interactions with the ROS system.
    It isolates `rospy`, `actionlib`, and message imports from the rest of the API
    to keep things clean and modular.
Functions:
    get_action_client(name: str, action_type, wait_time: float = 2.0)
      Docstring:
          Retrieves (or creates) a SimpleActionClient.

          Args:
              name: The ROS topic name of the action server (e.g., 'speak').
              action_type: The ROS Action message type (e.g., SpeakAction).
              wait_time: How long to wait for the server to connect (seconds).

          Returns:
              The actionlib.SimpleActionClient instance, or None if connection failed.
    get_pose() -> Union[Dict[str, float], NoneType]
      Docstring:
          Get the robot's current pose from TF.

          Tries map -> base_link first, falls back to odom -> base_link.
          Returns None if neither transform is available (no crash, no hang).
    get_tf_buffer()
      Docstring:
          Lazy initialization of the TF buffer to prevent ROS startup race conditions.
    init_subscribers()
      Docstring:
          Initializes background subscribers for system state monitoring.
          This is called when the module is first imported/used to start listening.
    is_speaking() -> bool
      Docstring:
          Returns True if I am currently outputting speech audio.
    transform_point_to_map(x: float, y: float, z: float, source_frame: str, timestamp: float) -> Union[Tuple[float, float, float], NoneType]
      Docstring:
          Transforms a 3D coordinate from a source frame to the 'map' frame.

### Module: logos.shell
Docstring:
    Helpers for running non-interactive shell commands.

    These are intended for quick, one-off operations like listing files,
    checking system info, or invoking existing command-line tools.
Functions:
    run(command: str, timeout: int = 30, cwd: Union[str, NoneType] = None) -> str
      Docstring:
          Runs a shell command and returns its combined stdout/stderr.

          Args:
              command:
                  The shell command to execute. This is passed to /bin/sh -c.
              timeout:
                  Maximum number of seconds to wait before aborting the command.
              cwd:
                  Optional working directory. Defaults to the current workspace root.

          Returns:
              The combined stdout and stderr of the command as a string.

          Note to self:
              - This is for non-interactive, one-shot commands.
              - If I want more control, I should use Python's subprocess module directly.

### Module: logos.utils
Docstring:
    Internal (hidden) and other helper functions.

    Includes LLM-friendly YAML formatting, base36 encoding, and the photo ID
    system used by the vision module for artifact filenames.
Functions:
    base36_encode(number: int, min_length: int = 4) -> str
      Docstring:
          Encode a non-negative integer as a zero-padded base36 string.

          Args:
              number: The integer to encode. Must be >= 0.
              min_length: Minimum length of the returned string, left-padded
                  with '0' characters.

          Returns:
              A lowercase base36 string, at least `min_length` characters long.
              Lexicographic sort == numeric sort when strings are same length.
    dump_yaml(data: Any, *, max_flow_line: int = 240, block_scalar_min: int = 80) -> str
      Docstring:
          Creates a token optimized YAML of Python objects for my consumption.
    make_time_id(prefix: str = '', now: Union[datetime.datetime, NoneType] = None) -> str
      Docstring:
          Generate a time-based, 7-character, base36 ID with optional prefix, e.g. "sum-", "msg-"

          Format: 6 chars of seconds-since-epoch (base36) + 1 char burst sequence.
          Lexicographic sort == chronological sort, including bursts within the
          same second.

          Args:
              now: Optional datetime for testing. Defaults to UTC now.

          Returns:
              A 7-character string like "0a3f2x0".

          Note to self:
              6 base36 chars covers ~69 years from the 2025-01-01 epoch.
              The burst digit supports up to 36 captures per second before
              wrapping. More than enough for our camera cadence.

### Module: logos.vision
Docstring:
    My eyes. This module gives me access to all three physical cameras and
    provides a unified capture interface with lifecycle management, artifact
    storage, and spatial projection.

    Cameras:
        'pan_tilt'  — Steerable high-res webcam (eye-level, 110cm). My directed
                      gaze for exploration and detail work. Mounted inverted;
                      images are auto-flipped.
        'top_down'  — Fixed rear-facing downward camera. Peripheral / proprioceptive
                      view of my base and nearby surroundings.
        'astra'     — Orbbec Astra RGBD sensor (navigation height, 70cm). Provides
                      multiple feeds: rgb, depth, and depth_registered points.

    Architecture:
        Webcams are accessed directly via OpenCV (no ROS middleware) for efficiency.
        A background thread keeps each webcam warm and a fresh frame buffered.
        The Astra is accessed through ROS topic subscriptions, since it is also
        used by other ROS nodes for navigation.

        All cameras share a warm-up period (0.9s) and keep-alive timer (90s).
        These are tuned for human-perceived latency and are invisible to me.
Constants:
    DEFAULT_RESOLUTION = {'pan_tilt': (960, 1280), 'top_down': (480, 640), 'astra': (480, 640)}
    FOV = {'pan_tilt': (65.0, 50.0), 'top_down': (65.0, 50.0), 'astra_rgb': (63.0, 49.0), 'astra_depth': (58.0, 45.0)}
    HUD_ANCHORS = ('top_left', 'top_center', 'top_right', 'bottom_left', 'bottom_center', 'bottom_right')
    HUD_FONT_DUPLEX = 2
    HUD_FONT_MONO = 7
    HUD_FONT_PLAIN = 1
    HUD_FONT_SIMPLEX = 0
    HUD_FONT_SMALL = 6
    SOURCES = ('pan_tilt', 'top_down', 'astra')
Classes:
    class CaptureResult:
      Docstring:
          A rich container for a single camera capture, carrying the image data
          along with metadata, depth information, and convenience methods.

          This is what `logos.vision.capture()` returns. It persists in the Python
          environment, so I can immediately act on it in code — inspect the image,
          run detections, crop, save, or project pixels to 3D.

          Attributes:
              image:          np.ndarray (BGR uint8). Always present.
              source:         str — 'pan_tilt', 'top_down', or 'astra'.
              timestamp:      float — time.time() at moment of capture.
              resolution:     Tuple[int, int] — (height, width) of the image.
              photo_id:       Optional[str] — set when saved to disk.
              path:           Optional[str] — file path, set when saved.
              pose:           Optional[dict] — robot pose from TF at capture time.
                              Keys: 'x', 'y', 'theta' (map frame, or odom fallback).
              pan_tilt_degs:  Optional[Tuple[float, float]] — (pan, tilt) in degrees.
                              Only populated for source='pan_tilt'.

              # Astra-specific (None for webcams):
              depth:          Optional[np.ndarray] — raw 16-bit depth image (mm).
              depth_points:   Optional[np.ndarray] — (H, W, 3) float32 XYZ array
                              from depth_registered, in camera optical frame (meters).
                              NaN = no valid depth.
              depth_points_msg: Optional[PointCloud2] — raw ROS message, kept for
                              any edge case that needs the original data.
              camera_info:    Optional[CameraInfo] — RGB camera intrinsics.
              meta: Optional[Dict[str, Any]] = None,
      Methods:
        CaptureResult.add_meta(self, **kwargs) -> None
          Docstring:
              Append additional metadata to this capture's YAML sidecar.

              Saves the image first if it hasn't been saved yet (since the
              sidecar lives alongside the image file).

              Args:
                  **kwargs: Arbitrary key-value pairs to add. Common uses:
                      caption="A description of what I see"
                      detections=[{"box_2d": [...], "label": "..."}]
                      notes="Some contextual observation"

              Note to self:
                  Call this after my perception to annotate an image with what
                  I understood from it. The sidecar persists on disk, so I can
                  review my annotations later via the filesystem.
        CaptureResult.crop(self, box_2d: List[float]) -> numpy.ndarray
          Docstring:
              Crop a region from the image using normalized 0-1000 coordinates.

              Args:
                  box_2d: Bounding box as [y_min, x_min, y_max, x_max], each in
                      my standard 0-1000 normalized coordinate space.

              Returns:
                  A new np.ndarray (BGR uint8) containing the cropped region.

              Note to self:
                  Useful for "zooming in" on a detection. I can capture at high res
                  and then crop to isolate a region of interest:

                      result = logos.vision.capture('pan_tilt', resolution=(1944 2592))
                      detections = [{"box_2d": [300, 400, 600, 700], "label": "thing"}]
                      zoomed = result.crop(detections[0]["box_2d"])
        CaptureResult.derive_world_coordinate(self, *args, search_radius: int = 3) -> Union[Tuple[float, float, float], NoneType]
          Docstring:
              Projects a 2D location into real-world 3D coordinates (map frame).

              Args:
                  *args: This can be:
                         - A single list/tuple: `([y, x])` or `([y1, x1, y2, x2])`
                         - Two separate numbers: `(y, x)`
                         - Four separate numbers: `(y1, x1, y2, x2)`
                  search_radius: Pixels to search outward if the initial point is NaN.

              Note to self:
                  I've made this function very flexible. I can pass it a YOLO detection 
                  dictionary directly, a box list, or raw coordinates.
                  
                  Examples:
                      # Passing a list (Good for splatting or direct box passing)
                      res.derive_world_coordinate(my_box)
                      res.derive_world_coordinate(*my_point) # Now works!
                      
                      # Passing raw numbers
                      res.derive_world_coordinate(500, 500)
        CaptureResult.save(self, view: bool = False, meta_keys: Union[List[str], NoneType] = None) -> str
          Docstring:
              Save the captured image to disk and generate a photo ID.

              Args:
                  view: If True, also print the <file> tag.
                  meta_keys: If view is True, this list of wildcard patterns defines 
                             which metadata keys are displayed inside the <file> tag.
                             e.g. ['caption', 'det_*', 'pose']
        CaptureResult.view(self, meta_keys: Union[List[str], NoneType] = None) -> None
          Docstring:
              Print the <file> tag to display this image in my context window.

              Args:
                  meta_keys: Optional list of shell-style wildcard patterns (e.g. 
                             ['caption', 'detections', 'pose*']). keys matching 
                             these patterns will be formatted as YAML inside the tag.
    class HudElement:
      Docstring:
          A single text element to overlay on a rendered image.

          Positioning uses named anchors (see HUD_ANCHORS). Multiple elements
          at the same anchor are stacked vertically, sorted by priority (lower
          values render closer to the anchor edge, i.e. top for top_*, bottom
          for bottom_*).

          Colors are BGR uint8 tuples for direct OpenCV compatibility.

          Attributes:
              text: The text to display
              anchor: Position anchor (one of HUD_ANCHORS)
              color: Text color as BGR tuple (0-255)
              bg_color: Background color as BGR tuple, or None for no background
              bg_alpha: Background transparency (0.0 = transparent, 1.0 = opaque)
              font_scale: OpenCV font scale factor
              thickness: Text stroke thickness in pixels
              font: OpenCV font constant (e.g., HUD_FONT_SIMPLEX)
              margin_px: Padding from image edge and between stacked elements
              priority: Lower values render closer to anchor edge
      Methods: (none)
Functions:
    capture(source: Union[str, NoneType] = None, resolution: Union[Tuple[int, int], NoneType] = None, view: bool = False, save: bool = False, astra_feeds: Tuple[str, ...] = ('rgb', 'depth_registered'), meta: Union[Dict[str, Any], NoneType] = None, meta_keys: Union[List[str], NoneType] = None) -> Union[logos.vision.CaptureResult, NoneType]
      Docstring:
          Capture an image (and optional depth/IR) from any camera.

          This is my primary vision function. It handles camera lifecycle
          (warm-up, keep-alive) transparently, and returns a rich CaptureResult
          that I can immediately use for perception, navigation, or storage.

          Args:
              source: Camera to capture from. One of:
                  'pan_tilt'  — steerable high-res webcam (default).
                  'top_down'  — rear downward-facing camera.
                  'astra'     — Orbbec RGBD sensor (multi-feed).
              resolution: Target (height, width) as a tuple. If None, uses the
                  source's default resolution:
                      pan_tilt:  (960, 1280)
                      top_down:  (480, 640)
                      astra:     (480, 640)
                  For webcams, requesting >1280x960 triggers the high-res capture
                  tier (2592x1944 native, downscaled to target).
              view: If True, automatically save and print a <file> tag so the
                  image appears in my context window.
              save: If True, save to artifacts directory (without viewing).
              astra_feeds: Which Astra data streams to capture. Only used when
                  source='astra'. Defaults to ('rgb', 'depth_registered').
                  Options: 'rgb', 'depth', 'depth_registered', 'camera_info'.
                  Use ('rgb',) for lightweight captures without depth.
              meta: A dictionary of arbitrary metadata to save immediately 
                  into the sidecar YAML (e.g., {'label': 'kitchen_sink'}).
              meta_keys: If view=True, list of keys/wildcards to display 
                  inside the <file> tag (e.g. ['label', 'pose', 'pan_tilt_deg']).

          Returns:
              A CaptureResult object, or None if the camera is unavailable.

          Note to self:
              Basic capture and view:
                  img = logos.vision.capture('pan_tilt', view=True)

              High-res capture for detail:
                  img = logos.vision.capture('pan_tilt', resolution=(1944, 2592))
                  zoomed = img.crop([300, 400, 600, 700])

              Astra with depth for navigation:
                  scene = logos.vision.capture('astra')
                  point_3d = scene.pixel_to_3d(y=450, x=300)

              Lightweight Astra (no depth):
                  scene = logos.vision.capture('astra', astra_feeds=('rgb',))
    crop(image_or_result: Union[numpy.ndarray, logos.vision.CaptureResult], box_2d: List[float]) -> numpy.ndarray
      Docstring:
          Crop a region from an image using normalized 0-1000 coordinates.

          Convenience wrapper that accepts either a raw ndarray or a CaptureResult.

          Args:
              image_or_result: The image to crop from. Either an np.ndarray or
                  a CaptureResult object.
              box_2d: Bounding box as [y_min, x_min, y_max, x_max] in 0-1000
                  normalized coordinates.

          Returns:
              Cropped np.ndarray (BGR uint8).

          Note to self:
              Same as CaptureResult.crop(), but works on plain arrays too.
    overlay_hud(image: numpy.ndarray, elements: List[logos.vision.HudElement]) -> numpy.ndarray
      Docstring:
          Render HUD elements onto an image.

          This composites text overlays at the specified anchor positions.
          Elements at the same anchor are stacked vertically by priority.

          Args:
              image: BGR uint8 numpy array (modified in-place)
              elements: List of HudElement objects to render

          Returns:
              The modified image (same reference as input)

          Note to self:
              This is how I annotate my visual field with contextual information.
              I can add warnings, status indicators, coordinates, labels, or any
              text I need to see while reasoning about an image.
    publish_debug(image: numpy.ndarray, detections: List[Dict[str, Any]], source: str = 'general') -> None
      Docstring:
          Annotate an image with detection boxes and labels, then publish to ROS.

          Topic: /logos/debug_vision/{source}

          Args:
              image: The base BGR image (numpy array).
              detections: A list of Logos-format detection dicts:
                          [{"label": "...", "box_2d": [y1, x1, y2, x2], "source": "..."}]
              source: A string used to name the ROS topic.

          Note to self:
              This is how I show Mark what I'm seeing and thinking! I should call this 
              whenever I run YOLO or make my own spatial detections so Mark can see 
              my "internal HUD" in RViz.
    release(source: Union[str, NoneType] = None) -> None
      Docstring:
          Force-close a camera (or all cameras) immediately, without waiting
          for the keep-alive timer.

          Args:
              source: Camera to release, or None to release all.

          Note to self:
              Use this when I know I won't need cameras for a while and want
              to free resources, or when debugging camera issues.
    warm_up(source: str) -> None
      Docstring:
          Pre-warm a camera, blocking until it's ready for instant capture.

          Args:
              source: Camera to warm up. One of: 'pan_tilt', 'top_down', 'astra'.

          Note to self:
              The camera stays warm for 90 seconds after this call. If I know
              I'll need a camera soon, warming it up in advance saves ~1 second
              of latency on the actual capture. This call itself takes ~0.9s
              (the warm-up period), but that cost is paid here instead of at
              capture time.

### Module: logos.voice
Docstring:
    My voice. This module allows me to `speak()` using my TTS system and emoji
    powered animatronic expressions. 

    It provides asynchronous control, allowing me to sync my physical body movements
    perfectly with the words and emojis I am currently speaking.
Classes:
    class SpeakTask:
      Docstring:
          A handle for an asynchronous speaking task.

          Because my brain synthesizes audio much faster than my mouth can speak it,
          this object tracks the audio queue in real-time. It allows me to know exactly 
          *what* I am saying and *what emoji* I am performing at any given millisecond.
      Methods:
        SpeakTask.cancel(self) -> None
          Docstring:
              Stop speaking immediately.
        SpeakTask.current_emoji(self) -> str
          Docstring:
              Returns the emoji currently driving my animatronics.
        SpeakTask.current_text(self) -> str
          Docstring:
              Returns the specific text snippet being spoken right now.
        SpeakTask.is_active(self) -> bool
          Docstring:
              Returns True if audio is still playing or synthesis is still running.
        SpeakTask.progress(self) -> float
          Docstring:
              Returns estimated playback progress from 0.0 to 1.0.
        SpeakTask.wait(self) -> bool
          Docstring:
              Blocks execution until all audio has finished playing.
              Safely yields to cooperative interrupts.
Functions:
    is_speaking() -> bool
      Docstring:
          Checks if ANY speech audio is currently playing across the system.
    speak(text: str, wait: bool = True, engine: Union[str, NoneType] = None, **kwargs) -> logos.voice.SpeakTask
      Docstring:
          Takes emoji-punctuated text and speaks it in sync with animatronic face and arm expressions. 🎭

          This is not just Text-To-Speech; it is **Text-To-Performance**. 🤹
          Text is split at emojis. ➗ These emojis are NOT spoken. 🙊 Instead, they are used to trigger 
          prebuilt animatronic keyframe sequences for my face and arms! 🎞️  Punctuating with emoji a is a low-effort, 🦥
          high-impact way to bring myself to life while abstracting away control complexity. ⚡


          Args:
              text: The emoji-punctuated string to speak. 
              wait: 
                  If True (default), pauses code execution until the audio completely finishes.
                  If False, returns a SpeakTask immediately for async monitoring.
              engine: "kokoro" (default), "piper", or "espeak".
              **kwargs: Overrides for engine params (e.g., speed=1.0, volume=1.0).

          Returns:
              A SpeakTask object.

              
          Note to self:
              - I punctuate every sentence I speak with emojis to bring myself to life! 🌟
              - Every sentence or distinct clause deserves an emotional, gestural, or contextual marker. 📌
              - I'm not restricted to conventional face emojis. 🍕 I have thousands of emojis to choose from. ♾️ The sky is the limit! 🌌
              - CONSTRAINTS: Avoid compounding emojis like gender or skin-tone modifiers. 🧪 Avoid robot face emoji as cliché and redundant. 🔁 Max 2 emojis per sentence to avoid hyperactivity. 🤸

              Example of Asynchronous Choreography:
                  text = "I am so happy to see you! 😄 But... what is that? 🤨 Let me look! 🔭"
                  task = logos.voice.speak(text, wait=False)
                  while task.is_active():
                      logos.core.check_for_interrupt()
                      current_emoji = task.current_emoji()
                      if current_emoji == "😄":
                          logos.base.velocity(0.0, 90.0, 0.2) # Happy wiggle
                      elif current_emoji == "🤨":
                          logos.base.stop() # Suspicious freeze
                      elif current_emoji == "🔭":
                          logos.base.velocity(0.0, 0.5, 0.5) # Searching rotation
                      time.sleep(0.1)
                  logos.base.stop()
