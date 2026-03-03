#!/usr/bin/env python3
"""
Interactive text-overlay tool (Tkinter + OpenCV).
Designed to overlay text on an image for a VLLM consumption.
In testing, 2000 text tokens worth of code are able to fit into 500 image tokens,
while still allowing the model to process a photograph. Continuous image vector
space is a better compressor that text tokens!

Features:
- Live sliders with numeric values (font scale, thickness, spacing, margins, alpha, darken).
- Preview zoom with scrollbars (handles huge images).
- Output rescale (affects the saved image, not just preview).
- Start-line control to "scroll" through long text files.
- Interactive crop: toggle Crop Mode, drag a rectangle, Apply/Reset.
- Optional Python-aware wrapping: tries to wrap at token boundaries and avoids splitting
  inside string literals when tokenization succeeds.

Usage:
    python overlay_gui.py <image_path> <text_file_path>

Notes:
- Text rendering uses OpenCV's built-in Hershey fonts for portability.
- Saved output is the rendered overlay at "Output scale" (not preview zoom).
"""

import io
import os
import sys
import tokenize
from dataclasses import dataclass
from typing import List, Optional, Tuple

import cv2
import numpy as np
from PIL import Image, ImageTk
import tkinter as tk
from tkinter import filedialog, colorchooser, ttk


@dataclass
class OverlayParams:
    font: int = cv2.FONT_HERSHEY_PLAIN
    font_scale: float = 0.6
    thickness: int = 1
    line_spacing: float = 1.0
    margin_px: int = 4
    text_color_bgr: Tuple[int, int, int] = (0, 255, 0)
    text_alpha: float = 1.0
    darken_bg: float = 0.8
    wrap_enabled: bool = False


def bgr_to_hex(bgr: Tuple[int, int, int]) -> str:
    b, g, r = bgr
    return f"#{r:02x}{g:02x}{b:02x}"


def hex_to_bgr(hex_color: str) -> Tuple[int, int, int]:
    hex_color = hex_color.lstrip("#")
    r = int(hex_color[0:2], 16)
    g = int(hex_color[2:4], 16)
    b = int(hex_color[4:6], 16)
    return (b, g, r)


def measure_text_width_px(text: str, font: int, scale: float, thickness: int) -> int:
    (size, _baseline) = cv2.getTextSize(text, font, scale, thickness)
    return int(size[0])


def get_line_metrics(font: int, scale: float, thickness: int, line_spacing: float) -> Tuple[int, int]:
    """
    Returns (line_height_px, step_px) where:
    - line_height is the font height for baseline placement
    - step is vertical advance per line (includes spacing multiplier)
    """
    (_w, line_h), _ = cv2.getTextSize("Tg", font, scale, thickness)
    step = max(1, int(line_h * max(0.5, line_spacing)))
    return int(line_h), int(step)


def python_token_breakpoints(content: str) -> List[int]:
    """
    Returns candidate breakpoints (indices into content) based on Python token boundaries.
    We deliberately exclude breakpoints inside STRING tokens.
    """
    breakpoints: List[int] = []

    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(content).readline))
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return breakpoints

    for tok in tokens:
        tok_type = tok.type
        if tok_type in (tokenize.STRING, tokenize.ENCODING):
            continue
        # End column for this token on line 1
        _row, end_col = tok.end
        if 0 < end_col <= len(content):
            breakpoints.append(end_col)

    # Dedupe + sort
    return sorted(set(breakpoints))


def fallback_breakpoints(content: str) -> List[int]:
    """
    Fallback breakpoints: whitespace positions plus a few "nice" operator locations.
    """
    breakpoints = []
    for i, ch in enumerate(content, start=1):
        if ch.isspace():
            breakpoints.append(i)
        elif ch in (",", ")", "]", "}", "+", "-", "*", "/", "=", ":", ";"):
            breakpoints.append(i)
    return sorted(set(breakpoints))


