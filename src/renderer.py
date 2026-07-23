"""
Frame rendering module.

Optimized for maximum throughput using numpy array operations for
per-frame dynamic elements. PIL is only used once to build the static
base image and pre-render bar cap stamps.
"""

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from dataclasses import dataclass, field
from pathlib import Path

from .config import VideoConfig, Color


@dataclass
class FrameContext:
    """
    Pre-computed frame rendering context.

    The base_array contains background + bubble + play button.
    Bar stamps are pre-rendered for each possible height.
    """
    base_array: np.ndarray  # (H, W, 3) uint8

    # Geometry
    wave_left: int
    wave_center_y: int
    bar_width: int
    bar_gap: int
    max_bar_height: int
    num_bars: int

    # Config
    config: VideoConfig
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont | None

    # Pre-computed bar x positions
    bar_x_positions: list[int]

    # Colors as numpy arrays for fast assignment
    color_played: np.ndarray
    color_unplayed: np.ndarray
    color_dot: np.ndarray

    # Timestamp y position
    timestamp_y: int

    # Pre-rendered bar stamps: dict[height] -> (played_stamp, unplayed_stamp, mask)
    bar_stamps: dict = field(default_factory=dict)

    # Pre-rendered timestamp cache
    timestamp_cache: object | None = None

    # Bubble y position (for fade calculations)
    bubble_y: int = 0
    bubble_height: int = 0


def load_background(config: VideoConfig) -> Image.Image:
    """Load and prepare the background image for the video dimensions."""
    bg_path = config.background_path
    if bg_path is None:
        bg_path = Path(__file__).parent.parent / "whatsbackground.webp"

    if not bg_path.exists():
        raise FileNotFoundError(
            f"Background image not found: {bg_path}\n"
            "Provide a background with --background or place 'whatsbackground.webp' "
            "in the project root."
        )

    img = Image.open(bg_path).convert("RGB")
    width, height = config.width, config.height

    img_ratio = img.width / img.height
    target_ratio = width / height

    if img_ratio > target_ratio:
        new_height = height
        new_width = int(height * img_ratio)
    else:
        new_width = width
        new_height = int(width / img_ratio)

    img = img.resize((new_width, new_height), Image.LANCZOS)

    left = (new_width - width) // 2
    top = (new_height - height) // 2
    img = img.crop((left, top, left + width, top + height))

    return img


