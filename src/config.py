"""
Configuration dataclass, theme definitions, and YAML config file support.

Themes define the visual style of the waveform video.
Config files (.waveform.yaml) let you save defaults per project.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Tuple


Color = Tuple[int, int, int]


@dataclass
class Theme:
    """Color theme for the waveform video."""

    name: str
    bubble: Color = (14, 30, 27)         # Message bubble background
    played: Color = (246, 240, 224)      # Played waveform bars
    unplayed: Color = (73, 120, 117)     # Unplayed waveform bars
    accent: Color = (18, 57, 64)         # Accent elements
    progress_dot: Color = (246, 240, 224)  # Progress indicator dot
    timestamp: Color = (180, 180, 180)   # Timestamp text color


# Built-in themes
THEME_DEFAULT = Theme(name="default")

THEME_LIGHT = Theme(
    name="light",
    bubble=(255, 255, 255),
    played=(37, 211, 102),
    unplayed=(180, 180, 180),
    accent=(7, 94, 84),
    progress_dot=(37, 211, 102),
    timestamp=(100, 100, 100),
)

THEME_DARK = Theme(
    name="dark",
    bubble=(32, 44, 51),
    played=(0, 168, 132),
    unplayed=(80, 96, 104),
    accent=(0, 128, 105),
    progress_dot=(0, 168, 132),
    timestamp=(134, 150, 160),
)

THEMES = {
    "default": THEME_DEFAULT,
    "light": THEME_LIGHT,
    "dark": THEME_DARK,
}


@dataclass
class VideoConfig:
    """Full configuration for video generation."""

    # Dimensions
    width: int = 1080
    height: int = 1920
    fps: int = 30

    # Waveform
    num_bars: int = 48
    bar_width_ratio: float = 0.55
    min_bar_height: int = 4
    smoothing_factor: float = 0.3  # Temporal smoothing (0 = no smoothing, 1 = frozen)
    use_spectral: bool = True      # Per-bar frequency bands vs global RMS

    # Visual features
    show_progress_dot: bool = True
    show_timestamp: bool = True
    bubble_radius: int = 28
    bar_style: str = "rounded"     # "rounded", "flat", or "gradient"
    fade_duration: float = 0.5     # Seconds for fade in/out (0 = disabled)
    bubble_position: str = "center"  # "center", "top", "bottom", "floating"

    # Theme
    theme: Theme = field(default_factory=lambda: THEME_DEFAULT)

    # Paths
    background_path: Path | None = None

    # Audio trimming
    start_time: float | None = None  # Start time in seconds
    end_time: float | None = None    # End time in seconds

    # Performance
    preview: bool = False  # Half-res, lower fps for quick iteration
    workers: int = 0       # 0 = auto-detect CPU cores

    def __post_init__(self):
        if self.preview:
            self.width //= 2
            self.height //= 2
            self.fps = min(self.fps, 15)

        if self.workers == 0:
            import os
            self.workers = max(1, os.cpu_count() - 1)


def load_config_file(config_path: Path | None = None) -> dict:
    """
    Load configuration from a .waveform.yaml file.

    Search order:
    1. Explicit path (if provided)
    2. .waveform.yaml in current working directory
    3. ~/.waveform.yaml in home directory

    Returns a dict of config values (may be empty if no file found).
    """
    import json

    search_paths = []
    if config_path:
        search_paths.append(config_path)
    else:
        search_paths.append(Path.cwd() / ".waveform.yaml")
        search_paths.append(Path.home() / ".waveform.yaml")

    for path in search_paths:
        if path.exists():
            try:
                # Use simple YAML-like parsing (key: value per line)
                # to avoid requiring PyYAML as a dependency
                return _parse_yaml_simple(path)
            except Exception as e:
                print(f"⚠️  Warning: Failed to parse config {path}: {e}")
                return {}

    return {}


def _parse_yaml_simple(path: Path) -> dict:
    """
    Parse a simple YAML file (flat key: value pairs, no nesting).

    Supports:
        key: value
        key: true/false
        key: 123 (int)
        key: 1.5 (float)
        # comments
    """
    result = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if ":" not in line:
                continue

            key, _, value = line.partition(":")
            key = key.strip()
            value = value.strip()

            # Strip inline comments
            if " #" in value:
                value = value[:value.index(" #")].strip()

            # Type coercion
            if value.lower() in ("true", "yes"):
                result[key] = True
            elif value.lower() in ("false", "no"):
                result[key] = False
            elif value.isdigit() or (value.startswith("-") and value[1:].isdigit()):
                result[key] = int(value)
            elif _is_float(value):
                result[key] = float(value)
            else:
                # Strip quotes if present
                if (value.startswith('"') and value.endswith('"')) or \
                   (value.startswith("'") and value.endswith("'")):
                    value = value[1:-1]
                result[key] = value

    return result


def _is_float(s: str) -> bool:
    """Check if string is a valid float."""
    try:
        float(s)
        return True
    except ValueError:
        return False


def apply_config_file(args_namespace, file_config: dict) -> None:
    """
    Apply config file values as defaults for CLI args.

    CLI args take precedence over config file values.
    Only applies values that weren't explicitly set on the command line.
    """
    # Mapping from yaml keys to argparse dest names
    key_map = {
        "width": "width",
        "height": "height",
        "fps": "fps",
        "bars": "bars",
        "theme": "theme",
        "background": "background",
        "smoothing": "smoothing",
        "format": "format",
        "workers": "workers",
        "bar_style": "bar_style",
        "fade_duration": "fade_duration",
        "bubble_position": "bubble_position",
        "no_spectral": "no_spectral",
        "no_dot": "no_dot",
        "no_timestamp": "no_timestamp",
        "preview": "preview",
    }

    for yaml_key, arg_key in key_map.items():
        if yaml_key in file_config:
            # Only set if the arg is at its default (not explicitly provided)
            current = getattr(args_namespace, arg_key, None)
            default = _get_default_for_key(arg_key)
            if current == default:
                setattr(args_namespace, arg_key, file_config[yaml_key])


def _get_default_for_key(key: str):
    """Get the argparse default for a given key."""
    defaults = {
        "width": 1080,
        "height": 1920,
        "fps": 30,
        "bars": 48,
        "theme": "default",
        "background": None,
        "smoothing": 0.3,
        "format": "mp4",
        "workers": 0,
        "bar_style": "rounded",
        "fade_duration": 0.5,
        "bubble_position": "center",
        "no_spectral": False,
        "no_dot": False,
        "no_timestamp": False,
        "preview": False,
    }
    return defaults.get(key)
