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

    # Set palm centroid indices [0, 5, 9, 13, 17] uniformly around (mid_x, mid_y)
    for idx in [0, 5, 9, 13, 17]:
        pixel_landmarks[idx] = [mid_x, mid_y]
        landmarks[idx] = [mid_x / 1280.0, mid_y / 720.0, 0.0]

    pixel_landmarks[0] = [wrist_x, wrist_y]
    landmarks[0] = [wrist_x / 1280.0, wrist_y / 720.0, 0.0]

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


def test_fist_steering_precision():
    """Verify that closed fists at steering wheel position produce accurate analog turn angles."""
    wheel = VirtualSteeringWheel(neutral_angle=0.0, deadzone_angle=2.5, max_angle=35.0, smoothing_factor=1.0)

    # Left fist tilted down (Left turn by ~25 degrees)
    left_fist = make_dummy_hand("Left", 400, 430, 400, 430)
    right_fist = make_dummy_hand("Right", 880, 290, 880, 290)
    res = wheel.update(FrameHandResult(left_hand=left_fist, right_hand=right_fist))

    assert res.active is True
    assert res.relative_angle_deg < -10.0
    assert res.xbox_stick_x < -6000


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


def test_sharp_steering_sensitivity():
    """Verify default sharp wheel profile reaches >60% steering with only ~8 degrees hand tilt."""
    wheel = VirtualSteeringWheel(
        neutral_angle=0.0,
        deadzone_angle=1.0,
        max_angle=14.0,
        sensitivity=1.40,
        smoothing_factor=1.0,
        response_curve="progressive_sharp"
    )

    # 480px width, dy = 68px -> atan2(68, 480) ~= 8.06 degrees
    left = make_dummy_hand("Left", 400, 326, 400, 326)
    right = make_dummy_hand("Right", 880, 394, 880, 394)
    res = wheel.update(FrameHandResult(left_hand=left, right_hand=right))

    assert 7.5 < res.relative_angle_deg < 8.5
    # Must deliver at least 0.60 (60%) steering authority at ~8 degrees tilt
    assert res.normalized_value >= 0.60
    assert res.xbox_stick_x >= 19500


def test_hypercar_smooth_precision():
    """Verify hypercar precision mode: fine micro-corrections near center and full lock at limit."""
    wheel = VirtualSteeringWheel(
        neutral_angle=0.0,
        deadzone_angle=1.5,
        max_angle=24.0,
        sensitivity=1.00,
        smoothing_factor=1.0,
        response_curve="hypercar_precision"
    )

    # 1. Micro-tilt (approx 3.5 degrees: dy = 29px on 480px width)
    left = make_dummy_hand("Left", 400, 345, 400, 345)
    right = make_dummy_hand("Right", 880, 374, 880, 374)
    res_micro = wheel.update(FrameHandResult(left_hand=left, right_hand=right))

    # At ~3.5 deg (just past deadzone), output should be ultra-gentle (< 10% deflection)
    assert 3.0 < res_micro.relative_angle_deg < 4.0
    assert res_micro.normalized_value < 0.10
    assert res_micro.xbox_stick_x < 3300

    # 2. Full Lock tilt (approx 25 degrees: dy = 224px on 480px width)
    left_lock = make_dummy_hand("Left", 400, 248, 400, 248)
    right_lock = make_dummy_hand("Right", 880, 472, 880, 472)
    res_lock = wheel.update(FrameHandResult(left_hand=left_lock, right_hand=right_lock))

    # Must provide full 100% steering lock for tight hairpins
    assert res_lock.relative_angle_deg > 24.0
    assert res_lock.normalized_value >= 0.99
    assert res_lock.xbox_stick_x >= 32400


