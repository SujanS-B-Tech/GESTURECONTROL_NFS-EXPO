"""
Realistic Two-Hand Virtual Steering Wheel Engine for GESTUREDRIVE X.
Calculates tilt angle between hands, applies deadzone, exponential/cubic response curves,
smooth interpolation, and maps to Xbox Left Stick X (-32768 to 32767).
"""

import math
from dataclasses import dataclass
from typing import Optional, Tuple
import numpy as np

from src.camera.hand_tracker import HandData, FrameHandResult
from src.utils.logger import logger


@dataclass
class SteeringState:
    """Current state of the virtual steering wheel."""
    active: bool = False
    raw_angle_deg: float = 0.0
    relative_angle_deg: float = 0.0
    normalized_value: float = 0.0  # -1.0 (full left) to +1.0 (full right)
    xbox_stick_x: int = 0          # -32768 to 32767
    center_px: Tuple[int, int] = (0, 0)
    left_hand_px: Tuple[int, int] = (0, 0)
    right_hand_px: Tuple[int, int] = (0, 0)
    hands_distance_px: float = 0.0


class VirtualSteeringWheel:
    """
    Simulates a physical steering wheel held at 9 o'clock (left) and 3 o'clock (right).
    Computes rotation angle, deadzone compensation, non-linear curves, and decay to center.
    """

    def __init__(
        self,
        neutral_angle: float = 0.0,
        deadzone_angle: float = 1.0,
        max_angle: float = 14.0,
        sensitivity: float = 1.40,
        smoothing_factor: float = 0.92,
        response_curve: str = "progressive_sharp",
        invert: bool = False,
        center_decay_rate: float = 0.35
    ):
        self.neutral_angle = neutral_angle
        self.deadzone_angle = deadzone_angle
        self.max_angle = max_angle
        self.sensitivity = sensitivity
        self.smoothing_factor = smoothing_factor  # 0.0 = freeze, 1.0 = instant (0.92 = sub-16ms snappy response)
        self.response_curve = response_curve
        self.invert = invert
        self.center_decay_rate = center_decay_rate

        self._current_normalized = 0.0
        self._last_valid_state = SteeringState()

    def set_neutral_now(self, current_raw_angle: float):
        """Quickly recalibrates the center neutral position to the current hand angle."""
        self.neutral_angle = current_raw_angle
        logger.info(f"Steering neutral calibrated to {self.neutral_angle:+.2f}°")

    def update(self, hand_result: FrameHandResult) -> SteeringState:
        """
        Process current frame hand result and compute updated steering state.
        If both hands are visible, computes wheel rotation.
        If hands are lost or only one hand is visible, smoothly decays steering to center (0.0).
        """
        if not hand_result.both_hands_detected:
            # Smoothly return to center
            if abs(self._current_normalized) > 0.01:
                self._current_normalized *= (1.0 - self.center_decay_rate)
            else:
                self._current_normalized = 0.0

            xbox_val = int(self._current_normalized * 32767)
            state = SteeringState(
                active=False,
                raw_angle_deg=0.0,
                relative_angle_deg=0.0,
                normalized_value=self._current_normalized,
                xbox_stick_x=np.clip(xbox_val, -32768, 32767)
            )
            self._last_valid_state = state
            return state

        left = hand_result.left_hand
        right = hand_result.right_hand

        # Compute stable fist/palm centroid: average of Wrist (0) and Knuckles (5, 9, 13, 17)
        # This centroid stays completely rock-solid when fingers are clenched into a fist!
        palm_indices = [0, 5, 9, 13, 17]
        p_left_x = float(np.mean(left.pixel_landmarks[palm_indices, 0]))
        p_left_y = float(np.mean(left.pixel_landmarks[palm_indices, 1]))

        p_right_x = float(np.mean(right.pixel_landmarks[palm_indices, 0]))
        p_right_y = float(np.mean(right.pixel_landmarks[palm_indices, 1]))

        dx = p_right_x - p_left_x
        dy = p_right_y - p_left_y

        dist = math.hypot(dx, dy)
        center_x = int((p_left_x + p_right_x) / 2)
        center_y = int((p_left_y + p_right_y) / 2)

        # Minimum physical distance between hands to prevent crossed hands
        if dist < 50:
            return self._last_valid_state

        # Calculate angle in degrees:
        # Note: image Y is positive downwards!
        # When steering Left: Left hand moves down (Y increases) or Right hand moves up (Y decreases) -> dy < 0
        # When steering Right: Right hand moves down (Y increases) or Left hand moves up (Y decreases) -> dy > 0
        raw_angle = math.degrees(math.atan2(dy, dx))

        # Relative angle subtracting calibrated neutral
        rel_angle = raw_angle - self.neutral_angle

        # Deadzone handling
        effective_angle = 0.0
        abs_rel = abs(rel_angle)
        if abs_rel > self.deadzone_angle:
            effective_angle = math.copysign(abs_rel - self.deadzone_angle, rel_angle)

        # Normalize to [-1.0, 1.0]
        usable_range = max(self.max_angle - self.deadzone_angle, 5.0)
        target_norm = np.clip(effective_angle / usable_range, -1.0, 1.0)

        # Apply response curves
        if self.response_curve in ["progressive_sharp", "precision", "progressive"]:
            # 85% linear + 15% quadratic: instant bite with steady center stability
            sign = math.copysign(1.0, target_norm)
            target_norm = sign * (0.85 * abs(target_norm) + 0.15 * (abs(target_norm) ** 2))
        elif self.response_curve == "linear":
            pass  # Direct 1:1 linear steering
        elif self.response_curve == "cubic":
            target_norm = 0.5 * (target_norm ** 3) + 0.5 * target_norm
        elif self.response_curve == "exponential":
            sign = math.copysign(1.0, target_norm)
            target_norm = sign * (abs(target_norm) ** 1.3)

        # Apply sensitivity multiplier
        target_norm = np.clip(target_norm * self.sensitivity, -1.0, 1.0)

        if self.invert:
            target_norm = -target_norm

        # Smooth interpolation (EMA) to eliminate hand jitter
        self._current_normalized = (
            self.smoothing_factor * target_norm +
            (1.0 - self.smoothing_factor) * self._current_normalized
        )

        xbox_val = int(np.clip(self._current_normalized * 32767, -32768, 32767))

        state = SteeringState(
            active=True,
            raw_angle_deg=raw_angle,
            relative_angle_deg=rel_angle,
            normalized_value=self._current_normalized,
            xbox_stick_x=xbox_val,
            center_px=(center_x, center_y),
            left_hand_px=(int(p_left_x), int(p_left_y)),
            right_hand_px=(int(p_right_x), int(p_right_y)),
            hands_distance_px=dist
        )
        self._last_valid_state = state
        return state

    def reset(self):
        """Reset steering wheel state to dead center."""
        self._current_normalized = 0.0
        self._last_valid_state = SteeringState()

