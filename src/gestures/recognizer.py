"""
Intuitive Gesture Recognition Engine for GESTUREDRIVE X.
Customized for natural arcade steering dynamics:
- Both hands closed / gripped = Drive forward (Throttle RT) + Steer
- Both palms open = Stop and Reverse (Brake LT) + Steer backward
- One hand closed, one hand open = Drift Handbrake (Button X) + Steer
- Thumbs up (either hand) = Nitrous Boost (Button A)
"""

from dataclasses import dataclass
from enum import Enum
import math
from typing import Dict, List, Optional, Tuple
import numpy as np

from src.camera.hand_tracker import HandData, FrameHandResult
from src.utils.logger import logger


class HandGesture(Enum):
    NONE = "none"
    OPEN_PALM = "open_palm"
    CLOSED_FIST = "closed_fist"
    THUMBS_UP = "thumbs_up"
    TWO_FINGERS_V = "two_fingers_v"


@dataclass
class HandGestureState:
    """Gesture classification and metrics for a single hand."""
    gesture: HandGesture = HandGesture.NONE
    confidence: float = 0.0
    curl_factors: List[float] = None
    overall_curl: float = 0.0         # 0.0 (open) to 1.0 (fist)
    overall_extension: float = 0.0    # 0.0 (fist) to 1.0 (open)
    is_fist: bool = False
    is_open: bool = False
    is_thumbs_up: bool = False


@dataclass
class FrameGestureResult:
    """Consolidated driving intent across both hands for the frame."""
    left: Optional[HandGestureState] = None
    right: Optional[HandGestureState] = None

    # Core intuitive driving modes
    both_closed_drive: bool = False       # Both hands gripped -> Move forward freely
    both_open_reverse: bool = False       # Both palms open -> Stop & Reverse
    one_open_one_closed_drift: bool = False # One closed, one open -> Drift Handbrake
    thumbs_up_nitro: bool = False         # Either hand thumbs up -> Nitrous

    throttle_analog: float = 0.0          # 0.0 to 1.0 (RT)
    brake_analog: float = 0.0             # 0.0 to 1.0 (LT)


