"""
Unit tests for InGameOverlayHUD and floating overlay integration.
"""

import sys
import os
import pytest
import numpy as np

# Ensure offscreen Qt platform for headless CI / testing
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

from src.ui.overlay import InGameOverlayHUD
from src.gestures.steering import SteeringState
from src.gestures.recognizer import FrameGestureResult, HandGestureState, HandGesture
from src.controller.virtual_xbox import GamepadState


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    yield app


def test_overlay_initialization(qapp):
    hud = InGameOverlayHUD()
    assert hud is not None
    # Verify tool window flag for floating on top without taskbar stealing
    assert bool(hud.windowFlags() & Qt.WindowType.Tool)
    assert bool(hud.windowFlags() & Qt.WindowType.FramelessWindowHint)
    assert bool(hud.windowFlags() & Qt.WindowType.WindowStaysOnTopHint)
    hud.close()


def test_overlay_corner_snapping(qapp):
    hud = InGameOverlayHUD()
    hud.show()

    # Snap to all 4 corners
    for corner in range(4):
        hud.snap_to_corner(corner)
        assert hud._corner_idx == corner

    hud.snap_next_corner()
    assert hud._corner_idx == 0
    hud.close()


def test_overlay_opacity_cycling(qapp):
    hud = InGameOverlayHUD()
    initial_idx = hud._opacity_idx
    hud._cycle_opacity()
    assert hud._opacity_idx == (initial_idx + 1) % len(hud._opacities)
    hud.close()


def test_overlay_telemetry_rendering(qapp):
    hud = InGameOverlayHUD()
    hud.show()

    fake_frame = np.zeros((720, 1280, 3), dtype=np.uint8)

    # Test driving forward
    steering = SteeringState(active=True, raw_angle_deg=10.5, relative_angle_deg=10.5, xbox_stick_x=16000)
    gestures = FrameGestureResult(
        both_closed_drive=True,
        both_open_reverse=False,
        one_open_one_closed_drift=False,
        throttle_analog=1.0,
        brake_analog=0.0
    )
    gamepad = GamepadState(right_trigger=255)

    hud.update_telemetry(fake_frame, steering, gestures, gamepad, fps=60.0)
    assert "DRIVE" in hud.lbl_mode.text()
    assert "+10.5°" in hud.lbl_steer.text()

    # Test reverse mode
    gestures_rev = FrameGestureResult(
        both_closed_drive=False,
        both_open_reverse=True,
        one_open_one_closed_drift=False,
        throttle_analog=0.0,
        brake_analog=1.0
    )
    gamepad_rev = GamepadState(left_trigger=255)
    hud.update_telemetry(fake_frame, steering, gestures_rev, gamepad_rev, fps=58.0)
    assert "REVERSE" in hud.lbl_mode.text()

    # Test drift handbrake mode
    gestures_drift = FrameGestureResult(
        both_closed_drive=False,
        both_open_reverse=False,
        one_open_one_closed_drift=True,
        throttle_analog=0.0,
        brake_analog=0.0
    )
    gamepad_drift = GamepadState(button_x=True)
    hud.update_telemetry(fake_frame, steering, gestures_drift, gamepad_drift, fps=60.0)
    assert "DRIFT" in hud.lbl_mode.text()

    # Test nitro active
    gamepad_nitro = GamepadState(button_a=True)
    hud.update_telemetry(fake_frame, steering, gestures, gamepad_nitro, fps=60.0)
    assert "NITRO" in hud.lbl_mode.text()

    hud.close()
