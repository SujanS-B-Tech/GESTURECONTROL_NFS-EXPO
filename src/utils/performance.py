"""
Performance monitoring utility for GESTUREDRIVE X.
Tracks frame rates, loop latencies, and drops to ensure low-latency responsiveness.
"""

import time
from collections import deque
from typing import Tuple

class PerformanceTracker:
    """Calculates FPS, latency, and performance statistics across frames."""

    def __init__(self, window_size: int = 30):
        self.window_size = window_size
        self._frame_times = deque(maxlen=window_size)
        self._latencies = deque(maxlen=window_size)
        self._last_timestamp = time.perf_counter()
        self._dropped_frames = 0
        self._total_frames = 0

    def start_frame(self) -> float:
        """Mark the beginning of frame processing. Returns start timestamp."""
        return time.perf_counter()

    def end_frame(self, start_timestamp: float):
        """Mark the end of frame processing and update latency & FPS buffers."""
        now = time.perf_counter()
        latency_ms = (now - start_timestamp) * 1000.0
        self._latencies.append(latency_ms)

        dt = now - self._last_timestamp
        if dt > 0:
            self._frame_times.append(dt)
        self._last_timestamp = now
        self._total_frames += 1

    def record_dropped_frame(self):
        """Record a frame dropped due to buffer overflow or stale frame discarding."""
        self._dropped_frames += 1

    @property
    def fps(self) -> float:
        """Current smoothed frames per second."""
        if not self._frame_times:
            return 0.0
        avg_dt = sum(self._frame_times) / len(self._frame_times)
        return 1.0 / avg_dt if avg_dt > 0 else 0.0

    @property
    def latency_ms(self) -> float:
        """Average processing latency in milliseconds."""
        if not self._latencies:
            return 0.0
        return sum(self._latencies) / len(self._latencies)

    @property
    def total_frames(self) -> int:
        return self._total_frames

    @property
    def dropped_frames(self) -> int:
        return self._dropped_frames

    def get_stats(self) -> Tuple[float, float, int, int]:
        """Returns (fps, latency_ms, total_frames, dropped_frames)."""
        return self.fps, self.latency_ms, self.total_frames, self.dropped_frames

    def reset(self):
        """Reset internal metrics."""
        self._frame_times.clear()
        self._latencies.clear()
        self._last_timestamp = time.perf_counter()
        self._dropped_frames = 0
        self._total_frames = 0