def create_frame_context(background: Image.Image, config: VideoConfig) -> FrameContext:
    """
    Pre-compute all static elements, geometry, and bar stamps.

    Called once; the result is shared across all render calls.
    """
    theme = config.theme
    width, height = config.width, config.height
    num_bars = config.num_bars

    # For floating mode: solid dark background instead of the image
    if config.bubble_position == "floating":
        base = Image.new("RGB", (width, height), (18, 18, 18))
    else:
        base = background.copy()

    draw = ImageDraw.Draw(base)

    # Bubble sizing — floating gets a smaller, more compact bubble
    if config.bubble_position == "floating":
        bubble_margin_x = int(width * 0.12)
        bubble_height = int(height * 0.07)
    else:
        bubble_margin_x = int(width * 0.08)
        bubble_height = int(height * 0.10)

    # Bubble vertical position
    if config.bubble_position == "top":
        bubble_y = int(height * 0.12)
    elif config.bubble_position == "bottom":
        bubble_y = int(height * 0.78)
    else:  # center and floating
        bubble_y = (height - bubble_height) // 2

    # Bubble shadow + background
    if config.bubble_position == "floating":
        # No shadow — just the bubble on solid dark bg
        pass
    else:
        shadow_offset = 4
        draw.rounded_rectangle(
            [bubble_margin_x + shadow_offset, bubble_y + shadow_offset,
             width - bubble_margin_x + shadow_offset, bubble_y + bubble_height + shadow_offset],
            radius=config.bubble_radius, fill=(30, 30, 30),
        )

    # Bubble fill
    draw.rounded_rectangle(
        [bubble_margin_x, bubble_y, width - bubble_margin_x, bubble_y + bubble_height],
        radius=config.bubble_radius, fill=theme.bubble,
    )

    # Play button
    circle_x = bubble_margin_x + 50
    circle_y = bubble_y + bubble_height // 2
    circle_r = 22
    draw.ellipse(
        [circle_x - circle_r, circle_y - circle_r,
         circle_x + circle_r, circle_y + circle_r],
        fill=theme.played,
    )
    pause_bar_w, pause_bar_h, pause_gap = 4, 16, 5
    draw.rectangle(
        [circle_x - pause_gap - pause_bar_w // 2, circle_y - pause_bar_h // 2,
         circle_x - pause_gap + pause_bar_w // 2, circle_y + pause_bar_h // 2],
        fill=theme.bubble,
    )
    draw.rectangle(
        [circle_x + pause_gap - pause_bar_w // 2, circle_y - pause_bar_h // 2,
         circle_x + pause_gap + pause_bar_w // 2, circle_y + pause_bar_h // 2],
        fill=theme.bubble,
    )

    # Waveform geometry
    wave_left = circle_x + circle_r + 30
    wave_right = width - bubble_margin_x - 30
    wave_area_width = wave_right - wave_left
    wave_center_y = bubble_y + bubble_height // 2
    if config.show_timestamp:
        wave_center_y -= 8

    bar_total_width = wave_area_width / num_bars
    bar_width = max(int(bar_total_width * config.bar_width_ratio), 3)
    bar_gap = max(int(bar_total_width * (1 - config.bar_width_ratio)), 2)
    max_bar_height = int(bubble_height * 0.50)

    bar_x_positions = [wave_left + i * (bar_width + bar_gap) for i in range(num_bars)]
    timestamp_y = wave_center_y + max_bar_height // 2 + 10

    # Load font once (cross-platform)
    font = None
    if config.show_timestamp:
        font = _load_system_font(20)

    # Convert to numpy
    base_array = np.array(base)

    # Pre-compute color arrays
    color_played = np.array(theme.played, dtype=np.uint8)
    color_unplayed = np.array(theme.unplayed, dtype=np.uint8)
    color_dot = np.array(theme.progress_dot, dtype=np.uint8)

    # Pre-render bar stamps for rounded/gradient styles
    bar_stamps = {}
    if config.bar_style in ("rounded", "gradient"):
        bar_stamps = _prerender_bar_stamps(
            bar_width, max_bar_height, config.min_bar_height,
            theme.played, theme.unplayed, theme.bubble,
            config.bar_style,
        )

    # Pre-render timestamp cache
    timestamp_cache = None
    if config.show_timestamp and font:
        timestamp_cache = TimestampCache(font, theme.timestamp, theme.bubble)

    return FrameContext(
        base_array=base_array,
        wave_left=wave_left,
        wave_center_y=wave_center_y,
        bar_width=bar_width,
        bar_gap=bar_gap,
        max_bar_height=max_bar_height,
        num_bars=num_bars,
        config=config,
        font=font,
        bar_x_positions=bar_x_positions,
        color_played=color_played,
        color_unplayed=color_unplayed,
        color_dot=color_dot,
        timestamp_y=timestamp_y,
        bar_stamps=bar_stamps,
        timestamp_cache=timestamp_cache,
        bubble_y=bubble_y,
        bubble_height=bubble_height,
    )


def _prerender_bar_stamps(
    bar_width: int,
    max_height: int,
    min_height: int,
    played_color: tuple,
    unplayed_color: tuple,
    bg_color: tuple,
    style: str,
) -> dict:
    """
    Pre-render bar images for every possible height.

    Each stamp is a small numpy array with rounded caps (and optionally
    a vertical gradient). A mask marks which pixels to blit.

    Returns: dict[height] -> {
        "played": np.ndarray (h, w, 3),
        "unplayed": np.ndarray (h, w, 3),
        "mask": np.ndarray (h, w) bool
    }
    """
    stamps = {}
    radius = bar_width // 2

    for h in range(min_height, max_height + 1):
        # Render rounded bar with PIL (once per unique height)
        img_played = Image.new("RGB", (bar_width, h), bg_color)
        img_unplayed = Image.new("RGB", (bar_width, h), bg_color)
        draw_p = ImageDraw.Draw(img_played)
        draw_u = ImageDraw.Draw(img_unplayed)

        if style == "gradient":
            # Draw gradient bar with rounded rectangle mask
            # Create gradient from lighter (top) to darker (bottom)
            played_light = _lighten(played_color, 0.3)
            unplayed_light = _lighten(unplayed_color, 0.3)

            for row in range(h):
                t = row / max(h - 1, 1)
                p_color = _lerp_color(played_light, played_color, t)
                u_color = _lerp_color(unplayed_light, unplayed_color, t)
                draw_p.line([(0, row), (bar_width - 1, row)], fill=p_color)
                draw_u.line([(0, row), (bar_width - 1, row)], fill=u_color)

            # Apply rounded mask
            mask_img = Image.new("L", (bar_width, h), 0)
            mask_draw = ImageDraw.Draw(mask_img)
            mask_draw.rounded_rectangle([0, 0, bar_width - 1, h - 1], radius=radius, fill=255)
            mask_arr = np.array(mask_img) > 128

            # Zero out pixels outside mask
            arr_p = np.array(img_played)
            arr_u = np.array(img_unplayed)
            bg_arr = np.array(bg_color, dtype=np.uint8)
            arr_p[~mask_arr] = bg_arr
            arr_u[~mask_arr] = bg_arr
        else:
            # Simple rounded rectangle
            draw_p.rounded_rectangle([0, 0, bar_width - 1, h - 1], radius=radius, fill=played_color)
            draw_u.rounded_rectangle([0, 0, bar_width - 1, h - 1], radius=radius, fill=unplayed_color)

            arr_p = np.array(img_played)
            arr_u = np.array(img_unplayed)
            bg_arr = np.array(bg_color, dtype=np.uint8)
            mask_arr = np.any(arr_p != bg_arr, axis=2)

        stamps[h] = {
            "played": arr_p,
            "unplayed": arr_u,
            "mask": mask_arr,
        }

    return stamps


def _lighten(color: tuple, amount: float) -> tuple:
    """Lighten a color by blending toward white."""
    return tuple(min(255, int(c + (255 - c) * amount)) for c in color)


def _lerp_color(c1: tuple, c2: tuple, t: float) -> tuple:
    """Linear interpolation between two colors."""
    return tuple(int(a + (b - a) * t) for a, b in zip(c1, c2))


def render_frame(
    ctx: FrameContext,
    frame_idx: int,
    num_frames: int,
    bar_data: np.ndarray,
    duration: float,
) -> bytes:
    """
    Render a single frame and return raw RGB bytes.

    Uses pre-rendered bar stamps for rounded/gradient bars,
    falls back to flat numpy slicing for maximum speed.
    """
    config = ctx.config

    # Fast numpy copy of pre-rendered base
    frame = ctx.base_array.copy()

    # Progress
    progress = frame_idx / max(num_frames - 1, 1)
    played_bars = int(progress * ctx.num_bars)

    # Fade in/out alpha
    fade_alpha = _compute_fade_alpha(frame_idx, num_frames, duration, config)

    # Draw bars
    min_bar_h = config.min_bar_height
    use_stamps = config.bar_style in ("rounded", "gradient") and ctx.bar_stamps

    for i in range(ctx.num_bars):
        bar_h = max(int(bar_data[i] * ctx.max_bar_height), min_bar_h)
        # Clamp to pre-rendered range
        bar_h = min(bar_h, ctx.max_bar_height)

        x = ctx.bar_x_positions[i]
        y_top = ctx.wave_center_y - bar_h // 2

        is_played = i <= played_bars

        if use_stamps and bar_h in ctx.bar_stamps:
            stamp = ctx.bar_stamps[bar_h]
            src = stamp["played"] if is_played else stamp["unplayed"]
            mask = stamp["mask"]
            region = frame[y_top:y_top + bar_h, x:x + ctx.bar_width]
            region[mask] = src[mask]
        else:
            # Flat fallback
            y_bottom = y_top + bar_h
            color = ctx.color_played if is_played else ctx.color_unplayed
            frame[y_top:y_bottom, x:x + ctx.bar_width] = color

    # Progress dot
    if config.show_progress_dot:
        dot_x = ctx.bar_x_positions[min(played_bars, ctx.num_bars - 1)] + ctx.bar_width // 2
        dot_y = ctx.wave_center_y
        dot_r = 6
        y_start = max(dot_y - dot_r, 0)
        x_start = max(dot_x - dot_r, 0)
        y_indices, x_indices = np.ogrid[0:dot_r * 2, 0:dot_r * 2]
        mask = (x_indices - dot_r) ** 2 + (y_indices - dot_r) ** 2 <= dot_r ** 2
        region = frame[y_start:y_start + dot_r * 2, x_start:x_start + dot_r * 2]
        region[mask] = ctx.color_dot

    # Timestamp (from pre-rendered cache)
    if config.show_timestamp and ctx.timestamp_cache is not None:
        elapsed_sec = int(duration * progress)
        total_sec = int(duration)
        cache_key = (elapsed_sec, total_sec)

        ts_arr, ts_mask, ts_h, ts_w = ctx.timestamp_cache[cache_key]
        y = ctx.timestamp_y
        x = ctx.wave_left
        # Bounds check
        if y + ts_h <= frame.shape[0] and x + ts_w <= frame.shape[1]:
            region = frame[y:y + ts_h, x:x + ts_w]
            region[ts_mask] = ts_arr[ts_mask]

    # Apply fade in/out
    if fade_alpha < 1.0:
        frame = _apply_fade(frame, ctx.base_array, fade_alpha, ctx)

    return frame.tobytes()


def _compute_fade_alpha(
    frame_idx: int, num_frames: int, duration: float, config: VideoConfig
) -> float:
    """
    Compute fade alpha for the current frame.

    Returns 1.0 for full visibility, 0.0 for fully faded.
    """
    if config.fade_duration <= 0:
        return 1.0

    fade_frames = int(config.fade_duration * config.fps)
    if fade_frames == 0:
        return 1.0

    # Fade in
    if frame_idx < fade_frames:
        return frame_idx / fade_frames

    # Fade out
    frames_from_end = num_frames - 1 - frame_idx
    if frames_from_end < fade_frames:
        return frames_from_end / fade_frames

    return 1.0


def _apply_fade(
    frame: np.ndarray, base: np.ndarray, alpha: float, ctx: FrameContext
) -> np.ndarray:
    """
    Apply fade by blending the bubble region toward the background.

    Only fades the bubble area, not the entire frame.
    """
    # Blend the bubble region between current frame and base (without bubble)
    # Simple approach: blend entire frame toward a darkened version
    faded = (frame.astype(np.float32) * alpha + base.astype(np.float32) * (1 - alpha))
    return faded.astype(np.uint8)


class TimestampCache:
    """Lazy cache for pre-rendered timestamp text as numpy arrays."""

    def __init__(self, font, text_color, bg_color):
        self.font = font
        self.text_color = text_color
        self.bg_color = bg_color
        self._cache = {}

    def __contains__(self, key):
        return True

    def __getitem__(self, key):
        if key not in self._cache:
            elapsed_sec, total_sec = key
            text = f"{_format_time(elapsed_sec)} / {_format_time(total_sec)}"
            self._cache[key] = self._render_text(text)
        return self._cache[key]

    def _render_text(self, text: str):
        """Render text string to numpy array + mask."""
        bbox = self.font.getbbox(text)
        w = bbox[2] - bbox[0] + 4
        h = bbox[3] - bbox[1] + 4

        img = Image.new("RGB", (w, h), self.bg_color)
        draw = ImageDraw.Draw(img)
        draw.text((-bbox[0] + 2, -bbox[1] + 2), text, fill=self.text_color, font=self.font)

        arr = np.array(img)
        bg = np.array(self.bg_color, dtype=np.uint8)
        mask = np.any(arr != bg, axis=2)

        return (arr, mask, h, w)


def _load_system_font(size: int):
    """
    Load a sans-serif font, trying platform-specific paths.

    Falls back to Pillow's built-in default if nothing is found.
    """
    import platform

    candidates = []
    system = platform.system()

    if system == "Darwin":
        candidates = [
            "/System/Library/Fonts/SFCompact.ttf",
            "/System/Library/Fonts/Helvetica.ttc",
            "/System/Library/Fonts/Supplemental/Arial.ttf",
        ]
    elif system == "Linux":
        candidates = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
            "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
            "/usr/share/fonts/TTF/DejaVuSans.ttf",  # Arch
            "/usr/share/fonts/dejavu-sans-fonts/DejaVuSans.ttf",  # Fedora
            "/usr/share/fonts/noto/NotoSans-Regular.ttf",
        ]
    elif system == "Windows":
        candidates = [
            "C:/Windows/Fonts/arial.ttf",
            "C:/Windows/Fonts/segoeui.ttf",
        ]

    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except (OSError, IOError):
            continue

    # Final fallback
    return ImageFont.load_default()


def _format_time(seconds) -> str:
    """Format seconds as M:SS."""
    m = int(seconds) // 60
    s = int(seconds) % 60
    return f"{m}:{s:02d}"
