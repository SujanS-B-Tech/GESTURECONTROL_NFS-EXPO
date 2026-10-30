"""
Calibration engine for GESTUREDRIVE X.
Guides user through natural hand positioning, computes custom neutral angle,
left/right steering limits, and stores calibration profiles.
"""

from dataclasses import dataclass, asdict
import json
import os
import time
from typing import List, Optional
import numpy as np

from src.utils.logger import logger


@dataclass
class CalibrationProfile:
    """Stores calibrated user profile."""
    neutral_angle: float = 0.0
    deadzone_angle: float = 3.0
    max_left_angle: float = 42.0
    max_right_angle: float = 42.0
    fist_curl_threshold: float = 0.65
    open_palm_extension_threshold: float = 0.70
    calibrated_at: str = ""
    is_calibrated: bool = False


class CalibrationManager:
    """Manages recording, computing, and persisting user calibration settings."""

    DEFAULT_CALIBRATION_FILE = "config/calibration.json"

    def __init__(self, config_path: str = DEFAULT_CALIBRATION_FILE):
        if not os.path.isabs(config_path):
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            self.config_path = os.path.join(base_dir, config_path)
        else:
            self.config_path = config_path

        self.profile = self.load_profile()
        self._samples: List[float] = []

    def start_recording(self):
        """Clears current sample buffer to begin a new calibration step."""
        self._samples.clear()

    def record_sample(self, value: float):
        """Appends a new sample to the active calibration buffer."""
        self._samples.append(value)

    def compute_average(self) -> float:
        """Returns the mean of recorded samples, or 0.0 if empty."""
        if not self._samples:
            return 0.0
        return float(np.mean(self._samples))

    def compute_robust_angle(self) -> float:
        """Returns median of samples to reject outliers."""
        if not self._samples:
            return 0.0
        return float(np.median(self._samples))

    def save_profile(self) -> bool:
        """Persists current calibration profile to disk."""
        try:
            os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
            self.profile.calibrated_at = time.strftime("%Y-%m-%d %H:%M:%S")
            self.profile.is_calibrated = True

            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(asdict(self.profile), f, indent=2)
            logger.info(f"Calibration profile saved successfully to {self.config_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to save calibration profile: {e}")
            return False

    def load_profile(self) -> CalibrationProfile:
        """Loads calibration profile from disk or returns defaults."""
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                logger.info(f"Loaded existing calibration profile from {self.config_path}")
                return CalibrationProfile(**data)
            except Exception as e:
                logger.warning(f"Could not parse calibration profile, using defaults: {e}")

        return CalibrationProfile()

