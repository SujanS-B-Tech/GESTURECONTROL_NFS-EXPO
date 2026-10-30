"""
Webcam capture module for GESTUREDRIVE X.
Runs a dedicated background thread for frame acquisition, maintaining a 
single-frame latest buffer to drop stale frames and minimize input latency.
"""

import cv2
import threading
import time
from typing import Optional, Tuple, List
import numpy as np

from src.utils.logger import logger


class WebcamCapture:
    """Threaded OpenCV webcam capture engine with drop-stale-frame logic and auto-recovery."""

    def __init__(
        self,
        device_index: int = 0,
        width: int = 1280,
        height: int = 720,
        fps: int = 30,
        mirror_horizontal: bool = True,
        api_preference: str = "DSHOW"
    ):
        self.device_index = device_index
        self.target_width = width
        self.target_height = height
        self.target_fps = fps
        self.mirror_horizontal = mirror_horizontal
        self.api_preference = api_preference

        self._cap: Optional[cv2.VideoCapture] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._lock = threading.Lock()

        self._latest_frame: Optional[np.ndarray] = None
        self._last_frame_time: float = 0.0
        self._consecutive_errors: int = 0
        self._max_consecutive_errors: int = 30

        self.actual_width = 0
        self.actual_height = 0
        self.actual_fps = 0.0

    def start(self) -> bool:
        """Initialize camera device and launch background acquisition thread."""
        with self._lock:
            if self._running:
                return True

            logger.info(f"Opening camera index {self.device_index} with {self.api_preference} backend...")
            backend = cv2.CAP_DSHOW if self.api_preference == "DSHOW" else cv2.CAP_ANY
            self._cap = cv2.VideoCapture(self.device_index, backend)

            if not self._cap.isOpened():
                logger.error(f"Failed to open camera device index {self.device_index}")
                return False

            # Set camera properties
            self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.target_width)
            self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.target_height)
            self._cap.set(cv2.CAP_PROP_FPS, self.target_fps)
            self._cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

            self.actual_width = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            self.actual_height = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            self.actual_fps = self._cap.get(cv2.CAP_PROP_FPS) or float(self.target_fps)

            logger.info(f"Camera opened successfully: {self.actual_width}x{self.actual_height} @ {self.actual_fps:.1f} FPS")

            self._running = True
            self._consecutive_errors = 0
            self._thread = threading.Thread(target=self._capture_worker, name="WebcamWorker", daemon=True)
            self._thread.start()
            return True

    def _capture_worker(self):
        """Worker loop that continuously grabs latest frame."""
        while self._running and self._cap is not None:
            ret, frame = self._cap.read()
            if not ret or frame is None:
                self._consecutive_errors += 1
                if self._consecutive_errors >= self._max_consecutive_errors:
                    logger.warning(f"Excessive camera read failures ({self._consecutive_errors}). Attempting reconnect...")
                    self._reconnect()
                time.sleep(0.01)
                continue

            self._consecutive_errors = 0

            # Horizontal mirroring if enabled
            if self.mirror_horizontal:
                frame = cv2.flip(frame, 1)

            with self._lock:
                self._latest_frame = frame
                self._last_frame_time = time.perf_counter()

    def _reconnect(self):
        """Internal recovery when camera drops connection."""
        if self._cap:
            try:
                self._cap.release()
            except Exception:
                pass
        time.sleep(0.5)
        backend = cv2.CAP_DSHOW if self.api_preference == "DSHOW" else cv2.CAP_ANY
        self._cap = cv2.VideoCapture(self.device_index, backend)
        if self._cap.isOpened():
            self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.target_width)
            self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.target_height)
            self._cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            self._consecutive_errors = 0
            logger.info("Camera reconnected successfully.")

    def read_latest(self) -> Tuple[bool, Optional[np.ndarray], float]:
        """
        Returns (success, latest_frame_copy, timestamp).
        Non-blocking read from the single-frame buffer.
        """
        with self._lock:
            if not self._running or self._latest_frame is None:
                return False, None, 0.0
            return True, self._latest_frame.copy(), self._last_frame_time

    def stop(self):
        """Stop worker thread and release hardware capture device."""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        with self._lock:
            if self._cap:
                self._cap.release()
                self._cap = None
            self._latest_frame = None
        logger.info("Webcam stopped and released.")

    @property
    def is_running(self) -> bool:
        return self._running and self._cap is not None and self._cap.isOpened()

    @staticmethod
    def list_available_cameras(max_tested: int = 4) -> List[int]:
        """Probes camera indices to find active devices."""
        available = []
        for i in range(max_tested):
            cap = cv2.VideoCapture(i, cv2.CAP_DSHOW)
            if cap.isOpened():
                available.append(i)
                cap.release()
        return available

