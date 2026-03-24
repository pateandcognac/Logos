# Logos/src/logos/nav.py

"""
Map-aware autonomous navigation.

This module provides tools for moving me intelligently through the world. 
It interfaces with the ROS `move_base` stack for absolute map navigation
and the `turtlebot_move` action server for odometry-based relative movements.
"""

import math
import time
from typing import Optional, List

from .core import api_call, Verbosity, check_for_interrupt
from . import ros

# Gated ROS imports
try:
    import rospy
    import actionlib
    import tf.transformations
    from move_base_msgs.msg import MoveBaseAction, MoveBaseGoal
    from turtlebot_actions.msg import TurtlebotMoveAction, TurtlebotMoveGoal
    from actionlib_msgs.msg import GoalStatus
    _HAS_ROS = True
except ImportError:
    _HAS_ROS = False

__all__ = ["go_to_abs", "move_relative", "turn_then_drive", "approach_coordinate", "approach_detection", "cancel_all", "NavTask"]


class NavTask:
    """
    A handle for an asynchronous navigation task.
    
    This allows me to start a movement, do other things (like look around or 
    speak), and periodically check on my progress or cancel the movement.
    """
    def __init__(self, client, goal_x: float, goal_y: float, start_x: float, start_y: float):
        self._client = client
        self._goal_x = goal_x
        self._goal_y = goal_y
        self._start_x = start_x
        self._start_y = start_y
        
        # Calculate the initial straight-line distance to the goal
        self._total_distance = math.hypot(goal_x - start_x, goal_y - start_y)

    def is_active(self) -> bool:
        """Returns True if the robot is currently trying to reach the goal."""
        if not _HAS_ROS: return False
        state = self._client.get_state()
        return state in [GoalStatus.PENDING, GoalStatus.ACTIVE]

    def succeeded(self) -> bool:
        """Returns True if the robot successfully reached the goal."""
        if not _HAS_ROS: return False
        return self._client.get_state() == GoalStatus.SUCCEEDED

    def status(self) -> str:
        """Returns a human-readable status of the goal (e.g., 'ACTIVE', 'SUCCEEDED', 'ABORTED')."""
        if not _HAS_ROS: return "NO_ROS"
        state = self._client.get_state()
        mapping = {
            GoalStatus.PENDING: "PENDING",
            GoalStatus.ACTIVE: "ACTIVE",
            GoalStatus.PREEMPTED: "CANCELED",
            GoalStatus.SUCCEEDED: "SUCCEEDED",
            GoalStatus.ABORTED: "FAILED/ABORTED",
            GoalStatus.REJECTED: "REJECTED",
            GoalStatus.LOST: "LOST"
        }
        return mapping.get(state, f"UNKNOWN({state})")

    def progress(self) -> float:
        """
        Uses Euclidean distance to estimate how far along the path I am. 0.0 is start pose. 1.0 is goal. Values can rise and fall as I navigate, even beyond 0 and 1.
        
        Note to self:
            This uses straight-line (Euclidean) distance. If I have to drive through
            rooms or around a large obstacles, this number can go down before it 
            goes up, and may even pass 1.0 before reaching goal. This is usable information!
        """
        if self._total_distance <= 0.01:
            return 1.0 # We started basically at the goal
            
        pose = ros.get_pose()
        if not pose:
            return 0.0 # Can't calculate without pose
            
        current_distance = math.hypot(self._goal_x - pose['x'], self._goal_y - pose['y'])
        
        # Calculate progress (clamped between 0.0 and 1.0 just in case)
        # Wait. Perhaps we should allow negative numbers?  This could enable behavior like:
        # if progress < -0.25 then speak("just a sec. gotta take a little detour first.")

        p = 1.0 - (current_distance / self._total_distance)
        return max(0.0, min(1.0, p))

    def cancel(self) -> None:
        """Stops the robot and cancels this specific goal."""
        if _HAS_ROS:
            self._client.cancel_goal()
            # Give it a tiny moment to process the cancel
            time.sleep(0.1)

    def wait(self, timeout: float = 120.0) -> bool:
        """
        Blocks execution until the goal is reached, fails, or times out.
        Includes cooperative interrupt checks.
        
        Returns:
            True if succeeded, False otherwise.
        """
        end_time = time.time() + timeout
        rate = rospy.Rate(10)
        
        while self.is_active() and time.time() < end_time:
            check_for_interrupt()
            rate.sleep()
            
        return self.succeeded()