def wrap_code_line(
    line: str,
    max_width_px: int,
    params: OverlayParams,
    continuation_indent: str = "  ",
) -> List[str]:
    """
    Wrap a single line to fit max_width_px using pixel measurements.
    Attempts to use Python token boundaries for nicer wraps.
    """
    if not line:
        return [""]

    # Preserve leading whitespace (code indentation)
    prefix_len = len(line) - len(line.lstrip(" \t"))
    base_prefix = line[:prefix_len]
    content = line[prefix_len:]

    # If it already fits, return as-is
    if measure_text_width_px(line, params.font, params.font_scale, params.thickness) <= max_width_px:
        return [line]

    token_bps = python_token_breakpoints(content)
    if not token_bps:
        token_bps = fallback_breakpoints(content)

    wrapped: List[str] = []
    prefix = base_prefix
    remaining = content

    while remaining:
        # Binary search for the max number of chars that fit.
        lo, hi = 1, len(remaining)
        best = 1
        while lo <= hi:
            mid = (lo + hi) // 2
            candidate = prefix + remaining[:mid]
            if measure_text_width_px(candidate, params.font, params.font_scale, params.thickness) <= max_width_px:
                best = mid
                lo = mid + 1
            else:
                hi = mid - 1

        # Choose a breakpoint <= best, prefer the last one before best.
        # token_bps were computed on the original content; we need them for the current remaining slice.
        # So we compute breakpoints for current remaining too.
        slice_bps = python_token_breakpoints(remaining) or fallback_breakpoints(remaining)
        split = max([bp for bp in slice_bps if bp <= best], default=best)

        # Avoid infinite loops on pathological lines
        split = max(1, min(split, len(remaining)))

        chunk = remaining[:split].rstrip()
        wrapped.append(prefix + chunk)

        remaining = remaining[split:].lstrip()
        prefix = base_prefix + continuation_indent

        # If prefix alone is already wider than max (tiny images / huge scale), bail hard
        if measure_text_width_px(prefix, params.font, params.font_scale, params.thickness) >= max_width_px:
            # Just hard-chop the rest into single chunks
            if remaining:
                wrapped.append(prefix + remaining)
            break

    return wrapped


def build_display_lines(
    all_lines: List[str],
    start_line: int,
    max_rows: int,
    max_width_px: int,
    params: OverlayParams,
) -> Tuple[List[str], int, int]:
    """
    Builds the list of lines to display given max_rows in the image.
    Returns (display_lines, start_line, end_line_exclusive_in_original).
    """
    display: List[str] = []
    idx = max(0, min(start_line, max(0, len(all_lines) - 1)))

    while idx < len(all_lines) and len(display) < max_rows:
        raw = all_lines[idx]
        if params.wrap_enabled:
            wrapped = wrap_code_line(raw, max_width_px, params)
        else:
            wrapped = [raw]

        for wline in wrapped:
            if len(display) >= max_rows:
                break
            display.append(wline)

        idx += 1

    return display, start_line, idx


