## 7. Map3d HUD System Extraction
### 7.1 Move to logos/vision.py

The HUD rendering mechanism currently in map3d (`_overlay_hud`, `HudElement`,
anchor constants, font constants) should be extracted to `logos/vision.py` as a
general-purpose overlay system. This makes it available for:

- Map3d renders (virtual camera)
- Physical Astra camera captures
- Pan-tilt webcam captures
- Any future image source

### 7.2 What moves

```python
# logos/vision.py (additions)

HUD_ANCHORS = (
    "top_left", "top_center", "top_right",
    "bottom_left", "bottom_center", "bottom_right",
)

HUD_FONT_SIMPLEX = 0
HUD_FONT_PLAIN = 1
HUD_FONT_DUPLEX = 2
HUD_FONT_SMALL = 6

@dataclass
class HudElement:
    """A single text/sprite element to overlay on an image."""
    text: str
    anchor: str = "top_left"
    color: Tuple[int, int, int] = (255, 255, 255)  # BGR
    bg_color: Optional[Tuple[int, int, int]] = (0, 0, 0)
    bg_alpha: float = 0.4
    font_scale: float = 0.45
    thickness: int = 1
    font: int = 0
    margin_px: int = 8
    priority: int = 0

def overlay_hud(image: np.ndarray, elements: List[HudElement]) -> np.ndarray:
    """Render HUD elements onto an image (mutates in-place, also returns)."""
    ...
```

### 7.3 What `build()` and `hud()` return

`build()` returns `SceneObject`, `List[SceneObject]`, or `None`.
`hud()` returns `List[HudElement]` or `None`.

They are separate functions. Map3d calls `build()` to get geometry for the 3D
scene, and calls `hud()` to get 2D overlays that are composited after rendering.
This clean separation means:

- A phantasma can be geometry-only (no `hud()` defined)
- A phantasma can be HUD-only (no `build()` or `build()` returns None)
- A phantasma can contribute both
