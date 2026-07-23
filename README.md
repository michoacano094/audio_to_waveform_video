# Audio to WhatsApp-Style Waveform Video (v2)

Converts audio files into MP4 videos with animated waveform bars that react to the audio spectrum, styled like a WhatsApp voice message.

## Features

- **Per-bar spectral animation** — Each bar reacts to its own frequency band
- **Direct FFmpeg piping** — No temp files, frames go straight to the encoder
- **Parallel rendering** — Uses all CPU cores (~370+ fps throughput)
- **Batch mode** — Process a whole folder in one command
- **3 themes** — `default` (brand), `dark`, `light`
- **3 bar styles** — `rounded` (caps), `flat`, `gradient` (vertical shading)
- **Bubble positions** — `center`, `top`, `bottom`, `floating`
- **Fade in/out** — Smooth entry/exit animation
- **Progress dot + timestamp** — Authentic WhatsApp look
- **Audio trimming** — `--start` / `--end`
- **Preview mode** — Half resolution + 15fps for quick iteration
- **Config file** — `.waveform.yaml` saves your defaults
- **Auto output name** — Just pass the input, output is auto-generated
- **Progress bar with ETA** — Shows fps, elapsed, and time remaining
- **FFmpeg check** — Friendly error if FFmpeg isn't installed

## Requirements

- Python 3.10+
- FFmpeg (`brew install ffmpeg` on macOS)

## Install

```bash
cd audio_to_waveform_video
pip install -r requirements.txt
```

## Usage

```bash
# Simplest — auto-generates dinero.mp4 next to the input
python audio_to_video.py dinero.m4a

# Explicit output
python audio_to_video.py dinero.m4a output.mp4

# Batch mode
python audio_to_video.py --batch ./audio_files ./output_videos

# Visual styles
python audio_to_video.py dinero.m4a --bar-style gradient --theme dark
python audio_to_video.py dinero.m4a --bubble-position top --fade-duration 1.0

# Square for Instagram
python audio_to_video.py dinero.m4a --width 1080 --height 1080

# Quick preview
python audio_to_video.py dinero.m4a --preview

# Trim a segment
python audio_to_video.py dinero.m4a --start 10 --end 45

# Custom background
python audio_to_video.py dinero.m4a --background my_bg.png

# Disable visual features
python audio_to_video.py dinero.m4a --no-dot --no-timestamp --fade-duration 0
```

## Config File

Place a `.waveform.yaml` in your project directory (or `~/.waveform.yaml` globally) to set defaults:

```yaml
# .waveform.yaml
width: 1080
height: 1920
fps: 30
bars: 48
smoothing: 0.3
theme: default           # default, light, dark
bar_style: rounded       # rounded, flat, gradient
fade_duration: 0.5       # seconds (0 to disable)
bubble_position: center  # center, top, bottom, floating
format: mp4
```

CLI flags always override config file values.

## CLI Reference

| Flag | Default | Description |
|------|---------|-------------|
| `--width` | 1080 | Video width in pixels |
| `--height` | 1920 | Video height in pixels |
| `--fps` | 30 | Frames per second |
| `--bars` | 48 | Number of waveform bars |
| `--theme` | default | Color theme: `default`, `light`, `dark` |
| `--bar-style` | rounded | Bar style: `rounded`, `flat`, `gradient` |
| `--fade-duration` | 0.5 | Fade in/out in seconds (0 = off) |
| `--bubble-position` | center | Position: `center`, `top`, `bottom`, `floating` |
| `--smoothing` | 0.3 | Temporal smoothing (0=none, 1=frozen) |
| `--background` | built-in | Path to custom background image |
| `--start` | — | Start time in seconds |
| `--end` | — | End time in seconds |
| `--preview` | off | Half resolution + 15fps |
| `--workers` | auto | Parallel rendering workers |
| `--format` | mp4 | Output: `mp4`, `webm`, `gif` |
| `--config` | auto | Path to .waveform.yaml |
| `--no-spectral` | off | Use legacy global RMS |
| `--no-dot` | off | Hide progress dot |
| `--no-timestamp` | off | Hide elapsed time |
| `--batch` | — | Batch mode: `INPUT_DIR OUTPUT_DIR` |

## Project Structure

```
audio_to_waveform_video/
├── audio_to_video.py       # Entry point
├── .waveform.yaml          # Default config (customize this)
├── src/
│   ├── __init__.py
│   ├── audio.py            # Audio analysis (FFmpeg decode + librosa spectral)
│   ├── renderer.py         # Frame rendering (pre-computed stamps + numpy)
│   ├── composer.py         # Video assembly (FFmpeg pipe + thread pool)
│   ├── config.py           # Config dataclass + themes + YAML loader
│   ├── progress.py         # Terminal progress bar with ETA
│   └── cli.py              # Argument parsing + batch logic
├── whatsbackground.webp    # Default background
├── requirements.txt
└── README.md
```

## Performance

On a 10-core Apple Silicon Mac:
- 94 seconds of audio → 2837 frames → **~9 seconds** total render time
- ~370+ frames/sec throughput
- Preview mode: ~2 seconds for the same file

The bottleneck is numpy memory operations (~6MB per frame × 2837 frames = 17GB throughput).
