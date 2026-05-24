<me><py>
# EXAMPLE: Chora spatial planning with raycasts, a pointer arrow, and fallback.

# Reviewing my latest ephemera output, I see map3d_result is already a Chora
# render. Let's use that rather than guessing from a camera-only view.
caption = (
    "Chora view from my current pose: open floor through the office doorway, "
    "desk obstacle on the left, chair legs near the center-right, and a clear "
    "corridor patch beyond them."
)
trajectory = [
    {"label": "near_clear_floor", "point": [655, 472]},
    {"label": "doorway_midline", "point": [548, 510]},
    {"label": "far_corridor_goal", "point": [430, 560]},
]
obstacles = [
    {"label": "desk_edge", "box_2d": [365, 105, 880, 310]},
    {"label": "chair_legs", "box_2d": [420, 600, 760, 760]},
]
print({"caption": caption, "trajectory": trajectory, "obstacles": obstacles})

# Lemme think spatially: I want the furthest reachable point, but I also want a
# visible marker so Mark can see what I mean in Chora if this becomes weird.
# This skill probes the trajectory from the end backward and starts the accepted
# NavTask for me, so I should not call go_to_abs a second time.
nav_task = skills.nav.find_reachable_goal(map3d_result, trajectory)

if nav_task is not None:
    goal_hit = logos.map3d.raycast(map3d_result, trajectory[-1]["point"])
    print("[Chora raycast] far goal:", goal_hit)

    # Most raycast hit objects in my API expose world-ish coordinates; I'll keep
    # this intentionally defensive because few-shot examples should model care.
    if hasattr(goal_hit, "point") and goal_hit.point is not None:
        goal_xyz = list(goal_hit.point)
    elif isinstance(goal_hit, dict) and goal_hit.get("point"):
        goal_xyz = goal_hit["point"]
    else:
        goal_xyz = [0.0, 0.0, 0.0]

    logos.map3d.place(
        name="candidate_nav_goal_arrow",
        object="pointer_arrow",
        params={
            "from_robot": True,
            "from_offset_z": 0.75,
            "to_point": goal_xyz,
            "color": [0.1, 0.8, 1.0],
            "shaft_radius": 0.012,
        },
        description="Temporary arrow pointing at my chosen reachable floor goal.",
        save_to_yaml=False,
    )

    print("[nav] accepted and started:", nav_task)
    loop_cognition = True
else:
    # Wait! Hold on. My chosen corridor path is not clearly reachable. I should
    # ask for help rather than wedge myself into chair legs with confidence.
    logos.sound.chime("warning", wait=False)
    logos.emote.ttp(
        "I see a possible route, but Chora says the far point may not be reachable. "
        "Could you clear the chair legs or point me at a better path?",
        wait=False,
    )
    loop_cognition = False
</py></me>
