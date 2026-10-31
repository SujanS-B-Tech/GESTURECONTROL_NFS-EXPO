"""
Unit tests for Intuitive Driving Gesture Recognition.
"""

import pytest
import numpy as np

from src.gestures.recognizer import GestureRecognizer, HandGesture
from src.camera.hand_tracker import HandData, FrameHandResult


def create_mock_hand(label: str, gesture_type: str, wrist_pos=(0.5, 0.7)) -> HandData:
    """Generates synthetic 21 landmark configurations for specific gestures."""
    lm = np.zeros((21, 3), dtype=np.float32)
    wx, wy = wrist_pos
    lm[0] = [wx, wy, 0.0]

    # Baseline MCP offsets from wrist
    mcp_offsets = [
        (-0.05, -0.05),  # 1: Thumb CMC
        (-0.04, -0.12),  # 5: Index MCP
        (0.00, -0.13),   # 9: Middle MCP
        (0.04, -0.12),   # 13: Ring MCP
        (0.07, -0.10)    # 17: Pinky MCP
    ]

    lm[1] = [wx + mcp_offsets[0][0], wy + mcp_offsets[0][1], 0.0]
    lm[5] = [wx + mcp_offsets[1][0], wy + mcp_offsets[1][1], 0.0]
    lm[9] = [wx + mcp_offsets[2][0], wy + mcp_offsets[2][1], 0.0]
    lm[13] = [wx + mcp_offsets[3][0], wy + mcp_offsets[3][1], 0.0]
    lm[17] = [wx + mcp_offsets[4][0], wy + mcp_offsets[4][1], 0.0]

    if gesture_type == "open_palm":
        # All fingers extended outward (ratio dist(wrist, tip) / dist(wrist, mcp) >= 2.0)
        lm[2] = [wx - 0.09, wy - 0.10, 0.0]
        lm[3] = [wx - 0.13, wy - 0.15, 0.0]
        lm[4] = [wx - 0.17, wy - 0.20, 0.0]

        lm[6] = [wx - 0.04, wy - 0.17, 0.0]
        lm[7] = [wx - 0.04, wy - 0.22, 0.0]
        lm[8] = [wx - 0.04, wy - 0.28, 0.0]

        lm[10] = [wx, wy - 0.19, 0.0]
        lm[11] = [wx, wy - 0.25, 0.0]
        lm[12] = [wx, wy - 0.31, 0.0]

        lm[14] = [wx + 0.04, wy - 0.17, 0.0]
        lm[15] = [wx + 0.04, wy - 0.22, 0.0]
        lm[16] = [wx + 0.04, wy - 0.27, 0.0]

        lm[18] = [wx + 0.07, wy - 0.14, 0.0]
        lm[19] = [wx + 0.07, wy - 0.18, 0.0]
        lm[20] = [wx + 0.07, wy - 0.23, 0.0]

    elif gesture_type == "closed_fist":
        # All tips curled inward to palm (ratio dist(wrist, tip) / dist(wrist, mcp) <= 1.0)
        lm[2] = [wx - 0.04, wy - 0.07, 0.0]
        lm[3] = [wx - 0.01, wy - 0.08, 0.0]
        lm[4] = [wx + 0.02, wy - 0.08, 0.0]

        for mcp_idx in [5, 9, 13, 17]:
            mcp_x, mcp_y = lm[mcp_idx][:2]
            lm[mcp_idx + 1] = [mcp_x, mcp_y - 0.02, 0.0]
            lm[mcp_idx + 2] = [mcp_x, mcp_y + 0.01, 0.0]
            lm[mcp_idx + 3] = [mcp_x, mcp_y + 0.03, 0.0]

    elif gesture_type == "thumbs_up":
        # Thumb pointing straight up (y decreases directly upwards)
        lm[2] = [wx - 0.03, wy - 0.08, 0.0]
        lm[3] = [wx - 0.03, wy - 0.14, 0.0]
        lm[4] = [wx - 0.03, wy - 0.20, 0.0]

        for mcp_idx in [5, 9, 13, 17]:
            mcp_x, mcp_y = lm[mcp_idx][:2]
            lm[mcp_idx + 1] = [mcp_x, mcp_y - 0.02, 0.0]
            lm[mcp_idx + 2] = [mcp_x, mcp_y + 0.01, 0.0]
            lm[mcp_idx + 3] = [mcp_x, mcp_y + 0.03, 0.0]

    pixel_lm = (lm[:, :2] * np.array([1280, 720])).astype(np.int32)
    return HandData(
        handedness=label,
        landmarks=lm,
        pixel_landmarks=pixel_lm,
        confidence=0.92,
        bbox=(int(wx * 1280), int(wy * 720), 100, 100),
        wrist_px=tuple(pixel_lm[0]),
        index_tip_px=tuple(pixel_lm[8]),
        thumb_tip_px=tuple(pixel_lm[4])
    )