def overlay_text(img_bgr: np.ndarray, all_lines: List[str], start_line: int, params: OverlayParams) -> Tuple[np.ndarray, dict]:
    """
    Returns (result_bgr, info_dict).
    """
    h, w = img_bgr.shape[:2]

    line_h, step = get_line_metrics(params.font, params.font_scale, params.thickness, params.line_spacing)
    usable_h = max(1, h - 2 * params.margin_px)
    max_rows = max(1, usable_h // max(1, step))
    usable_w = max(1, w - 2 * params.margin_px)

    display_lines, used_start, used_end = build_display_lines(
        all_lines=all_lines,
        start_line=start_line,
        max_rows=max_rows,
        max_width_px=usable_w,
        params=params,
    )

    # Darken base so text pops
    darken = float(np.clip(params.darken_bg, 0.0, 1.0))
    base = (img_bgr.astype(np.float32) * darken).astype(np.uint8)

    # Draw onto a separate layer for clean alpha blending
    text_layer = np.zeros_like(base)
    y = params.margin_px + line_h
    for line in display_lines:
        cv2.putText(
            text_layer,
            line,
            (params.margin_px, y),
            params.font,
            float(params.font_scale),
            params.text_color_bgr,
            int(params.thickness),
            cv2.LINE_AA,
        )
        y += step

    # Alpha composite only where text exists
    text_alpha = float(np.clip(params.text_alpha, 0.0, 1.0))
    mask = (text_layer.sum(axis=2) > 0).astype(np.float32)[:, :, None]
    alpha_mask = mask * text_alpha

    result = base.astype(np.float32) * (1.0 - alpha_mask) + text_layer.astype(np.float32) * alpha_mask
    result = np.clip(result, 0, 255).astype(np.uint8)

    info = {
        "h": h,
        "w": w,
        "line_h": line_h,
        "step": step,
        "max_rows": max_rows,
        "start_line": used_start,
        "end_line": used_end,
        "shown_rows": len(display_lines),
        "total_lines": len(all_lines),
    }
    return result, info


class OverlayGUI:
    def __init__(self, root: tk.Tk, image_path: Optional[str] = None, text_path: Optional[str] = None):
        self.root = root
        self.root.title("Overlay Text (interactive)")

        self.params = OverlayParams()

        self.original_img: Optional[np.ndarray] = None
        self.working_img: Optional[np.ndarray] = None
        self.last_result: Optional[np.ndarray] = None

        self.image_path: Optional[str] = None
        self.text_path: Optional[str] = None
        self.all_lines: List[str] = []

        self.output_scale = tk.DoubleVar(value=1.0)   # affects saved output
        self.preview_zoom = tk.DoubleVar(value=1.0)   # affects only preview display
        self.start_line = tk.IntVar(value=0)
        self.crop_mode = tk.BooleanVar(value=False)
        self.wrap_enabled = tk.BooleanVar(value=False)

        self._pending_update_job = None

        # Crop selection state
        self._crop_rect_id = None
        self._crop_start_xy = None
        self._crop_box_working = None  # (x0, y0, x1, y1) in working image coords

        self._build_ui()
        self._bind_events()

        if image_path:
            self.load_image(image_path)
        if text_path:
            self.load_text(text_path)

        # If both loaded, render
        self.request_update()

    def _build_ui(self) -> None:
        self.root.geometry("1200x800")

        main = ttk.Frame(self.root)
        main.pack(fill=tk.BOTH, expand=True)

        controls = ttk.Frame(main, padding=8)
        controls.pack(side=tk.LEFT, fill=tk.Y)

        preview = ttk.Frame(main, padding=8)
        preview.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        # Buttons row
        btn_row = ttk.Frame(controls)
        btn_row.pack(fill=tk.X)

        ttk.Button(btn_row, text="Open Image…", command=self.open_image_dialog).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_row, text="Open Text…", command=self.open_text_dialog).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_row, text="Reload Text", command=self.reload_text).pack(side=tk.LEFT, padx=2)

        # Save row
        save_row = ttk.Frame(controls)
        save_row.pack(fill=tk.X, pady=(6, 0))
        ttk.Button(save_row, text="Save As…", command=self.save_as_dialog).pack(side=tk.LEFT, padx=2)

        # Status label
        self.status = tk.StringVar(value="Load an image + text file to begin.")
        ttk.Label(controls, textvariable=self.status, wraplength=340).pack(fill=tk.X, pady=(8, 10))

        # Color picker
        color_row = ttk.Frame(controls)
        color_row.pack(fill=tk.X, pady=(0, 8))
        ttk.Button(color_row, text="Pick Text Color…", command=self.pick_color).pack(side=tk.LEFT)
        self.color_swatch = tk.Label(
            color_row,
            text="   ",
            bg=bgr_to_hex(self.params.text_color_bgr),
            relief=tk.SUNKEN,
            width=4,
        )
        self.color_swatch.pack(side=tk.LEFT, padx=8)

        # Toggles
        toggles = ttk.Frame(controls)
        toggles.pack(fill=tk.X, pady=(0, 8))
        ttk.Checkbutton(toggles, text="Wrap (Python-aware-ish)", variable=self.wrap_enabled, command=self.request_update).pack(anchor="w")
        ttk.Checkbutton(toggles, text="Crop Mode (drag rectangle)", variable=self.crop_mode).pack(anchor="w")

        crop_btns = ttk.Frame(controls)
        crop_btns.pack(fill=tk.X, pady=(0, 10))
        ttk.Button(crop_btns, text="Apply Crop", command=self.apply_crop).pack(side=tk.LEFT, padx=2)
        ttk.Button(crop_btns, text="Reset Crop", command=self.reset_crop).pack(side=tk.LEFT, padx=2)

        # Sliders
        sliders = ttk.LabelFrame(controls, text="Overlay Settings", padding=8)
        sliders.pack(fill=tk.X, pady=(0, 10))

        self._add_scale(sliders, "Font scale", 0.2, 3.0, 0.01, self.params.font_scale, self._set_font_scale)
        self._add_scale(sliders, "Thickness", 1, 6, 1, self.params.thickness, self._set_thickness, is_int=True)
        self._add_scale(sliders, "Line spacing", 0.7, 2.0, 0.01, self.params.line_spacing, self._set_line_spacing)
        self._add_scale(sliders, "Margin (px)", 0, 40, 1, self.params.margin_px, self._set_margin, is_int=True)
        self._add_scale(sliders, "Text alpha", 0.0, 1.0, 0.01, self.params.text_alpha, self._set_text_alpha)
        self._add_scale(sliders, "Darken bg", 0.0, 1.0, 0.01, self.params.darken_bg, self._set_darken_bg)

        view = ttk.LabelFrame(controls, text="View / Output", padding=8)
        view.pack(fill=tk.X)

        self._add_var_scale(view, "Start line", self.start_line, 0, 100000, 1, self.request_update, is_int=True)
        self._add_var_scale(view, "Output scale", self.output_scale, 0.25, 3.0, 0.01, self.request_update)
        self._add_var_scale(view, "Preview zoom", self.preview_zoom, 0.1, 4.0, 0.01, self._update_canvas_image)

        # Preview canvas with scrollbars
        self.canvas = tk.Canvas(preview, bg="#111111", highlightthickness=0)
        self.hbar = ttk.Scrollbar(preview, orient=tk.HORIZONTAL, command=self.canvas.xview)
        self.vbar = ttk.Scrollbar(preview, orient=tk.VERTICAL, command=self.canvas.yview)
        self.canvas.configure(xscrollcommand=self.hbar.set, yscrollcommand=self.vbar.set)

        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.vbar.grid(row=0, column=1, sticky="ns")
        self.hbar.grid(row=1, column=0, sticky="ew")

        preview.grid_rowconfigure(0, weight=1)
        preview.grid_columnconfigure(0, weight=1)

        self._tk_img = None
        self._canvas_img_id = self.canvas.create_image(0, 0, anchor="nw")

    def _add_scale(
        self,
        parent: ttk.Frame,
        label: str,
        frm: float,
        to: float,
        resolution: float,
        initial,
        setter,
        is_int: bool = False,
    ) -> None:
        row = ttk.Frame(parent)
        row.pack(fill=tk.X, pady=2)

        ttk.Label(row, text=label, width=14).pack(side=tk.LEFT)

        var = tk.DoubleVar(value=float(initial)) if not is_int else tk.IntVar(value=int(initial))

        def on_change(_evt=None):
            value = var.get()
            setter(int(value) if is_int else float(value))
            self.request_update()

        scale = tk.Scale(
            row,
            from_=frm,
            to=to,
            orient=tk.HORIZONTAL,
            resolution=resolution,
            variable=var,
            showvalue=True,
            command=lambda _v: on_change(),
            length=180,
        )
        scale.pack(side=tk.LEFT, fill=tk.X, expand=True)

    def _add_var_scale(
        self,
        parent: ttk.Frame,
        label: str,
        variable,
        frm: float,
        to: float,
        resolution: float,
        on_change,
        is_int: bool = False,
    ) -> None:
        row = ttk.Frame(parent)
        row.pack(fill=tk.X, pady=2)

        ttk.Label(row, text=label, width=14).pack(side=tk.LEFT)

        scale = tk.Scale(
            row,
            from_=frm,
            to=to,
            orient=tk.HORIZONTAL,
            resolution=resolution,
            variable=variable,
            showvalue=True,
            command=lambda _v: on_change(),
            length=180,
        )
        scale.pack(side=tk.LEFT, fill=tk.X, expand=True)

    def _bind_events(self) -> None:
        self.canvas.bind("<ButtonPress-1>", self._on_mouse_down)
        self.canvas.bind("<B1-Motion>", self._on_mouse_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_mouse_up)

        # Mouse wheel zoom (platform quirks handled)
        self.canvas.bind("<MouseWheel>", self._on_mousewheel)      # Windows/macOS
        self.canvas.bind("<Button-4>", self._on_mousewheel_linux)  # Linux scroll up
        self.canvas.bind("<Button-5>", self._on_mousewheel_linux)  # Linux scroll down

    def _set_font_scale(self, v: float) -> None:
        self.params.font_scale = float(v)

    def _set_thickness(self, v: int) -> None:
        self.params.thickness = int(v)

    def _set_line_spacing(self, v: float) -> None:
        self.params.line_spacing = float(v)

    def _set_margin(self, v: int) -> None:
        self.params.margin_px = int(v)

    def _set_text_alpha(self, v: float) -> None:
        self.params.text_alpha = float(v)

    def _set_darken_bg(self, v: float) -> None:
        self.params.darken_bg = float(v)

    def pick_color(self) -> None:
        rgb, hex_color = colorchooser.askcolor(title="Pick text color", initialcolor=bgr_to_hex(self.params.text_color_bgr))
        if not hex_color:
            return
        self.params.text_color_bgr = hex_to_bgr(hex_color)
        self.color_swatch.configure(bg=hex_color)
        self.request_update()

    def open_image_dialog(self) -> None:
        path = filedialog.askopenfilename(
            title="Open image",
            filetypes=[("Images", "*.png *.jpg *.jpeg *.bmp *.tif *.tiff *.webp"), ("All files", "*.*")],
        )
        if path:
            self.load_image(path)

    def open_text_dialog(self) -> None:
        path = filedialog.askopenfilename(
            title="Open text/code file",
            filetypes=[("Text / Code", "*.txt *.py *.cpp *.hpp *.h *.c *.md *.yaml *.yml *.json *.xml *.launch"), ("All files", "*.*")],
        )
        if path:
            self.load_text(path)

    def load_image(self, path: str) -> None:
        img = cv2.imread(path, cv2.IMREAD_COLOR)
        if img is None:
            self.status.set(f"Could not read image: {path}")
            return

        self.image_path = path
        self.original_img = img
        self.working_img = img.copy()
        self._crop_box_working = None
        self._clear_crop_rect()

        self.status.set(f"Loaded image: {os.path.basename(path)} ({img.shape[1]}x{img.shape[0]})")
        self.request_update()

    def load_text(self, path: str) -> None:
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                lines = [ln.rstrip("\n").rstrip("\r") for ln in f.readlines()]
        except OSError as exc:
            self.status.set(f"Could not read text: {path}\n{exc}")
            return

        self.text_path = path
        self.all_lines = lines
        self.start_line.set(0)

        self.status.set(f"Loaded text: {os.path.basename(path)} ({len(lines)} lines)")
        self.request_update()

    def reload_text(self) -> None:
        if not self.text_path:
            return
        self.load_text(self.text_path)

    def save_as_dialog(self) -> None:
        if self.last_result is None:
            self.status.set("Nothing to save yet (load image + text first).")
            return

        default_name = "overlay.png"
        if self.image_path:
            stem = os.path.splitext(os.path.basename(self.image_path))[0]
            default_name = f"{stem}_overlay.png"

        path = filedialog.asksaveasfilename(
            title="Save overlay image",
            defaultextension=".png",
            initialfile=default_name,
            filetypes=[("PNG", "*.png"), ("JPEG", "*.jpg *.jpeg"), ("BMP", "*.bmp"), ("TIFF", "*.tif *.tiff"), ("All files", "*.*")],
        )
        if not path:
            return

        ok = cv2.imwrite(path, self.last_result)
        if ok:
            self.status.set(f"Saved: {path}")
        else:
            self.status.set(f"Save failed: {path}")

    def request_update(self) -> None:
        # Debounce rapid slider changes
        if self._pending_update_job is not None:
            self.root.after_cancel(self._pending_update_job)
        self._pending_update_job = self.root.after(40, self._update_render)

    def _update_render(self) -> None:
        self._pending_update_job = None

        if self.working_img is None or not self.all_lines:
            self._update_canvas_blank()
            return

        self.params.wrap_enabled = bool(self.wrap_enabled.get())

        # Apply output scaling before overlay (this changes final saved pixels)
        out_scale = float(self.output_scale.get())
        out_scale = float(np.clip(out_scale, 0.05, 10.0))

        base = self.working_img
        if abs(out_scale - 1.0) > 1e-6:
            new_w = max(1, int(base.shape[1] * out_scale))
            new_h = max(1, int(base.shape[0] * out_scale))
            base = cv2.resize(base, (new_w, new_h), interpolation=cv2.INTER_AREA)

        start = int(self.start_line.get())
        start = max(0, min(start, max(0, len(self.all_lines) - 1)))
        self.start_line.set(start)

        result, info = overlay_text(base, self.all_lines, start, self.params)
        self.last_result = result

        # Update status line with something actually useful
        shown = info["shown_rows"]
        total = info["total_lines"]
        end_line = info["end_line"]
        crop_txt = ""
        if self.working_img is not None and self.original_img is not None:
            if self.working_img.shape[:2] != self.original_img.shape[:2]:
                crop_txt = f" | Cropped to {self.working_img.shape[1]}x{self.working_img.shape[0]}"

        self.status.set(
            f"Output: {info['w']}x{info['h']} @ scale {out_scale:.2f} | "
            f"Rows shown: {shown}/{info['max_rows']} | "
            f"Source lines: {start}..{end_line-1} of {total-1}{crop_txt}"
        )

        self._update_canvas_image()

    def _update_canvas_blank(self) -> None:
        self.canvas.itemconfigure(self._canvas_img_id, image="")
        self.canvas.configure(scrollregion=(0, 0, 1, 1))

    def _update_canvas_image(self) -> None:
        if self.last_result is None:
            self._update_canvas_blank()
            return

        zoom = float(self.preview_zoom.get())
        zoom = float(np.clip(zoom, 0.05, 20.0))
        self.preview_zoom.set(zoom)

        img = self.last_result
        if abs(zoom - 1.0) > 1e-6:
            new_w = max(1, int(img.shape[1] * zoom))
            new_h = max(1, int(img.shape[0] * zoom))
            disp = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_NEAREST)
        else:
            disp = img

        rgb = cv2.cvtColor(disp, cv2.COLOR_BGR2RGB)
        pil = Image.fromarray(rgb)
        self._tk_img = ImageTk.PhotoImage(pil)

        self.canvas.itemconfigure(self._canvas_img_id, image=self._tk_img)
        self.canvas.coords(self._canvas_img_id, 0, 0)
        self.canvas.configure(scrollregion=(0, 0, pil.width, pil.height))

        # Keep crop rectangle (display-space) consistent if it exists
        self._refresh_crop_rect_display()

    def _on_mousewheel(self, event) -> None:
        # Zoom with Ctrl+wheel, else vertical scroll
        if event.state & 0x0004:  # Control key
            delta = 1 if event.delta > 0 else -1
            self._bump_zoom(delta)
        else:
            # Scroll vertically
            self.canvas.yview_scroll(-1 * (event.delta // 120), "units")

    def _on_mousewheel_linux(self, event) -> None:
        # Linux sends Button-4 (up) / Button-5 (down)
        if event.state & 0x0004:  # Control
            delta = 1 if event.num == 4 else -1
            self._bump_zoom(delta)
        else:
            self.canvas.yview_scroll(-1 if event.num == 4 else 1, "units")

    def _bump_zoom(self, direction: int) -> None:
        z = float(self.preview_zoom.get())
        z *= 1.1 if direction > 0 else 1 / 1.1
        z = float(np.clip(z, 0.1, 6.0))
        self.preview_zoom.set(z)
        self._update_canvas_image()

    def _on_mouse_down(self, event) -> None:
        if not self.crop_mode.get():
            return
        self._crop_start_xy = (self.canvas.canvasx(event.x), self.canvas.canvasy(event.y))
        self._ensure_crop_rect()

    def _on_mouse_drag(self, event) -> None:
        if not self.crop_mode.get() or self._crop_start_xy is None:
            return
        x0, y0 = self._crop_start_xy
        x1 = self.canvas.canvasx(event.x)
        y1 = self.canvas.canvasy(event.y)
        self._draw_crop_rect_display(x0, y0, x1, y1)

    def _on_mouse_up(self, event) -> None:
        if not self.crop_mode.get() or self._crop_start_xy is None:
            return
        x0, y0 = self._crop_start_xy
        x1 = self.canvas.canvasx(event.x)
        y1 = self.canvas.canvasy(event.y)
        self._crop_start_xy = None

        # Convert from display coords -> working image coords
        if self.working_img is None:
            return

        out_scale = float(np.clip(self.output_scale.get(), 0.05, 10.0))
        zoom = float(np.clip(self.preview_zoom.get(), 0.05, 20.0))
        scale_total = out_scale * zoom

        wx0 = int(min(x0, x1) / scale_total)
        wy0 = int(min(y0, y1) / scale_total)
        wx1 = int(max(x0, x1) / scale_total)
        wy1 = int(max(y0, y1) / scale_total)

        h, w = self.working_img.shape[:2]
        wx0 = max(0, min(wx0, w - 1))
        wy0 = max(0, min(wy0, h - 1))
        wx1 = max(1, min(wx1, w))
        wy1 = max(1, min(wy1, h))

        # Minimum crop size
        if (wx1 - wx0) < 5 or (wy1 - wy0) < 5:
            self._crop_box_working = None
            return

        self._crop_box_working = (wx0, wy0, wx1, wy1)

    def apply_crop(self) -> None:
        if self.working_img is None or self._crop_box_working is None:
            return
        x0, y0, x1, y1 = self._crop_box_working
        self.working_img = self.working_img[y0:y1, x0:x1].copy()
        self._crop_box_working = None
        self._clear_crop_rect()
        self.request_update()

    def reset_crop(self) -> None:
        if self.original_img is None:
            return
        self.working_img = self.original_img.copy()
        self._crop_box_working = None
        self._clear_crop_rect()
        self.request_update()

    def _ensure_crop_rect(self) -> None:
        if self._crop_rect_id is None:
            self._crop_rect_id = self.canvas.create_rectangle(0, 0, 0, 0, outline="#ffcc00", width=2)

    def _clear_crop_rect(self) -> None:
        if self._crop_rect_id is not None:
            self.canvas.delete(self._crop_rect_id)
        self._crop_rect_id = None

    def _draw_crop_rect_display(self, x0: float, y0: float, x1: float, y1: float) -> None:
        self._ensure_crop_rect()
        self.canvas.coords(self._crop_rect_id, x0, y0, x1, y1)

    def _refresh_crop_rect_display(self) -> None:
        # If user selected a crop box, keep showing it.
        # (We only have the working-image coords after mouse-up; display it if present.)
        if self._crop_box_working is None or self._crop_rect_id is None:
            return
        if self.working_img is None:
            return

        x0, y0, x1, y1 = self._crop_box_working

        out_scale = float(np.clip(self.output_scale.get(), 0.05, 10.0))
        zoom = float(np.clip(self.preview_zoom.get(), 0.05, 20.0))
        scale_total = out_scale * zoom

        dx0 = x0 * scale_total
        dy0 = y0 * scale_total
        dx1 = x1 * scale_total
        dy1 = y1 * scale_total
        self.canvas.coords(self._crop_rect_id, dx0, dy0, dx1, dy1)


def main() -> None:
    image_path = sys.argv[1] if len(sys.argv) > 1 else None
    text_path = sys.argv[2] if len(sys.argv) > 2 else None

    root = tk.Tk()
    app = OverlayGUI(root, image_path=image_path, text_path=text_path)
    root.mainloop()


if __name__ == "__main__":
    main()