class GestureRecognizer:
    """Classifies natural driving gestures into forward drive, reverse, drift, and nitrous."""

    def __init__(
        self,
        throttle_smoothing: float = 0.35,
        brake_smoothing: float = 0.40,
        decay_rate: float = 0.25,
        thumbs_up_angle_tolerance_deg: float = 40.0
    ):
        self.throttle_smoothing = throttle_smoothing
        self.brake_smoothing = brake_smoothing
        self.decay_rate = decay_rate
        self.thumbs_up_angle_tolerance_deg = thumbs_up_angle_tolerance_deg

        self._current_throttle = 0.0
        self._current_brake = 0.0

    def analyze_hand(self, hand: Optional[HandData]) -> HandGestureState:
        """Analyzes 21 landmarks of a single hand."""
        if hand is None:
            return HandGestureState(curl_factors=[0.0] * 5)

        lm = hand.landmarks
        wrist = lm[0]

        finger_indices = [
            (1, 2, 4),   # Thumb
            (5, 6, 8),   # Index
            (9, 10, 12), # Middle
            (13, 14, 16),# Ring
            (17, 18, 20) # Pinky
        ]

        curl_factors = []

        # 1. Thumb curl calculation
        dist_thumb_tip_pinky = np.linalg.norm(lm[4][:2] - lm[17][:2])
        dist_thumb_mcp_pinky = np.linalg.norm(lm[2][:2] - lm[17][:2])
        thumb_curl = np.clip(1.0 - (dist_thumb_tip_pinky / (dist_thumb_mcp_pinky * 1.4 + 1e-5)), 0.0, 1.0)
        curl_factors.append(float(thumb_curl))

        # 2. Fingers 1-4 curl calculations
        for mcp_idx, pip_idx, tip_idx in finger_indices[1:]:
            mcp = lm[mcp_idx]
            tip = lm[tip_idx]
            dist_wrist_tip = np.linalg.norm(wrist[:2] - tip[:2])
            dist_wrist_mcp = np.linalg.norm(wrist[:2] - mcp[:2])

            ratio = dist_wrist_tip / (dist_wrist_mcp + 1e-5)
            curl = np.clip((2.0 - ratio) / 1.0, 0.0, 1.0)
            curl_factors.append(float(curl))

        four_fingers_curl = float(np.mean(curl_factors[1:]))
        overall_curl = float(np.mean(curl_factors))
        overall_extension = float(1.0 - overall_curl)

        is_fist = four_fingers_curl >= 0.48
        is_open = four_fingers_curl <= 0.35 and thumb_curl <= 0.40

        # 3. Thumbs-up check
        vec_thumb = lm[4][:2] - lm[2][:2]
        angle_from_up = math.degrees(math.atan2(vec_thumb[0], -vec_thumb[1]))
        is_pointing_up = abs(angle_from_up) <= self.thumbs_up_angle_tolerance_deg
        is_thumbs_up = bool(is_pointing_up and (four_fingers_curl >= 0.42) and (lm[4][1] < lm[3][1] < lm[2][1]))

        if is_thumbs_up:
            gesture = HandGesture.THUMBS_UP
        elif is_fist:
            gesture = HandGesture.CLOSED_FIST
        elif is_open:
            gesture = HandGesture.OPEN_PALM
        else:
            gesture = HandGesture.NONE

        return HandGestureState(
            gesture=gesture,
            confidence=hand.confidence,
            curl_factors=curl_factors,
            overall_curl=overall_curl,
            overall_extension=overall_extension,
            is_fist=is_fist,
            is_open=is_open,
            is_thumbs_up=is_thumbs_up
        )

    def process_frame(self, hand_result: FrameHandResult) -> FrameGestureResult:
        """
        Processes driving intent across hands:
        - Both closed = Drive forward
        - Both open = Stop and Reverse
        - One open, one closed = Drift Handbrake
        - Either thumbs up = Nitrous
        """
        left_state = self.analyze_hand(hand_result.left_hand)
        right_state = self.analyze_hand(hand_result.right_hand)

        both_detected = hand_result.both_hands_detected

        # Check Nitrous (Either hand thumbs up)
        nitro_active = bool(left_state.is_thumbs_up or right_state.is_thumbs_up)

        both_closed = False
        both_open = False
        one_open_one_closed = False

        if both_detected:
            # Check for Nitrous with one hand driving
            left_gripped = left_state.is_fist or left_state.is_thumbs_up
            right_gripped = right_state.is_fist or right_state.is_thumbs_up

            # 1. Drift Handbrake: Exactly one hand closed and the other hand open
            if (left_state.is_fist and right_state.is_open) or (right_state.is_fist and left_state.is_open):
                one_open_one_closed = True

            # 2. Drive Forward: Both hands closed (or one fist + one thumbs up nitro)
            elif (left_state.is_fist and right_state.is_fist) or (nitro_active and (left_gripped and right_gripped)):
                both_closed = True

            # 3. Stop & Reverse: Both palms open
            elif left_state.is_open and right_state.is_open:
                both_open = True

            # If hands are resting/steering naturally without full open palm, default to cruising forward
            elif not one_open_one_closed and not both_open:
                both_closed = True
        elif hand_result.any_hand_detected:
            # Single hand visible: if gripped drive, if open brake
            hand = right_state if hand_result.right_hand else left_state
            if hand.is_open:
                both_open = True
            elif hand.is_fist or hand.is_thumbs_up:
                both_closed = True

        # Calculate analog throttle (RT) and brake (LT)
        target_throttle = 0.0
        target_brake = 0.0

        if both_closed:
            # Drive forward freely
            target_throttle = 1.0
            target_brake = 0.0
        elif both_open:
            # Stop and reverse
            target_throttle = 0.0
            target_brake = 1.0
        elif one_open_one_closed:
            # Drift: maintain power through slide
            target_throttle = 0.65
            target_brake = 0.0
        else:
            # Decay to neutral
            target_throttle = 0.0
            target_brake = 0.0

        # Apply smooth interpolation
        self._current_throttle = (
            self.throttle_smoothing * target_throttle +
            (1.0 - self.throttle_smoothing) * self._current_throttle
        )
        self._current_brake = (
            self.brake_smoothing * target_brake +
            (1.0 - self.brake_smoothing) * self._current_brake
        )

        return FrameGestureResult(
            left=left_state,
            right=right_state,
            both_closed_drive=both_closed,
            both_open_reverse=both_open,
            one_open_one_closed_drift=one_open_one_closed,
            thumbs_up_nitro=nitro_active,
            throttle_analog=float(np.clip(self._current_throttle, 0.0, 1.0)),
            brake_analog=float(np.clip(self._current_brake, 0.0, 1.0))
        )

    def reset(self):
        self._current_throttle = 0.0
        self._current_brake = 0.0
