"""
Unit tests for Virtual Steering Wheel calculation.
"""

import pytest
import numpy as np

from src.gestures.steering import VirtualSteeringWheel
from src.camera.hand_tracker import HandData, FrameHandResult


def make_dummy_hand(label: str, wrist_x: int, wrist_y: int, mid_x: int, mid_y: int) -> HandData:
    """Creates a mock HandData object for deterministic steering testing."""
    pixel_landmarks = np.zeros((21, 2), dtype=np.int32)
    landmarks = np.zeros((21, 3), dtype=np.float32)

    # Index 0: Wrist
    pixel_landmarks[0] = [wrist_x, wrist_y]
    landmarks[0] = [wrist_x / 1280.0, wrist_y / 720.0, 0.0]

    # Index 9: Middle MCP
    pixel_landmarks[9] = [mid_x, mid_y]
    landmarks[9] = [mid_x / 1280.0, mid_y / 720.0, 0.0]

    return HandData(
        handedness=label,
        landmarks=landmarks,
        pixel_landmarks=pixel_landmarks,
        confidence=0.95,
        bbox=(min(wrist_x, mid_x), min(wrist_y, mid_y), 50, 50),
        wrist_px=(wrist_x, wrist_y),
        index_tip_px=(mid_x, mid_y - 20),
        thumb_tip_px=(mid_x - 20, mid_y)
    )


def test_steering_neutral_deadzone():
    wheel = VirtualSteeringWheel(neutral_angle=0.0, deadzone_angle=3.0, max_angle=40.0)

    # Perfectly level hands (Y = 360 for both)
    left = make_dummy_hand("Left", 400, 360, 400, 360)
    right = make_dummy_hand("Right", 880, 360, 880, 360)
    result = FrameHandResult(left_hand=left, right_hand=right)

    state = wheel.update(result)
    assert abs(state.relative_angle_deg) < 0.1
    assert state.xbox_stick_x == 0
    assert state.normalized_value == 0.0


def test_steering_left_turn():
    wheel = VirtualSteeringWheel(neutral_angle=0.0, deadzone_angle=2.0, max_angle=40.0, smoothing_factor=1.0)

    # Left turn: Left hand is lower (Y = 460), Right hand is higher (Y = 260) -> dy = -200 < 0
    left = make_dummy_hand("Left", 400, 460, 400, 460)
    right = make_dummy_hand("Right", 880, 260, 880, 260)
    result = FrameHandResult(left_hand=left, right_hand=right)

    state = wheel.update(result)
    assert state.relative_angle_deg < -15.0
    assert state.normalized_value < -0.3
    assert state.xbox_stick_x < -10000


def test_steering_right_turn():
    wheel = VirtualSteeringWheel(neutral_angle=0.0, deadzone_angle=2.0, max_angle=40.0, smoothing_factor=1.0)

    # Right turn: Right hand is lower (Y = 460), Left hand is higher (Y = 260) -> dy = +200 > 0
    left = make_dummy_hand("Left", 400, 260, 400, 260)
    right = make_dummy_hand("Right", 880, 460, 880, 460)
    result = FrameHandResult(left_hand=left, right_hand=right)

    state = wheel.update(result)
    assert state.relative_angle_deg > 15.0
    assert state.normalized_value > 0.3
    assert state.xbox_stick_x > 10000


def test_steering_hands_lost_returns_to_center():
    wheel = VirtualSteeringWheel(neutral_angle=0.0, deadzone_angle=2.0, max_angle=40.0, smoothing_factor=1.0, center_decay_rate=0.5)

    # Turn right first
    left = make_dummy_hand("Left", 400, 260, 400, 260)
    right = make_dummy_hand("Right", 880, 460, 880, 460)
    wheel.update(FrameHandResult(left_hand=left, right_hand=right))

    # Now hands disappear
    lost_result = FrameHandResult(left_hand=None, right_hand=None)
    for _ in range(10):
        state = wheel.update(lost_result)

    assert abs(state.normalized_value) < 0.05
    assert abs(state.xbox_stick_x) < 1500

