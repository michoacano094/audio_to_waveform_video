"""
Video composition module.

Pipes rendered frames directly to FFmpeg for encoding.
Uses thread pool for parallel rendering with pre-computed frame context.
"""

import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

import numpy as np
from PIL import Image

from .config import VideoConfig
from .audio import extract_waveform_data
from .renderer import load_background, create_frame_context, render_frame, FrameContext
from .progress import ProgressBar


def generate_video(
    audio_path: str,
    output_path: str,
    config: VideoConfig,
) -> None:
    """
    Generate an MP4 video with waveform animation.

    Pipeline:
    1. Analyze audio → per-frame bar data
    2. Pre-compute static frame elements (background + bubble + geometry)
    3. Render dynamic bars in parallel via thread pool
    4. Pipe raw frames to FFmpeg
    """
    # Check FFmpeg is available
    _check_ffmpeg()

    print(f"🎵 Loading audio: {audio_path}")
    audio_data = extract_waveform_data(audio_path, config)

    duration = audio_data["duration"]
    num_frames = audio_data["num_frames"]
    frame_bar_data = audio_data["frame_bar_data"]

    print(f"📐 Video: {config.width}x{config.height} | {duration:.1f}s | {num_frames} frames @ {config.fps}fps")
    if config.use_spectral:
        print("🎼 Using per-bar spectral decomposition")

    # Pre-compute everything static
    print("🎨 Preparing frame context...")
    background = load_background(config)
    ctx = create_frame_context(background, config)

    # Start FFmpeg
    ffmpeg_cmd = _build_ffmpeg_command(audio_path, output_path, config)

    process = subprocess.Popen(
        ffmpeg_cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    try:
        print(f"🖼️  Rendering {num_frames} frames ({config.workers} threads)...")

        _render_and_pipe(process, ctx, frame_bar_data, num_frames, duration, config)

        process.stdin.close()
        process.wait()
        stderr = process.stderr.read()

        if process.returncode != 0:
            print(f"\n❌ FFmpeg error:\n{stderr.decode()}", file=sys.stderr)
            sys.exit(1)

        print(f"\n✅ Done! → {output_path}")
        _warn_if_too_large_for_whatsapp(output_path)

    except KeyboardInterrupt:
        process.kill()
        # Clean up partial output
        from pathlib import Path
        partial = Path(output_path)
        if partial.exists():
            partial.unlink()
        print("\n⚠️  Cancelled. Partial output removed.")
        sys.exit(130)
    except Exception as e:
        process.kill()
        raise e


def _warn_if_too_large_for_whatsapp(output_path: str) -> None:
    """
    Warn if the output exceeds WhatsApp's 16 MB media limit.

    WhatsApp Business API (used by GoHighLevel templates) rejects or fails to
    deliver video files larger than 16 MB. If we're over, suggest ways to shrink.
    """
    from pathlib import Path

    WHATSAPP_LIMIT = 16 * 1024 * 1024  # 16 MB

    p = Path(output_path)
    if not p.exists():
        return

    size = p.stat().st_size
    size_mb = size / (1024 * 1024)

    if size > WHATSAPP_LIMIT:
        print(
            f"⚠️  {size_mb:.1f} MB — exceeds WhatsApp's 16 MB limit. "
            "It may fail to load for recipients.\n"
            "   Try: --end to trim length, a lower --fps (e.g. 24), "
            "or smaller --width/--height.",
            file=sys.stderr,
        )
    else:
        print(f"📦 {size_mb:.1f} MB (within WhatsApp's 16 MB limit)")


def _check_ffmpeg() -> None:
    """Verify FFmpeg is installed and accessible."""
    import shutil
    if shutil.which("ffmpeg") is None:
        print(
            "❌ FFmpeg not found! Install it:\n"
            "   macOS:  brew install ffmpeg\n"
            "   Ubuntu: sudo apt install ffmpeg\n"
            "   Windows: choco install ffmpeg",
            file=sys.stderr,
        )
        sys.exit(1)


def _render_and_pipe(
    process: subprocess.Popen,
    ctx: FrameContext,
    frame_bar_data: np.ndarray,
    num_frames: int,
    duration: float,
    config: VideoConfig,
) -> None:
    """
    Render frames via thread pool and pipe to FFmpeg in order.
    Shows a progress bar with ETA.
    """
    batch_size = config.workers * 3
    progress = ProgressBar(total=num_frames)

    with ThreadPoolExecutor(max_workers=config.workers) as executor:
        for batch_start in range(0, num_frames, batch_size):
            batch_end = min(batch_start + batch_size, num_frames)

            # Submit batch
            futures = []
            for i in range(batch_start, batch_end):
                fut = executor.submit(
                    render_frame, ctx, i, num_frames,
                    frame_bar_data[i], duration,
                )
                futures.append(fut)

            # Write in order
            for fut in futures:
                raw_bytes = fut.result()
                process.stdin.write(raw_bytes)
                progress.update(1)

    progress.finish()


def _build_ffmpeg_command(
    audio_path: str, output_path: str, config: VideoConfig
) -> list:
    """Build the FFmpeg command for encoding."""
    cmd = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel", "error",
        # Raw video input from pipe
        "-f", "rawvideo",
        "-vcodec", "rawvideo",
        "-pix_fmt", "rgb24",
        "-s", f"{config.width}x{config.height}",
        "-r", str(config.fps),
        "-i", "-",
    ]

    # Audio input with optional trimming
    if config.start_time is not None:
        cmd += ["-ss", str(config.start_time)]
    cmd += ["-i", audio_path]
    if config.end_time is not None:
        dur = config.end_time - (config.start_time or 0)
        cmd += ["-t", str(dur)]

    cmd += [
        # Video encoding — tuned for WhatsApp / GoHighLevel template compatibility.
        # WhatsApp requires H.264 + AAC in an MP4, recommends the Baseline profile
        # for broad device support, and needs the moov atom up front for streaming.
        "-c:v", "libx264",
        "-profile:v", "baseline",   # Max device compatibility (WhatsApp recommendation)
        "-level", "4.0",
        "-preset", "veryfast",      # Much better compression than ultrafast → smaller files
        "-crf", "23",               # Balanced quality/size to help stay under the 16 MB limit
        "-maxrate", "4M",           # Cap bitrate so files don't blow past 16 MB
        "-bufsize", "8M",
        "-pix_fmt", "yuv420p",
        # Audio encoding — single AAC-LC stereo stream
        "-c:a", "aac",
        "-b:a", "128k",
        "-ar", "44100",
        "-ac", "2",
        "-shortest",
        # Place the moov atom at the start for progressive/streaming playback.
        # Without this, WhatsApp and many web players fail to load the video.
        "-movflags", "+faststart",
        output_path,
    ]

    return cmd
