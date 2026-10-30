"""
Unit tests for Intuitive Input Mapping and Virtual Controller Dispatches.
"""

import time
import pytest

from src.controller.virtual_xbox import VirtualXboxController
from src.controller.input_mapper import InputMapper
from src.gestures.steering import SteeringState
from src.gestures.recognizer import FrameGestureResult, HandGestureState, HandGesture


def test_steering_dispatch():
    controller = VirtualXboxController()
    mapper = InputMapper(controller)

    steering = SteeringState(xbox_stick_x=16384)
    gestures = FrameGestureResult()

    mapper.process(steering, gestures)
    assert controller.state.left_stick_x == 16384


def test_drive_forward_dispatch():
    controller = VirtualXboxController()
    mapper = InputMapper(controller)

    steering = SteeringState(xbox_stick_x=0)
    gestures = FrameGestureResult(both_closed_drive=True, throttle_analog=1.0, brake_analog=0.0)

    mapper.process(steering, gestures)
    assert controller.state.right_trigger == 255
    assert controller.state.left_trigger == 0


def test_stop_and_reverse_dispatch():
    controller = VirtualXboxController()
    mapper = InputMapper(controller)

    steering = SteeringState(xbox_stick_x=-10000)
    gestures = FrameGestureResult(both_open_reverse=True, throttle_analog=0.0, brake_analog=1.0)

    mapper.process(steering, gestures)
    assert controller.state.left_trigger == 255
    assert controller.state.right_trigger == 0
    # Steering backward is preserved!
    assert controller.state.left_stick_x == -10000


def test_drift_handbrake_dispatch():
    controller = VirtualXboxController()
    mapper = InputMapper(controller)

    steering = SteeringState(xbox_stick_x=22000)
    gestures = FrameGestureResult(one_open_one_closed_drift=True, throttle_analog=0.65)

    mapper.process(steering, gestures)
    assert controller.state.button_x is True
    assert controller.state.right_trigger > 100
    assert controller.state.left_stick_x == 22000


def test_nitro_pulse_and_cooldown():
    controller = VirtualXboxController()
    mapper = InputMapper(controller)

    gestures = FrameGestureResult(thumbs_up_nitro=True)

    # First trigger: nitro button A should activate
    mapper.process(SteeringState(), gestures)
    assert controller.state.button_a is True

    # After pulse duration (e.g. 160ms), button A should release
    time.sleep(0.18)
    mapper.process(SteeringState(), gestures)
    assert controller.state.button_a is False

    # Within cooldown period (e.g. 600ms), immediate re-trigger should be blocked
    mapper.process(SteeringState(), gestures)
    assert controller.state.button_a is False


def test_emergency_stop_zeros_outputs():
    controller = VirtualXboxController()
    mapper = InputMapper(controller)

    steering = SteeringState(xbox_stick_x=20000)
    gestures = FrameGestureResult(throttle_analog=1.0, brake_analog=0.0)

    mapper.process(steering, gestures, emergency_stop=True)
    assert controller.state.left_stick_x == 0
    assert controller.state.right_trigger == 0
    assert controller.state.left_trigger == 0
    assert controller.state.button_a is False
    assert controller.state.button_x is False
