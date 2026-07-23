#!/usr/bin/env python3
"""
Audio to Video Converter with WhatsApp-style Waveform Animation (v2).

Entry point — delegates to src.cli for the full CLI interface.

Quick usage:
    python audio_to_video.py input.m4a output.mp4
    python audio_to_video.py --batch ./audio_folder ./output_folder
    python audio_to_video.py input.m4a output.mp4 --theme dark --preview
"""

from src.cli import main

if __name__ == "__main__":
    main()