@api_call(default_verbosity=Verbosity.BRIEF)
def go_to_abs(x: float, y: float, deg: Optional[float] = None, wait: bool = False) -> NavTask:
    """
    Navigate to an absolute (x, y) coordinate on the ROS map using move_base.

    Args:
        x: Map X coordinate in meters.
        y: Map Y coordinate in meters.
        deg: Final facing direction in degrees. If None, I will automatically 
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
                    logos.emote.ttp("Halfway there! 🏃", wait=False)
                    break # Break the loop, but the task keeps running in background!
            task.wait() # Now wait for the rest of the trip
    """
    if not _HAS_ROS:
        print("nav: ROS not available.")
        return NavTask(None, x, y, 0.0, 0.0)

    client = ros.get_action_client('move_base', MoveBaseAction)
    if not client:
        print("nav: move_base action server not available.")
        return NavTask(None, x, y, 0.0, 0.0)

    pose = ros.get_pose()
    start_x = pose['x'] if pose else 0.0
    start_y = pose['y'] if pose else 0.0

    # Auto-calculate orientation if none provided
    if deg is None:
        # math.atan2(dy, dx) gives the angle of the vector
        yaw_rad = math.atan2(y - start_y, x - start_x)
    else:
        yaw_rad = math.radians(deg)

    # Convert Euler yaw to Quaternion
    quat = tf.transformations.quaternion_from_euler(0, 0, yaw_rad)

    goal = MoveBaseGoal()
    goal.target_pose.header.frame_id = "map"
    goal.target_pose.header.stamp = rospy.Time.now()
    goal.target_pose.pose.position.x = x
    goal.target_pose.pose.position.y = y
    goal.target_pose.pose.orientation.x = quat[0]
    goal.target_pose.pose.orientation.y = quat[1]
    goal.target_pose.pose.orientation.z = quat[2]
    goal.target_pose.pose.orientation.w = quat[3]

    client.send_goal(goal)
    
    task = NavTask(client, x, y, start_x, start_y)
    
    if wait:
        task.wait()
        
    return task


@api_call(default_verbosity=Verbosity.BRIEF)
def move_relative(forward_m: float = 0.0, left_m: float = 0.0, turn_deg: float = 0.0, wait: bool = False) -> NavTask:
    """
    Move relative to my CURRENT position and orientation using the map navigation stack.

    This calculates a global map coordinate based on my current pose and uses
    `go_to_abs` to plan a safe, obstacle-avoiding path to get there.

    Args:
        forward_m: Meters to move forward (positive) or backward (negative).
        left_m: Meters to my left (positive) or right (negative).
        turn_deg: Degrees to turn relative to my current facing (positive is left).
        wait: If True, blocks until I arrive.

    Note to self:
        I am a differential drive robot — I can't strafe! If I command a movement
        purely to my `left_m`, `move_base` will try to find a global path to that
        coordinate. This often results in a ridiculous, circuitous dance where I
        drive forward, loop around, and oscillate just to move 1 foot to the left.

        Use this function when I need obstacle avoidance to reach a nearby relative 
        location. If I just need to inch closer to a table or perform a simple geometric 
        maneuver in open space, I should absolutely use `logos.nav.turn_then_drive()` instead.

    Example:
        # Safely navigate to a spot 1m ahead and end up facing 90 degrees left
        logos.nav.move_relative(forward_m=1.0, turn_deg=90.0)
    """
    pose = ros.get_pose()
    if not pose:
        print("nav: Cannot move relative, current pose unknown.")
        # Returning a dummy/failed NavTask (adjust signature to match your actual NavTask init)
        return NavTask(None, 0, 0, 0, 0)

    # Current state
    x, y, deg = pose['x'], pose['y'], pose['theta']
    theta_rad = math.radians(deg)
    
    # Calculate global map offsets based on my local orientation
    dx = (forward_m * math.cos(theta_rad)) - (left_m * math.sin(theta_rad))
    dy = (forward_m * math.sin(theta_rad)) + (left_m * math.cos(theta_rad))
    
    target_x = x + dx
    target_y = y + dy
    target_theta = deg + turn_deg
    
    return go_to_abs(target_x, target_y, deg=target_theta, wait=wait)


