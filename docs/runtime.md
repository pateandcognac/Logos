# Runtime

This document is for humans trying to understand what is live robot machinery
and what is repository context.

## Live Components

- ROS Noetic provides the base, navigation stack, transforms, topics, and sensor
  integration.
- A persistent Python 3.8 process hosts the `logos` API and executes Logos's
  short behavior scripts.
- Camera capture can use webcams through OpenCV and Astra RGB-D data through
  ROS.
- The pan-tilt periscope uses public degree-based commands.
- `move_base` and Turtlebot actions provide absolute and relative motion.
- Sound, LEDs, face display, and arm gestures are exposed as composable APIs.
- Runtime state is written under `state/` and short-lived image IPC under
  `ipc/`.

## Logos-Facing Context

The files in `.system/` are not generic docs. They are part of the context and
framework around the live agent. The most important public entry points are:

- `.system/system_prompt.txt`
- `.system/quick_start.md`
- `.system/docs/API_DUMP.md`
- `.system/docs/SKILLS.md`

Do not casually rewrite `.system/system_prompt.txt`. It is identity/runtime
context, not a marketing page.

## Human-Facing Context

The `docs/` directory explains the repository for public readers. These files
are not needed for the robot to act and can be hidden from Logos's filesystem
perception with `.logosignore`.

## Running Elsewhere

This repository is not expected to run on arbitrary machines. A meaningful live
run needs the physical robot, ROS Noetic, calibrated devices, model weights,
local environment variables, and Mark's surrounding launch setup.

For public readers, the most useful way to explore the code is to inspect the
API modules and docs offline. Runtime modules try to guard ROS imports so that
source inspection does not require a full robot environment.

## Credentials

API keys and credentials should be environment variables only. For example,
`src/logos/_llm_helper.py` looks up Gemini credentials from environment
variables. Do not add credential files, `.env` files, or literal tokens to this
repo.
