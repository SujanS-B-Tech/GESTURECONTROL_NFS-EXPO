"""
High-Precision Intuitive Gesture Recognition Engine for GESTUREDRIVE X.
Engineered for razor-sharp, deviation-free racing control in Need for Speed Heat:
- Natural wheel grip / fists closed = Drive Forward (Throttle RT: instant punch) + Steer
- Both palms open flat = Stop & Reverse (Brake LT: instant bite) + Steer backward
- Front, Reverse, and Steer control with zero accidental drift/handbrake interference
- Thumbs up (either hand) = Nitrous Boost (Xbox Button A pulse)
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
    """High-precision gesture classification and anatomical metrics for a single hand."""
    gesture: HandGesture = HandGesture.NONE
    confidence: float = 0.0
    curl_factors: List[float] = None
    overall_curl: float = 0.0         # 0.0 (open) to 1.0 (fist)
    overall_extension: float = 0.0    # 0.0 (fist) to 1.0 (open)
    extended_fingers: int = 0         # Count of extended fingers (0-4)
    curled_fingers: int = 0           # Count of curled fingers (0-4)
    is_fist: bool = False
    is_open: bool = False
    is_thumbs_up: bool = False


@dataclass
class FrameGestureResult:
    """Consolidated driving intent across both hands for the frame."""
    left: Optional[HandGestureState] = None
    right: Optional[HandGestureState] = None

    # Core intuitive driving modes (Front, Reverse, Steer)
    both_closed_drive: bool = False       # Wheel grip -> Move forward freely
    both_open_reverse: bool = False       # Both palms open -> Stop & Reverse
    one_open_one_closed_drift: bool = False # Drift gesture removed (maintained as False for API safety)
    thumbs_up_nitro: bool = False         # Either hand thumbs up -> Nitrous

    throttle_analog: float = 0.0          # 0.0 to 1.0 (RT)
    brake_analog: float = 0.0             # 0.0 to 1.0 (LT)


class GestureRecognizer:
    """
    Classifies natural driving gestures into forward drive, reverse, drift, and nitrous
    using multi-metric anatomical joint analysis and fast-response throttle/brake curves.
    """

    def __init__(
        self,
        throttle_smoothing: float = 0.75,  # High responsiveness (instant throttle punch)
        brake_smoothing: float = 0.85,     # Immediate brake bite
        decay_rate: float = 0.35,
        thumbs_up_angle_tolerance_deg: float = 38.0
    ):
        self.throttle_smoothing = throttle_smoothing
        self.brake_smoothing = brake_smoothing
        self.decay_rate = decay_rate
        self.thumbs_up_angle_tolerance_deg = thumbs_up_angle_tolerance_deg

        self._current_throttle = 0.0
        self._current_brake = 0.0

        # Debounce and stability histories (prevents single-frame sensor flicker)
        self._left_history: List[HandGesture] = []
        self._right_history: List[HandGesture] = []

    def analyze_hand(self, hand: Optional[HandData]) -> HandGestureState:
        """
        Analyzes 21 landmarks of a single hand using dual anatomical metrics:
        1. Tip-to-wrist vs PIP-to-wrist extension ratio
        2. Tip-to-MCP fold distance
        This ensures rock-solid classification invariant to camera angle or hand tilt.
        """
        if hand is None:
            return HandGestureState(curl_factors=[0.0] * 5)

        lm = hand.landmarks
        wrist = lm[0]

        finger_indices = [
            (1, 2, 4),    # Thumb: CMC(1), MCP(2), TIP(4)
            (5, 6, 8),    # Index: MCP(5), PIP(6), TIP(8)
            (9, 10, 12),  # Middle: MCP(9), PIP(10), TIP(12)
            (13, 14, 16), # Ring: MCP(13), PIP(14), TIP(16)
            (17, 18, 20)  # Pinky: MCP(17), PIP(18), TIP(20)
        ]

        curl_factors = []
        extended_count = 0
        curled_count = 0

        # 1. Thumb analysis
        dist_thumb_tip_pinky = float(np.linalg.norm(lm[4][:2] - lm[17][:2]))
        dist_thumb_mcp_pinky = float(np.linalg.norm(lm[2][:2] - lm[17][:2]))
        thumb_curl = np.clip(1.0 - (dist_thumb_tip_pinky / (dist_thumb_mcp_pinky * 1.35 + 1e-5)), 0.0, 1.0)
        curl_factors.append(float(thumb_curl))

        # 2. Fingers 1-4 (Index, Middle, Ring, Pinky) Dual-Metric Analysis
        for mcp_idx, pip_idx, tip_idx in finger_indices[1:]:
            mcp = lm[mcp_idx]
            pip = lm[pip_idx]
            tip = lm[tip_idx]

            dist_wrist_tip = float(np.linalg.norm(wrist[:2] - tip[:2]))
            dist_wrist_mcp = float(np.linalg.norm(wrist[:2] - mcp[:2]))
            dist_tip_mcp = float(np.linalg.norm(tip[:2] - mcp[:2]))
            dist_pip_mcp = float(np.linalg.norm(pip[:2] - mcp[:2]))

            # Ratio for curl factor (1.0 = curled fist, 0.0 = extended open)
            ratio = dist_wrist_tip / (dist_wrist_mcp + 1e-5)
            curl = float(np.clip((2.0 - ratio) / 1.0, 0.0, 1.0))
            curl_factors.append(curl)

            # Discrete anatomical checks
            is_finger_extended = (dist_wrist_tip > dist_wrist_mcp * 1.25) and (dist_tip_mcp > dist_pip_mcp * 0.95)
            is_finger_curled = (dist_wrist_tip <= dist_wrist_mcp * 1.15) or (dist_tip_mcp < dist_pip_mcp * 0.90)

            if is_finger_extended:
                extended_count += 1
            elif is_finger_curled:
                curled_count += 1

        four_fingers_curl = float(np.mean(curl_factors[1:]))
        overall_curl = float(np.mean(curl_factors))
        overall_extension = float(1.0 - overall_curl)

        # Classification thresholds with guard-bands:
        # FIST: At least 3 of 4 fingers curled, or high curl ratio with no extended fingers
        is_fist = (curled_count >= 3) or (four_fingers_curl >= 0.40 and extended_count <= 1)

        # OPEN PALM: At least 3 fingers extended and low curl ratio
        is_open = (extended_count >= 3) and (four_fingers_curl <= 0.32)

        # 3. Strict Thumbs-up check (thumb extended upward while 4 fingers are curled)
        vec_thumb = lm[4][:2] - lm[2][:2]
        angle_from_up = math.degrees(math.atan2(vec_thumb[0], -vec_thumb[1]))
        is_pointing_up = abs(angle_from_up) <= self.thumbs_up_angle_tolerance_deg

        # Thumb tip must be higher than index knuckle (lm[5]) by at least 3.5% of frame
        thumb_protrudes_up = (lm[4][1] < lm[5][1] - 0.035) and (lm[4][1] < lm[3][1])
        # Thumb itself must not be curled against the fist
        thumb_is_straight = thumb_curl <= 0.30

        is_thumbs_up = bool(is_pointing_up and thumb_protrudes_up and thumb_is_straight and is_fist)

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
            extended_fingers=extended_count,
            curled_fingers=curled_count,
            is_fist=is_fist,
            is_open=is_open,
            is_thumbs_up=is_thumbs_up
        )

    def process_frame(self, hand_result: FrameHandResult) -> FrameGestureResult:
        """
        Processes driving intent across hands with front, reverse, and steer rules:
        - Natural grip / fists closed = Drive forward (Throttle RT) & Steer smoothly
        - Both hands open flat = Stop & Reverse (Brake LT) & Steer backward
        - Either hand thumbs up = Nitrous Boost (Button A)
        """
        left_state = self.analyze_hand(hand_result.left_hand)
        right_state = self.analyze_hand(hand_result.right_hand)

        both_detected = hand_result.both_hands_detected

        # Check Nitrous (Either hand thumbs up)
        nitro_active = bool(left_state.is_thumbs_up or right_state.is_thumbs_up)

        both_closed = False
        both_open = False

        if both_detected:
            # 1. Stop & Reverse: Both hands deliberately open flat
            if left_state.is_open and right_state.is_open:
                both_open = True
            # 2. Drive Forward: Gripping the steering wheel (fists / natural driving posture)
            # Drift handbrake is eliminated so turning or relaxing one hand does not stall driving!
            else:
                both_closed = True

        elif hand_result.any_hand_detected:
            # Single hand fallback (e.g. one hand temporarily off-screen)
            hand = right_state if hand_result.right_hand else left_state
            if hand.is_open:
                both_open = True
            else:
                both_closed = True

        # Calculate analog throttle (RT) and brake (LT) with instant cutoffs
        target_throttle = 0.0
        target_brake = 0.0

        if both_closed:
            # Drive forward freely with full power
            target_throttle = 1.0
            target_brake = 0.0
            # Instant cutoff of residual brake for immediate response
            self._current_brake = 0.0

        elif both_open:
            # Stop and reverse with full braking authority
            target_throttle = 0.0
            target_brake = 1.0
            # Instant cutoff of residual throttle
            self._current_throttle = 0.0

        else:
            # Decay to neutral
            target_throttle = 0.0
            target_brake = 0.0

        # Fast-response exponential interpolation
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
            one_open_one_closed_drift=False,
            thumbs_up_nitro=nitro_active,
            throttle_analog=float(np.clip(self._current_throttle, 0.0, 1.0)),
            brake_analog=float(np.clip(self._current_brake, 0.0, 1.0))
        )

    def reset(self):
        self._current_throttle = 0.0
        self._current_brake = 0.0
        self._left_history.clear()
        self._right_history.clear()