@api_call(default_verbosity=Verbosity.BRIEF)
def turn_then_drive(turn_deg: float, forward_m: float, wait: bool = True) -> NavTask:
    """
    Smoothed movement using odometry (rotate first, then drive forward/backward).

    Args:
        turn_deg: Degrees to turn *before* driving. Positive is left, negative is right.
        forward_m: Meters to drive straight. Can be negative to back up.
        wait: If True, blocks until the movement is finished.

    Returns:
        A NavTask object.

    Note to self:
        This does NOT use the map or obstacle avoidance! It is a "blind" 
        precision movement based on wheel encoders. Useful for inching closer 
        to an object, backing out of a tight spot, or turning to face a human.
        
        It executes sequentially: It turns `turn_deg`, stops, then drives `forward_m`.
    """
    if not _HAS_ROS:
        print("nav: ROS not available.")
        return NavTask(None, 0, 0, 0, 0)

    client = ros.get_action_client('turtlebot_move', TurtlebotMoveAction)
    if not client:
        print("nav: turtlebot_move action server not available.")
        return NavTask(None, 0, 0, 0, 0)

    # Calculate approximate global target for progress tracking
    pose = ros.get_pose()
    start_x = pose['x'] if pose else 0.0
    start_y = pose['y'] if pose else 0.0
    start_theta = pose['theta'] if pose else 0.0
    
    # Target global pose after turning and moving forward
    target_theta_rad = start_theta + math.radians(turn_deg)
    goal_x = start_x + (forward_m * math.cos(target_theta_rad))
    goal_y = start_y + (forward_m * math.sin(target_theta_rad))

    goal = TurtlebotMoveGoal()
    goal.turn_distance = math.radians(turn_deg)
    goal.forward_distance = forward_m

    client.send_goal(goal)
    
    task = NavTask(client, goal_x, goal_y, start_x, start_y)
    
    if wait:
        task.wait()
        
    return task


@api_call(default_verbosity=Verbosity.ACK)
def cancel_all() -> None:
    """
    Panic button. Immediately halts all map-based and relative navigation tasks.
    """
    if not _HAS_ROS: return
    
    mb_client = ros.get_action_client('move_base', MoveBaseAction, wait_time=0.1)
    if mb_client: mb_client.cancel_all_goals()
        
    tb_client = ros.get_action_client('turtlebot_move', TurtlebotMoveAction, wait_time=0.1)
    if tb_client: tb_client.cancel_all_goals()


@api_call(default_verbosity=Verbosity.ACK)
def approach_detection(box_3d: List[float], standoff: float = 1.0, source_frame: str = 'camera_depth_optical_frame', wait: bool = True) -> NavTask:
    """
    Navigate to a spot `standoff` meters away from the nearest face of a box_3d I detected from my Astra.
    
    This bridges the gap between my native visual 3D detections (in camera optical frame) 
    and the physical map. It calculates the object's radius on the floor plane to ensure 
    I stop at the appropriate distance from the surface, not the center.

    Args:
        box_3d: The 9-value 3D bounding box list I emit natively:
                [cx, cy, cz, sx, sy, sz, r, p, y]
                (Center X, Y, Z; Size X, Y, Z; Roll, Pitch, Yaw).
                Convention: Camera Optical Frame (X-Right, Y-Down, Z-Forward).
        standoff: How many meters from the *surface* of the object to stop.
        source_frame: The TF frame the detection was made in. Defaults to Astra depth.
        wait: If True, blocks until arrival.

    Returns:
        A NavTask object.

    Note to self:
        I use this when I want to inspect something I've seen. 
        Since my native `box_3d` is in the camera frame, this function handles the 
        messy TF transforms to get it onto the map.
        
        Crucially, it adjusts the goal so I don't ram into large objects! 
        If I see a couch that is 1 meter deep, and request a 1.0m standoff, 
        this function calculates the geometry and stops me 1.5m from the center 
        (1.0m standoff + 0.5m object radius).
        
        Example:
            # "I see a chair over there, let me get a closer look."
            # [My native detection triggers] -> box = [...]
            logos.nav.approach_detection(box, standoff=0.8)
    """
    # 1. Unpack the box (We only need center and size for this)
    # Optical Frame: X=Right, Y=Down, Z=Forward
    cx, cy, cz, sx, sy, sz, *_ = box_3d

    # 2. Transform Center to Map Frame
    # We use the current time (0.0) as we are acting on a live perception.
    map_coords = logos.ros.transform_point_to_map(cx, cy, cz, source_frame, 0.0)
    
    if not map_coords:
        print(f"Error: Could not transform detection from {source_frame} to map.")
        return logos.nav.NavTask(status="ABORTED")

    mx, my, mz = map_coords

    # 3. Calculate "Floor Radius"
    # In Optical Frame, the object's footprint on the floor is defined by X (width) and Z (depth).
    # We want to stop `standoff` away from the face. 
    # Conservative approach: treat the object depth as the max of its optical X/Z dimensions 
    # halved. This prevents clipping corners of rotated objects.
    object_radius = max(sx, sz) / 2.0
    
    # 4. Total Standoff = Requested Standoff + Distance from Center to Face
    effective_standoff = standoff + object_radius

    # 5. Execute Approach
    # approach_coordinate automatically faces the target (mx, my) upon arrival.
    return logos.nav.approach_coordinate(mx, my, standoff=effective_standoff, wait=wait)