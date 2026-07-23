"""
Command-line interface for the audio-to-video converter.

Supports single file and batch mode processing.
Reads defaults from .waveform.yaml config file.
"""

import argparse
import sys
from pathlib import Path

from .config import VideoConfig, THEMES, load_config_file, apply_config_file
from .composer import generate_video


AUDIO_EXTENSIONS = {".m4a", ".mp3", ".wav", ".flac", ".ogg", ".aac", ".wma", ".opus"}


def main():
    parser = argparse.ArgumentParser(
        description="Convert audio to MP4 with WhatsApp-style waveform animation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Single file (auto-names output as input_name.mp4)
  python audio_to_video.py input.m4a

  # Explicit output
  python audio_to_video.py input.m4a output.mp4

  # Batch mode: process all audio in a folder
  python audio_to_video.py --batch ./audio_folder ./output_folder

  # Custom theme and dimensions
  python audio_to_video.py input.m4a --theme dark --width 1080 --height 1080

  # Visual styles
  python audio_to_video.py input.m4a --bar-style gradient --bubble-position top

  # Quick preview (half-res, 15fps)
  python audio_to_video.py input.m4a --preview

  # Use a config file for defaults
  # (place .waveform.yaml in your project directory)
""",
    )

    # Input/Output
    parser.add_argument("input", nargs="?", help="Input audio file (M4A, MP3, WAV, etc.)")
    parser.add_argument("output", nargs="?", help="Output file path (default: input_name.mp4)")

    # Batch mode
    parser.add_argument("--batch", nargs=2, metavar=("INPUT_DIR", "OUTPUT_DIR"),
                        help="Batch mode: process all audio files in INPUT_DIR, save to OUTPUT_DIR")

    # Config file
    parser.add_argument("--config", type=str, default=None,
                        help="Path to .waveform.yaml config file")

    # Dimensions
    parser.add_argument("--width", type=int, default=1080, help="Video width (default: 1080)")
    parser.add_argument("--height", type=int, default=1920, help="Video height (default: 1920)")
    parser.add_argument("--fps", type=int, default=30, help="Frames per second (default: 30)")

    # Waveform
    parser.add_argument("--bars", type=int, default=48, help="Number of waveform bars (default: 48)")
    parser.add_argument("--no-spectral", action="store_true",
                        help="Use legacy global RMS instead of per-bar spectral analysis")
    parser.add_argument("--smoothing", type=float, default=0.3,
                        help="Temporal smoothing factor 0-1 (default: 0.3)")

    # Visual
    parser.add_argument("--theme", choices=list(THEMES.keys()), default="default",
                        help="Color theme (default: default)")
    parser.add_argument("--no-dot", action="store_true", help="Hide progress dot")
    parser.add_argument("--no-timestamp", action="store_true", help="Hide timestamp")
    parser.add_argument("--background", type=str, default=None,
                        help="Custom background image path")
    parser.add_argument("--bar-style", choices=["rounded", "flat", "gradient"], default="rounded",
                        help="Bar visual style (default: rounded)")
    parser.add_argument("--fade-duration", type=float, default=0.5,
                        help="Fade in/out duration in seconds (0 to disable, default: 0.5)")
    parser.add_argument("--bubble-position", choices=["center", "top", "bottom", "floating"],
                        default="center", help="Bubble position (default: center)")

    # Audio trimming
    parser.add_argument("--start", type=float, default=None,
                        help="Start time in seconds (trim audio)")
    parser.add_argument("--end", type=float, default=None,
                        help="End time in seconds (trim audio)")

    # Performance
    parser.add_argument("--preview", action="store_true",
                        help="Preview mode: half resolution, 15fps")
    parser.add_argument("--workers", type=int, default=0,
                        help="Number of parallel workers (default: auto)")

    # Output format
    parser.add_argument("--format", choices=["mp4", "webm", "gif"], default="mp4",
                        help="Output format (default: mp4)")

    args = parser.parse_args()

    # Load config file and apply as defaults
    config_path = Path(args.config) if args.config else None
    file_config = load_config_file(config_path)
    if file_config:
        apply_config_file(args, file_config)

    # Validate input mode
    if args.batch:
        _run_batch(args)
    elif args.input:
        _run_single(args)
    else:
        parser.print_help()
        sys.exit(1)


def _build_config(args) -> VideoConfig:
    """Build VideoConfig from CLI args."""
    bg_path = Path(args.background) if args.background else None

    config = VideoConfig(
        width=args.width,
        height=args.height,
        fps=args.fps,
        num_bars=args.bars,
        use_spectral=not args.no_spectral,
        smoothing_factor=args.smoothing,
        show_progress_dot=not args.no_dot,
        show_timestamp=not args.no_timestamp,
        theme=THEMES[args.theme],
        background_path=bg_path,
        start_time=args.start,
        end_time=args.end,
        preview=args.preview,
        workers=args.workers,
        bar_style=args.bar_style,
        fade_duration=args.fade_duration,
        bubble_position=args.bubble_position,
    )

    return config


def _resolve_output_path(args) -> str:
    """
    Determine the output file path.

    If output is not specified, auto-generate from input filename.
    """
    if args.output:
        output_path = args.output
    else:
        # Auto-generate: same name as input, with target extension
        input_path = Path(args.input)
        output_path = str(input_path.with_suffix(f".{args.format}"))

    # Ensure correct extension for format
    if args.format != "mp4":
        p = Path(output_path)
        if p.suffix.lstrip(".") != args.format:
            output_path = str(p.with_suffix(f".{args.format}"))

    return output_path


def _run_single(args) -> None:
    """Process a single audio file."""
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"❌ Error: Input file not found: {args.input}", file=sys.stderr)
        sys.exit(1)

    config = _build_config(args)
    output_path = _resolve_output_path(args)

    generate_video(
        audio_path=str(input_path),
        output_path=output_path,
        config=config,
    )


def _run_batch(args) -> None:
    """Process all audio files in a directory."""
    input_dir = Path(args.batch[0])
    output_dir = Path(args.batch[1])

    if not input_dir.exists():
        print(f"❌ Error: Input directory not found: {input_dir}", file=sys.stderr)
        sys.exit(1)

    output_dir.mkdir(parents=True, exist_ok=True)

    # Find all audio files
    audio_files = sorted(
        f for f in input_dir.iterdir()
        if f.suffix.lower() in AUDIO_EXTENSIONS and not f.name.startswith(".")
    )

    if not audio_files:
        print(f"❌ No audio files found in: {input_dir}", file=sys.stderr)
        sys.exit(1)

    print(f"📂 Batch mode: {len(audio_files)} files found in {input_dir}")
    print(f"📁 Output directory: {output_dir}\n")

    config = _build_config(args)

    for idx, audio_file in enumerate(audio_files, 1):
        output_ext = args.format
        output_file = output_dir / f"{audio_file.stem}.{output_ext}"

        print(f"\n{'─' * 60}")
        print(f"📄 [{idx}/{len(audio_files)}] {audio_file.name}")
        print(f"{'─' * 60}")

        try:
            generate_video(
                audio_path=str(audio_file),
                output_path=str(output_file),
                config=config,
            )
        except Exception as e:
            print(f"❌ Failed: {e}", file=sys.stderr)
            continue

    print(f"\n{'═' * 60}")
    print(f"✅ Batch complete! {len(audio_files)} videos in {output_dir}")


if __name__ == "__main__":
    main()
