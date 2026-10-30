"""
Safety, Watchdog, and Game Process Monitoring for GESTUREDRIVE X.
Protects against tracking drops, frozen camera frames, accidental input retention,
and provides emergency shutdown controls.
"""

import time
import threading
from typing import Optional, List, Tuple
import psutil

from src.controller.virtual_xbox import VirtualXboxController
from src.utils.logger import logger


class SafetyWatchdog:
    """Monitors system health and resets controls if tracking or camera fails."""

    def __init__(
        self,
        controller: VirtualXboxController,
        tracking_loss_timeout_s: float = 0.25,
        camera_timeout_s: float = 1.0,
        game_processes: Optional[List[str]] = None
    ):
        self.controller = controller
        self.tracking_loss_timeout_s = tracking_loss_timeout_s
        self.camera_timeout_s = camera_timeout_s
        self.game_processes = game_processes or [
            "NeedForSpeedHeat.exe",
            "NFSHeat.exe",
            "NFS19.exe",
            "NeedForSpeedHeatTrial.exe"
        ]

        self._emergency_stop = False
        self._last_valid_tracking_time = time.perf_counter()
        self._last_camera_frame_time = time.perf_counter()
        self._tracking_lost = False
        self._camera_frozen = False

        # Process monitor state
        self._is_game_running = False
        self._game_pid: Optional[int] = None
        self._last_proc_check_time = 0.0
        self._proc_check_interval = 2.0

        self._lock = threading.Lock()

    @property
    def emergency_stop(self) -> bool:
        return self._emergency_stop

    def set_emergency_stop(self, stop: bool):
        """Engage or disengage emergency stop."""
        with self._lock:
            self._emergency_stop = stop
            if stop:
                logger.warning("EMERGENCY STOP ENGAGED! Controller outputs severed.")
                self.controller.reset_to_neutral()
            else:
                logger.info("Emergency stop disengaged. Control restored.")

    def record_hand_detection(self):
        """Called whenever at least one hand is successfully detected."""
        self._last_valid_tracking_time = time.perf_counter()
        if self._tracking_lost:
            self._tracking_lost = False
            logger.info("Hand tracking restored.")

    def record_camera_frame(self, frame_timestamp: float):
        """Called whenever a fresh frame is acquired from the camera."""
        self._last_camera_frame_time = time.perf_counter()
        if self._camera_frozen:
            self._camera_frozen = False
            logger.info("Webcam frame stream resumed.")

    def evaluate_safety(self) -> Tuple[bool, bool]:
        """
        Evaluates timeouts. If tracking is lost or camera freezes, resets controller to neutral.
        Returns (tracking_lost, camera_frozen).
        """
        now = time.perf_counter()

        # Check tracking loss timeout
        if (now - self._last_valid_tracking_time) > self.tracking_loss_timeout_s:
            if not self._tracking_lost:
                self._tracking_lost = True
                logger.warning(
                    f"Hand tracking lost for > {int(self.tracking_loss_timeout_s * 1000)}ms. Auto-neutral triggered."
                )
            self.controller.reset_to_neutral()

        # Check camera freeze timeout
        if (now - self._last_camera_frame_time) > self.camera_timeout_s:
            if not self._camera_frozen:
                self._camera_frozen = True
                logger.error("Webcam frame feed frozen! Auto-neutral triggered.")
            self.controller.reset_to_neutral()

        return self._tracking_lost, self._camera_frozen

    def check_nfs_heat_process(self) -> Tuple[bool, Optional[int]]:
        """Checks if Need for Speed Heat process is currently active."""
        now = time.perf_counter()
        if (now - self._last_proc_check_time) < self._proc_check_interval:
            return self._is_game_running, self._game_pid

        self._last_proc_check_time = now
        found = False
        pid = None

        try:
            for proc in psutil.process_iter(['pid', 'name']):
                name = proc.info.get('name')
                if name and any(target.lower() == name.lower() for target in self.game_processes):
                    found = True
                    pid = proc.info.get('pid')
                    break
        except Exception:
            pass

        self._is_game_running = found
        self._game_pid = pid
        return found, pid

