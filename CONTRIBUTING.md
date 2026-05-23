# Contributing

Logos is a personal embodied robot workspace, not a general-purpose robotics
framework. Contributions are welcome as conversation, issues, experiments, or
careful pull requests, but the bar for runtime changes is high because they may
affect a physical robot in a home.

Guidelines:

- Do not change runtime behavior casually.
- Keep runtime Python compatible with Python 3.8 and ROS Noetic.
- Guard ROS imports so modules remain inspectable offline.
- Preserve Logos-facing first-person style in files meant for Logos to read.
- Use degrees in public robot APIs.
- Do not add credentials, `.env` files, model weights, generated captures, or
  personal memory logs.
- Keep docs honest about the project's experimental state.

For substantial behavior changes, open an issue or discussion first so Mark can
decide whether the idea belongs in this robot's live workspace.
