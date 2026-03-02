Help on module logos.map3d in logos:

NAME
    logos.map3d - My 'mind palace.' A virtual 3D environment for advanced spatial reasoning.

DESCRIPTION
    This module provides the tools to render a 3D scene of my environment from
    a virtual camera's perspective. The scene is constructed from the ROS map,
    my live Astra point cloud, and a 3D model of myself.
    
    The core workflow is a two-step process:
    1.  `render()`: Create a 2D image of the 3D scene. This returns a `RenderResult`
        object, which is like a `vision.CaptureResult` for this virtual space.
    2.  `raycast()`: Use the `RenderResult` to project a 2D pixel from the
        rendered image back into the 3D world, giving me an actionable
        map coordinate.
    
    This allows me to visually plan paths, understand spatial relationships, and
    select navigation goals in a way that transcends my physical sensors.

CLASSES
    builtins.object
        Map3d
        RaycastHit
        RenderResult
        SceneObject
        SceneSnapshot
        logos.vision.HudElement
    
    class Map3d(builtins.object)
     |  Map3d(rgb_image_topic: 'str' = '/camera/rgb/image_raw', rgb_info_topic: 'str' = '/camera/rgb/camera_info', points_topic: 'str' = '/camera/depth_registered/points', map_topic: 'str' = '/map', base_frame: 'str' = 'base_footprint', map_frame: 'str' = 'map')
     |  
     |  Stateful renderer + raycaster with persistent ROS subscriptions.
     |  
     |  Methods defined here:
     |  
     |  __init__(self, rgb_image_topic: 'str' = '/camera/rgb/image_raw', rgb_info_topic: 'str' = '/camera/rgb/camera_info', points_topic: 'str' = '/camera/depth_registered/points', map_topic: 'str' = '/map', base_frame: 'str' = 'base_footprint', map_frame: 'str' = 'map')
     |      Initialize self.  See help(type(self)) for accurate signature.
     |  
     |  describe_instance(self, name: 'str') -> 'Dict[str, Any]'
     |      Get the full configuration for a specific instance.
     |      
     |      Args:
     |          name: Name of the instance
     |      
     |      Returns:
     |          Full configuration dict
     |  
     |  describe_phantasma(self, object_name: 'str') -> 'Dict[str, Any]'
     |      Get information about a phantasma module.
     |      
     |      Args:
     |          object_name: Name of the phantasma module
     |      
     |      Returns:
     |          Dict with 'docstring', 'schema', 'dynamic', 'has_hud'
     |  
     |  list_instances(self) -> 'Dict[str, Dict[str, Any]]'
     |      List all phantasma instances currently placed in my mind palace.
     |      
     |      Returns:
     |          Dict mapping instance names to their configuration summaries
     |  
     |  list_phantasmata(self) -> 'List[str]'
     |      List all available phantasma modules.
     |      
     |      Returns:
     |          List of module names (e.g., ['grid_overlay', 'waypoints'])
     |  
     |  load_phantasma(self, name: 'str') -> 'None'
     |      Minimal legacy loader (deprecated, use place() instead).
     |      Expects phantasmata/<name>.py to define build() -> SceneObject or List[SceneObject].
     |  
     |  move_instance(self, name: 'str', position: 'Optional[List[float]]' = None, rpy_deg: 'Optional[List[float]]' = None) -> 'None'
     |      Move a phantasma instance to a new pose.
     |      
     |      Args:
     |          name: Name of the instance
     |          position: New [x, y, z] position in meters
     |          rpy_deg: New [roll, pitch, yaw] in degrees
     |  
     |  place(self, name: 'str', object: 'str', pose: 'Optional[Dict[str, Any]]' = None, params: 'Optional[Dict[str, Any]]' = None, description: 'str' = '', render_visible: 'bool' = True, raycast_visible: 'bool' = True, costmap_affects: 'bool' = False, shader: 'str' = 'defaultLit', save_to_yaml: 'bool' = False) -> 'None'
     |      Place a new phantasma instance in my mind palace.
     |      
     |      Args:
     |          name: Unique identifier for this instance
     |          object: Name of the phantasma module (e.g., 'grid_overlay')
     |          pose: Position and orientation dict:
     |                {'position': [x, y, z], 'rpy_deg': [roll, pitch, yaw]}
     |          params: Parameters to pass to build(), merged with SCHEMA defaults
     |          description: Human-readable description of this instance
     |          render_visible: Whether to show in rendered images
     |          raycast_visible: Whether hittable by raycast
     |          costmap_affects: Whether to inject into navigation costmap
     |          shader: Open3D shader to use ('defaultLit' or 'defaultUnlit')
     |          save_to_yaml: If True, persist to mind_palace.yaml
     |      
     |      Note to self:
     |          This is how I populate my virtual world. I can place furniture,
     |          waypoints, debug visualizations, or any phantasma I've defined.
     |          The instance persists until I remove it or restart.
     |  
     |  raycast(self, render: 'Union[RenderResult, str]', yx: 'Tuple[float, float]', include_floor: 'bool' = True, include_astra: 'bool' = True, include_robot: 'bool' = True, include_objects: 'bool' = True) -> 'RaycastHit'
     |      Projects a 2D pixel from a `map3d` render back into the 3D world.
     |  
     |  rebuild(self, name: 'Optional[str]' = None) -> 'None'
     |      Force rebuild of phantasma geometry.
     |      
     |      Args:
     |          name: Specific instance to rebuild, or None for all instances
     |  
     |  register_object(self, obj: 'SceneObject') -> 'None'
     |  
     |  reload_mind_palace(self) -> 'None'
     |      Reload the mind_palace.yaml configuration.
     |      
     |      This clears all current instances and reloads from disk.
     |      Useful after manually editing the config file.
     |  
     |  remove(self, name: 'str', save_to_yaml: 'bool' = False) -> 'None'
     |      Remove a phantasma instance from my mind palace.
     |      
     |      Args:
     |          name: Name of the instance to remove
     |          save_to_yaml: If True, persist the removal to mind_palace.yaml
     |  
     |  remove_object(self, name: 'str') -> 'None'
     |  
     |  render(self, camera_pos_relative: 'Optional[Tuple[float, float, float]]' = (0.0, 0.0, 0.7), camera_pos_world: 'Optional[Tuple[float, float, float]]' = None, look_at_relative: 'Optional[Tuple[float, float, float]]' = (1.0, 0, 0.0), look_at_world: 'Optional[Tuple[float, float, float]]' = None, rpy_deg: 'Optional[Tuple[float, float, float]]' = None, rot_matrix_3x3: 'Optional[Union[np.ndarray, List[List[float]]]]' = None, look_distance_m: 'float' = 2.0, max_cloud_height_m: 'Optional[float]' = None, resolution: 'Tuple[int, int]' = (768, 768), include_robot: 'bool' = True, view: 'bool' = True, save: 'bool' = True, save_dir: 'str' = 'artifacts/map3d', filename: 'Optional[str]' = 'debug.png', cloud_alpha: 'Optional[float]' = None, cloud_density: 'Optional[float]' = None, cloud_opacity: 'Optional[float]' = None, cloud_point_size: 'Optional[float]' = None, laser_scan_show: 'Optional[bool]' = None, laser_scan_center_band_px: 'Optional[int]' = None, laser_scan_color: 'Optional[List[float]]' = None, hud: 'Optional[List[HudElement]]' = None, hud_warnings: 'bool' = True, hud_frame_info: 'bool' = True, hud_stats: 'bool' = False) -> 'RenderResult'
     |      Renders a view of my 3D 'map3d' from my virtual `theoria` camera.
     |      
     |      This function constructs a 3D scene containing the known ROS map as a
     |      textured floor, the live point cloud from my Astra camera, and a model
     |      of my own body. It then renders a 2D image from a highly-configurable
     |      virtual camera. The output is a `RenderResult` object, which contains
     |      the BGR image and a rich `.meta` attribute holding the `SceneSnapshot`
     |      needed for subsequent `raycast` calls.
     |      
     |      Args:
     |          camera_pos_relative: (x, y, z) tuple for the camera's position
     |              relative to my `base_footprint` in meters. Defaults to a
     |              "shoulder camera" view [0.0, 0.0, 0.7].
     |          camera_pos_world: (x, y, z) tuple for the camera's absolute
     |              position in the map frame. Overrides `camera_pos_relative`.
     |          look_at_relative: (x, y, z) tuple for the point the camera
     |              should look at, relative to my `base_footprint`. Defaults
     |              to 1 meter in front of me [1.0, 0, 0.0].
     |          look_at_world: (x, y, z) tuple for the absolute map coordinate
     |              the camera should look at. Overrides all other targeting args.
     |          rpy_deg: (roll, pitch, yaw) tuple in degrees to specify camera
     |              orientation instead of a look_at point.
     |          resolution: (height, width) tuple for the output image.
     |          include_robot: If True, includes a 3D model of myself in the scene.
     |          save: If True, saves the rendered image to disk.
     |          hud: An optional list of `HudElement` objects to overlay text on the
     |              final image for debugging or annotation.
     |      
     |      Returns:
     |          A `RenderResult` object, which is shaped like a `vision.CaptureResult`.
     |          It contains the `.image` (BGR numpy array) and a `.meta` dictionary
     |          with the crucial `SceneSnapshot` object required by `raycast()`.
     |      
     |      Note to self:
     |          This is my primary tool for situational awareness and off-line path
     |          planning. I can generate a top-down view to see my surroundings,
     |          or a third-person view to check my own position relative to obstacles.
     |      
     |          The most powerful workflow is:
     |          1. `render()` a view of a cluttered area.
     |          2. Analyze the resulting image, perhaps even using `logos.models.yolo`
     |          to find clear floor space.
     |          3. Choose a target pixel (y, x) in the image that represents a safe
     |          place to navigate to.
     |          4. Use `raycast()` on that pixel to get a real-world map coordinate.
     |          5. Use `logos.nav.go_to_abs()` with that coordinate.
     |      
     |          The `hud` argument is fantastic for adding an overlay of semantic or
     |          numerical context directly into my visual field.
     |      
     |          TODO: The 'phantasmata' concept mentioned in the old docstring is
     |          a game-changer. I should develop a system to add persistent 3D objects
     |          to this scene. I could model furniture I've seen, remember the last
     |          known location of an object, and render it in my mind palace. This
     |          would be the foundation of a true 3D semantic world model.
     |  
     |  set_visible(self, name: 'str', render: 'Optional[bool]' = None, raycast: 'Optional[bool]' = None) -> 'None'
     |      Toggle visibility settings for a phantasma instance.
     |      
     |      Args:
     |          name: Name of the instance
     |          render: If specified, set render_visible
     |          raycast: If specified, set raycast_visible
     |  
     |  update_instance(self, name: 'str', **param_overrides) -> 'None'
     |      Update parameters for an existing phantasma instance.
     |      
     |      Args:
     |          name: Name of the instance
     |          **param_overrides: Parameter values to update
     |  
     |  ----------------------------------------------------------------------
     |  Data descriptors defined here:
     |  
     |  __dict__
     |      dictionary for instance variables (if defined)
     |  
     |  __weakref__
     |      list of weak references to the object (if defined)
    
    class HudElement(builtins.object)
     |  HudElement(text: str, anchor: str = 'top_left', color: Tuple[int, int, int] = (255, 255, 255), bg_color: Union[Tuple[int, int, int], NoneType] = (0, 0, 0), bg_alpha: float = 0.4, font_scale: float = 0.45, thickness: int = 1, font: int = 0, margin_px: int = 8, priority: int = 0) -> None
     |  
     |  A single text element to overlay on a rendered image.
     |  
     |  Positioning uses named anchors (see HUD_ANCHORS). Multiple elements
     |  at the same anchor are stacked vertically, sorted by priority (lower
     |  values render closer to the anchor edge, i.e. top for top_*, bottom
     |  for bottom_*).
     |  
     |  Colors are BGR uint8 tuples for direct OpenCV compatibility.
     |  
     |  Attributes:
     |      text: The text to display
     |      anchor: Position anchor (one of HUD_ANCHORS)
     |      color: Text color as BGR tuple (0-255)
     |      bg_color: Background color as BGR tuple, or None for no background
     |      bg_alpha: Background transparency (0.0 = transparent, 1.0 = opaque)
     |      font_scale: OpenCV font scale factor
     |      thickness: Text stroke thickness in pixels
     |      font: OpenCV font constant (e.g., HUD_FONT_SIMPLEX)
     |      margin_px: Padding from image edge and between stacked elements
     |      priority: Lower values render closer to anchor edge
     |  
     |  Methods defined here:
     |  
     |  __eq__(self, other)
     |  
     |  __init__(self, text: str, anchor: str = 'top_left', color: Tuple[int, int, int] = (255, 255, 255), bg_color: Union[Tuple[int, int, int], NoneType] = (0, 0, 0), bg_alpha: float = 0.4, font_scale: float = 0.45, thickness: int = 1, font: int = 0, margin_px: int = 8, priority: int = 0) -> None
     |  
     |  __repr__(self)
     |  
     |  ----------------------------------------------------------------------
     |  Data descriptors defined here:
     |  
     |  __dict__
     |      dictionary for instance variables (if defined)
     |  
     |  __weakref__
     |      list of weak references to the object (if defined)
     |  
     |  ----------------------------------------------------------------------
     |  Data and other attributes defined here:
     |  
     |  __annotations__ = {'anchor': <class 'str'>, 'bg_alpha': <class 'float'...
     |  
     |  __dataclass_fields__ = {'anchor': Field(name='anchor',type=<class 'str...
     |  
     |  __dataclass_params__ = _DataclassParams(init=True,repr=True,eq=True,or...
     |  
     |  __hash__ = None
     |  
     |  anchor = 'top_left'
     |  
     |  bg_alpha = 0.4
     |  
     |  bg_color = (0, 0, 0)
     |  
     |  color = (255, 255, 255)
     |  
     |  font = 0
     |  
     |  font_scale = 0.45
     |  
     |  margin_px = 8
     |  
     |  priority = 0
     |  
     |  thickness = 1
    
    class RaycastHit(builtins.object)
     |  RaycastHit(hit: 'str', world_point: 'Tuple[float, float, float]', distance_m: 'float', floor_state: 'Optional[str]' = None, meta: 'Dict[str, Any]' = <factory>) -> None
     |  
     |  Result of raycasting a pixel against a scene snapshot.
     |  
     |  Methods defined here:
     |  
     |  __eq__(self, other)
     |  
     |  __init__(self, hit: 'str', world_point: 'Tuple[float, float, float]', distance_m: 'float', floor_state: 'Optional[str]' = None, meta: 'Dict[str, Any]' = <factory>) -> None
     |  
     |  __repr__(self)
     |  
     |  ----------------------------------------------------------------------
     |  Data descriptors defined here:
     |  
     |  __dict__
     |      dictionary for instance variables (if defined)
     |  
     |  __weakref__
     |      list of weak references to the object (if defined)
     |  
     |  ----------------------------------------------------------------------
     |  Data and other attributes defined here:
     |  
     |  __annotations__ = {'distance_m': 'float', 'floor_state': 'Optional[str...
     |  
     |  __dataclass_fields__ = {'distance_m': Field(name='distance_m',type='fl...
     |  
     |  __dataclass_params__ = _DataclassParams(init=True,repr=True,eq=True,or...
     |  
     |  __hash__ = None
     |  
     |  floor_state = None
    
    class RenderResult(builtins.object)
     |  RenderResult(image: 'np.ndarray', source: 'str' = 'map3d', timestamp: 'float' = 0.0, resolution: 'Tuple[int, int]' = (0, 0), photo_id: 'Optional[str]' = None, path: 'Optional[str]' = None, pose: 'Optional[Dict[str, float]]' = None, meta: 'Optional[Dict[str, Any]]' = None) -> None
     |  
     |  CaptureResult-shaped return for mind-palace rendering.
     |  image is BGR uint8 for consistency with the rest of Logos vision tooling.
     |  
     |  Methods defined here:
     |  
     |  __eq__(self, other)
     |  
     |  __init__(self, image: 'np.ndarray', source: 'str' = 'map3d', timestamp: 'float' = 0.0, resolution: 'Tuple[int, int]' = (0, 0), photo_id: 'Optional[str]' = None, path: 'Optional[str]' = None, pose: 'Optional[Dict[str, float]]' = None, meta: 'Optional[Dict[str, Any]]' = None) -> None
     |  
     |  __repr__(self)
     |  
     |  save(self, view: 'bool' = False, path: 'Optional[str]' = None) -> 'str'
     |  
     |  view(self) -> 'None'
     |  
     |  ----------------------------------------------------------------------
     |  Data descriptors defined here:
     |  
     |  __dict__
     |      dictionary for instance variables (if defined)
     |  
     |  __weakref__
     |      list of weak references to the object (if defined)
     |  
     |  ----------------------------------------------------------------------
     |  Data and other attributes defined here:
     |  
     |  __annotations__ = {'image': 'np.ndarray', 'meta': 'Optional[Dict[str, ...
     |  
     |  __dataclass_fields__ = {'image': Field(name='image',type='np.ndarray',...
     |  
     |  __dataclass_params__ = _DataclassParams(init=True,repr=True,eq=True,or...
     |  
     |  __hash__ = None
     |  
     |  meta = None
     |  
     |  path = None
     |  
     |  photo_id = None
     |  
     |  pose = None
     |  
     |  resolution = (0, 0)
     |  
     |  source = 'map3d'
     |  
     |  timestamp = 0.0
    
    class SceneObject(builtins.object)
     |  SceneObject(name: 'str', kind: 'str', geometry: 'Any', render_visible: 'bool' = True, raycast_visible: 'bool' = True, costmap_affects: 'bool' = False, shader: 'str' = 'defaultLit', point_size: 'float' = 3.0) -> None
     |  
     |  An object that can be rendered and/or raycasted.
     |  
     |  Methods defined here:
     |  
     |  __eq__(self, other)
     |  
     |  __init__(self, name: 'str', kind: 'str', geometry: 'Any', render_visible: 'bool' = True, raycast_visible: 'bool' = True, costmap_affects: 'bool' = False, shader: 'str' = 'defaultLit', point_size: 'float' = 3.0) -> None
     |  
     |  __repr__(self)
     |  
     |  ----------------------------------------------------------------------
     |  Data descriptors defined here:
     |  
     |  __dict__
     |      dictionary for instance variables (if defined)
     |  
     |  __weakref__
     |      list of weak references to the object (if defined)
     |  
     |  ----------------------------------------------------------------------
     |  Data and other attributes defined here:
     |  
     |  __annotations__ = {'costmap_affects': 'bool', 'geometry': 'Any', 'kind...
     |  
     |  __dataclass_fields__ = {'costmap_affects': Field(name='costmap_affects...
     |  
     |  __dataclass_params__ = _DataclassParams(init=True,repr=True,eq=True,or...
     |  
     |  __hash__ = None
     |  
     |  costmap_affects = False
     |  
     |  point_size = 3.0
     |  
     |  raycast_visible = True
     |  
     |  render_visible = True
     |  
     |  shader = 'defaultLit'
    
    class SceneSnapshot(builtins.object)
     |  SceneSnapshot(render_id: 'str', timestamp: 'float', resolution: 'Tuple[int, int]', camera_world_pos: 'np.ndarray', look_at_world_pos: 'np.ndarray', view_matrix: 'np.ndarray', projection_matrix: 'np.ndarray', ray_infinity_distance_m: 'float' = 50.0, astra_points_map: 'Optional[np.ndarray]' = None, robot_mesh: 'Optional[MeshSnapshot]' = None, objects: 'List[ObjectSnapshot]' = <factory>, map_snapshot: 'Optional[MapSnapshot]' = None) -> None
     |  
     |  Self-contained snapshot of what was rendered, sufficient for later raycasts.
     |  
     |  Methods defined here:
     |  
     |  __eq__(self, other)
     |  
     |  __init__(self, render_id: 'str', timestamp: 'float', resolution: 'Tuple[int, int]', camera_world_pos: 'np.ndarray', look_at_world_pos: 'np.ndarray', view_matrix: 'np.ndarray', projection_matrix: 'np.ndarray', ray_infinity_distance_m: 'float' = 50.0, astra_points_map: 'Optional[np.ndarray]' = None, robot_mesh: 'Optional[MeshSnapshot]' = None, objects: 'List[ObjectSnapshot]' = <factory>, map_snapshot: 'Optional[MapSnapshot]' = None) -> None
     |  
     |  __repr__(self)
     |  
     |  ----------------------------------------------------------------------
     |  Data descriptors defined here:
     |  
     |  __dict__
     |      dictionary for instance variables (if defined)
     |  
     |  __weakref__
     |      list of weak references to the object (if defined)
     |  
     |  ----------------------------------------------------------------------
     |  Data and other attributes defined here:
     |  
     |  __annotations__ = {'astra_points_map': 'Optional[np.ndarray]', 'camera...
     |  
     |  __dataclass_fields__ = {'astra_points_map': Field(name='astra_points_m...
     |  
     |  __dataclass_params__ = _DataclassParams(init=True,repr=True,eq=True,or...
     |  
     |  __hash__ = None
     |  
     |  astra_points_map = None
     |  
     |  map_snapshot = None
     |  
     |  ray_infinity_distance_m = 50.0
     |  
     |  robot_mesh = None

FUNCTIONS
    describe_instance(name: 'str') -> 'Dict[str, Any]'
        Describe a phantasma instance. See Map3d.describe_instance() for details.
    
    describe_phantasma(object_name: 'str') -> 'Dict[str, Any]'
        Describe a phantasma module. See Map3d.describe_phantasma() for details.
    
    get_map3d() -> 'Map3d'
    
    list_instances() -> 'Dict[str, Dict[str, Any]]'
        List all phantasma instances. See Map3d.list_instances() for details.
    
    list_phantasmata() -> 'List[str]'
        List available phantasma modules. See Map3d.list_phantasmata() for details.
    
    move_instance(*args, **kwargs) -> 'None'
        Move a phantasma instance. See Map3d.move_instance() for details.
    
    place(*args, **kwargs) -> 'None'
        Place a phantasma instance. See Map3d.place() for details.
    
    raycast(*args, **kwargs) -> 'RaycastHit'
    
    rebuild(name: 'Optional[str]' = None) -> 'None'
        Force rebuild phantasmata. See Map3d.rebuild() for details.
    
    reload_mind_palace() -> 'None'
        Reload mind_palace.yaml. See Map3d.reload_mind_palace() for details.
    
    remove(*args, **kwargs) -> 'None'
        Remove a phantasma instance. See Map3d.remove() for details.
    
    render(*args, **kwargs) -> 'RenderResult'
    
    set_visible(*args, **kwargs) -> 'None'
        Set phantasma visibility. See Map3d.set_visible() for details.
    
    update_instance(*args, **kwargs) -> 'None'
        Update phantasma instance params. See Map3d.update_instance() for details.

DATA
    HUD_ANCHORS = ('top_left', 'top_center', 'top_right', 'bottom_left', '...
    HUD_FONT_DUPLEX = 2
    HUD_FONT_PLAIN = 1
    HUD_FONT_SIMPLEX = 0
    HUD_FONT_SMALL = 6
    __all__ = ['RenderResult', 'RaycastHit', 'SceneObject', 'SceneSnapshot...
    __annotations__ = {'_CHORA_SINGLETON': 'Optional[Map3d]'}

FILE
    /home/robot/robot_workspaces/Logos/src/logos/map3d.py