"""
Progress bar with ETA display.

Renders a compact, terminal-friendly progress bar that shows
percentage, frame count, elapsed time, and estimated time remaining.
"""

import sys
import time


class ProgressBar:
    """Terminal progress bar with ETA."""

    def __init__(self, total: int, width: int = 30, prefix: str = ""):
        self.total = total
        self.width = width
        self.prefix = prefix
        self.current = 0
        self.start_time = time.perf_counter()
        self._last_print_len = 0

    def update(self, n: int = 1) -> None:
        """Advance progress by n steps."""
        self.current += n
        self._render()

    def set(self, value: int) -> None:
        """Set progress to an absolute value."""
        self.current = value
        self._render()

    def finish(self) -> None:
        """Complete the progress bar."""
        self.current = self.total
        self._render()
        sys.stdout.write("\n")
        sys.stdout.flush()

    def _render(self) -> None:
        """Render the progress bar to stdout."""
        elapsed = time.perf_counter() - self.start_time
        pct = self.current / self.total if self.total > 0 else 1.0

        # Bar
        filled = int(self.width * pct)
        bar = "█" * filled + "░" * (self.width - filled)

        # ETA
        if pct > 0.02 and self.current > 0:
            eta = (elapsed / pct) * (1 - pct)
            eta_str = _format_duration(eta)
        else:
            eta_str = "..."

        # FPS
        fps = self.current / elapsed if elapsed > 0 else 0

        # Build line
        line = (
            f"\r    {self.prefix}|{bar}| "
            f"{pct:>5.1%} "
            f"{self.current}/{self.total} "
            f"[{_format_duration(elapsed)}<{eta_str}, {fps:.0f}fps]"
        )

        # Clear previous line if shorter
        padding = max(0, self._last_print_len - len(line))
        sys.stdout.write(line + " " * padding)
        sys.stdout.flush()
        self._last_print_len = len(line)


def _format_duration(seconds: float) -> str:
    """Format seconds as MM:SS or H:MM:SS."""
    if seconds < 0:
        return "0:00"
    s = int(seconds)
    if s < 3600:
        return f"{s // 60}:{s % 60:02d}"
    h = s // 3600
    m = (s % 3600) // 60
    return f"{h}:{m:02d}:{s % 60:02d}"
