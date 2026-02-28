## 12. TODOs & Future Work

Collected from the design conversation. Not blocking the implementation above.

### Near-term

- [ ] **Waypoints phantasma** with emoji rendering (OpenMoji PNGs), billboard/
  theta/floor modes, floor arrows. Reads `waypoints.yaml`.
- [ ] **`pose.frame` TF override** on instances — allows objects to follow
  arbitrary TF frames. Consider implementing only when actually needed.
- [ ] **World-space labels** — project 3D coords through view/projection to
  pixel coords, render text at scene objects. Occlusion: skip objects behind
  camera (check w sign after projection), sort by distance. Can be implemented
  as a phantasma `hud()` that reads scene object positions.
- [ ] **Costmap injection pipeline** — when `costmap_affects: true`, flatten
  object footprint to Z=0 and publish to costmap. Needs integration with
  nav stack.
- [ ] **Scene rebuild optimization** — profile and consider incremental
  scene updates if clear+re-add becomes a bottleneck with many phantasmata.

### Medium-term

- [ ] **RGBD camera overlay minimap** — since we're spending tokens on a
  640×480 depth image anyway, overlay a not-so-mini bird's-eye 3D view on
  the physical camera image. Toggle-able, scalable. Implementation: second
  OffscreenRenderer at small resolution with orthographic projection, composited
  via cv2 onto the camera image.
- [ ] **Skybox phantasma** — could be a cubemap or just a large sphere with
  interior texture. Needs to not interfere with raycasting.
- [ ] **Image/texture mapping on phantasmata** — beyond solid colors, allow
  phantasma `build()` to apply textures. Already possible via `albedo_img` on
  materials, just needs nice patterns/helpers.
- [ ] **Costmap inflation gradient visualization** — read inflated costmap,
  map values to color gradient, apply as floor texture or overlay.
- [ ] **Icon/sprite HUD overlays** — small PNG overlays at anchor positions.
  Extend `HudElement` to support image content, not just text.

### Long-term / Exploratory

- [ ] **`logos.state` as ROS callback target** — instead of `get_pose()`,
  have `logos.state.pose` updated by a callback. Pro: always fresh, no
  blocking call. Con: adds callback overhead, thread-safety concerns for
  large high-frequency data (point clouds). **Recommendation:** good for
  low-frequency scalar state (pose, battery, joint positions). Bad for
  high-bandwidth data (images, point clouds). Implement selectively.
- [ ] **Claude Code as summarization agent** ("Logos's Gnosis") — use Claude
  to summarize the io_buffer with narrative prose, few-shot prompting Gemini
  with Claude-ness.
- [ ] **Claude as Logos pilot** — investigate Claude Code integration for
  direct robot control.
- [ ] **Phantasmata as texture-mapped likenesses** — AI photographs real
  objects, creates mesh approximations, maps captured textures onto them.
  The full Platonic loop.