def test_both_closed_drives_forward():
    recognizer = GestureRecognizer()
    left_fist = create_mock_hand("Left", "closed_fist")
    right_fist = create_mock_hand("Right", "closed_fist")
    frame_res = FrameHandResult(left_hand=left_fist, right_hand=right_fist)

    res = recognizer.process_frame(frame_res)
    assert res.both_closed_drive is True
    assert res.throttle_analog > 0.0
    assert res.brake_analog == 0.0


def test_both_open_stops_and_reverses():
    recognizer = GestureRecognizer()
    left_open = create_mock_hand("Left", "open_palm")
    right_open = create_mock_hand("Right", "open_palm")
    frame_res = FrameHandResult(left_hand=left_open, right_hand=right_open)

    res = recognizer.process_frame(frame_res)
    assert res.both_open_reverse is True
    assert res.brake_analog > 0.0
    assert res.throttle_analog == 0.0


def test_one_closed_one_open_drives_forward_no_drift():
    """Verify drift option using gesture is removed: turning or relaxing one hand keeps driving forward."""
    recognizer = GestureRecognizer()
    left_fist = create_mock_hand("Left", "closed_fist")
    right_open = create_mock_hand("Right", "open_palm")
    frame_res = FrameHandResult(left_hand=left_fist, right_hand=right_open)

    res = recognizer.process_frame(frame_res)
    assert res.one_open_one_closed_drift is False
    assert res.both_closed_drive is True
    assert res.throttle_analog > 0.0  # Drive forward power maintained


def test_thumbs_up_triggers_nitrous():
    recognizer = GestureRecognizer()
    left_fist = create_mock_hand("Left", "closed_fist")
    right_thumbs = create_mock_hand("Right", "thumbs_up")
    frame_res = FrameHandResult(left_hand=left_fist, right_hand=right_thumbs)

    res = recognizer.process_frame(frame_res)
    assert res.thumbs_up_nitro is True


def test_throttle_instant_punch():
    """Verify sharp throttle response reaches near-full authority within 2 frames."""
    recognizer = GestureRecognizer(throttle_smoothing=0.75)
    left_fist = create_mock_hand("Left", "closed_fist")
    right_fist = create_mock_hand("Right", "closed_fist")
    frame = FrameHandResult(left_hand=left_fist, right_hand=right_fist)

    # Frame 1
    res1 = recognizer.process_frame(frame)
    assert res1.throttle_analog >= 0.70

    # Frame 2
    res2 = recognizer.process_frame(frame)
    assert res2.throttle_analog >= 0.90


def test_brake_instant_bite_and_throttle_cutoff():
    """Verify emergency stop cuts throttle instantly and bites with >80% brake on frame 1."""
    recognizer = GestureRecognizer(throttle_smoothing=0.75, brake_smoothing=0.85)

    # Start by driving forward
    fist = create_mock_hand("Left", "closed_fist")
    recognizer.process_frame(FrameHandResult(left_hand=fist, right_hand=fist))
    recognizer.process_frame(FrameHandResult(left_hand=fist, right_hand=fist))

    # Suddenly open both palms to reverse
    open_h = create_mock_hand("Left", "open_palm")
    res = recognizer.process_frame(FrameHandResult(left_hand=open_h, right_hand=open_h))

    assert res.both_open_reverse is True
    assert res.throttle_analog == 0.0      # Cutoff immediate!
    assert res.brake_analog >= 0.80        # Instant stopping bite!

