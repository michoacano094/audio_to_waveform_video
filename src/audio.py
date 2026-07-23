"""
Audio analysis module.

Extracts waveform amplitude and spectral data from audio files
for driving the waveform animation.
"""

import subprocess
import numpy as np
import librosa

from .config import VideoConfig


def _load_audio_ffmpeg(audio_path: str, sr: int = 22050) -> tuple[np.ndarray, int]:
    """
    Load audio using FFmpeg directly — fastest path for any format.

    Decodes to raw PCM via pipe, avoiding librosa's slow audioread fallback
    for formats like M4A/AAC that libsndfile doesn't support.
    """
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel", "error",
        "-i", audio_path,
        "-f", "f32le",       # 32-bit float little-endian PCM
        "-acodec", "pcm_f32le",
        "-ar", str(sr),      # Resample to target rate
        "-ac", "1",          # Mono
        "-",                 # Output to stdout
    ]

    result = subprocess.run(cmd, capture_output=True)

    if result.returncode != 0:
        raise RuntimeError(
            f"FFmpeg failed to decode audio: {result.stderr.decode().strip()}"
        )

    # Convert raw bytes to numpy float32 array
    y = np.frombuffer(result.stdout, dtype=np.float32)
    return y, sr


def extract_waveform_data(audio_path: str, config: VideoConfig) -> dict:
    """
    Extract amplitude and spectral data from an audio file.

    Returns a dict with:
        - bar_amplitudes: static bar heights (num_bars,)
        - frame_bar_data: per-frame bar heights with spectral decomposition (num_frames, num_bars)
        - duration: audio duration in seconds
        - num_frames: total frame count
    """
    sr = 22050
    y, sr = _load_audio_ffmpeg(audio_path, sr=sr)

    # Apply trimming if specified
    if config.start_time is not None:
        start_sample = int(config.start_time * sr)
        y = y[start_sample:]
    if config.end_time is not None:
        end_sample = int(config.end_time * sr)
        if config.start_time is not None:
            end_sample -= int(config.start_time * sr)
        y = y[:end_sample]

    duration = len(y) / sr
    num_frames = int(duration * config.fps)
    num_bars = config.num_bars

    if config.use_spectral:
        frame_bar_data = _extract_spectral_bars(y, sr, num_frames, num_bars, config)
    else:
        frame_bar_data = _extract_rms_bars(y, sr, num_frames, num_bars)

    # Apply temporal smoothing for organic movement
    if config.smoothing_factor > 0:
        frame_bar_data = _apply_temporal_smoothing(frame_bar_data, config.smoothing_factor)

    # Static bar amplitudes (average across all frames, used as fallback)
    bar_amplitudes = np.mean(frame_bar_data, axis=0)

    return {
        "bar_amplitudes": bar_amplitudes,
        "frame_bar_data": frame_bar_data,
        "duration": duration,
        "num_frames": num_frames,
    }


def _extract_spectral_bars(
    y: np.ndarray, sr: int, num_frames: int, num_bars: int, config: VideoConfig
) -> np.ndarray:
    """
    Extract per-bar spectral energy using mel-frequency bands.

    Each bar corresponds to a frequency band, giving independent
    movement that reacts to different parts of the audio spectrum.
    """
    # Use mel spectrogram with num_bars frequency bands
    hop_length = max(1, len(y) // num_frames)

    S = librosa.feature.melspectrogram(
        y=y, sr=sr, n_mels=num_bars, hop_length=hop_length, n_fft=2048
    )
    S_db = librosa.power_to_db(S, ref=np.max)

    # Normalize to 0-1 range
    S_norm = (S_db - S_db.min()) / (S_db.max() - S_db.min() + 1e-8)

    # Interpolate to exact frame count
    frame_bar_data = np.zeros((num_frames, num_bars))
    for bar_idx in range(num_bars):
        frame_bar_data[:, bar_idx] = np.interp(
            np.linspace(0, S_norm.shape[1] - 1, num_frames),
            np.arange(S_norm.shape[1]),
            S_norm[bar_idx, :],
        )

    # Apply floor so bars are never invisible
    frame_bar_data = np.clip(frame_bar_data, 0.08, 1.0)

    return frame_bar_data


def _extract_rms_bars(
    y: np.ndarray, sr: int, num_frames: int, num_bars: int
) -> np.ndarray:
    """
    Legacy extraction: static bar heights modulated by global RMS energy.
    """
    hop_length = 512
    rms = librosa.feature.rms(y=y, frame_length=2048, hop_length=hop_length)[0]
    rms_norm = rms / (rms.max() + 1e-8)

    rms_per_frame = np.interp(
        np.linspace(0, len(rms) - 1, num_frames),
        np.arange(len(rms)),
        rms_norm,
    )

    # Compute static bar amplitudes from audio segments
    total_samples = len(y)
    samples_per_bar = total_samples // num_bars

    bar_amplitudes = np.zeros(num_bars)
    for i in range(num_bars):
        start = i * samples_per_bar
        end = start + samples_per_bar
        segment = np.abs(y[start:end])
        bar_amplitudes[i] = np.sqrt(np.mean(segment**2))

    bar_amplitudes = bar_amplitudes / (bar_amplitudes.max() + 1e-8)
    bar_amplitudes = np.clip(
        bar_amplitudes + np.random.uniform(-0.05, 0.05, num_bars), 0.08, 1.0
    )

    # Create frame data by modulating static bars with RMS
    frame_bar_data = np.zeros((num_frames, num_bars))
    for i in range(num_frames):
        pulse = 0.85 + 0.15 * rms_per_frame[i]
        frame_bar_data[i] = bar_amplitudes * pulse

    return frame_bar_data


def _apply_temporal_smoothing(
    frame_bar_data: np.ndarray, factor: float
) -> np.ndarray:
    """
    Apply exponential moving average smoothing across frames.

    This prevents jarring jumps between frames, giving bars
    an organic, fluid movement.
    """
    smoothed = np.copy(frame_bar_data)
    for i in range(1, len(smoothed)):
        smoothed[i] = factor * smoothed[i - 1] + (1 - factor) * smoothed[i]
    return smoothed
