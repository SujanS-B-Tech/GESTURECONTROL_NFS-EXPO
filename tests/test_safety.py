"""
Unit tests for Safety Watchdog and Process Watcher.
"""

import time
import pytest

from src.controller.virtual_xbox import VirtualXboxController
from src.controller.safety import SafetyWatchdog


def test_safety_tracking_loss_watchdog():
    controller = VirtualXboxController()
    watchdog = SafetyWatchdog(controller, tracking_loss_timeout_s=0.15)

    # Simulate active controller inputs
    controller.set_steering(15000)
    controller.set_throttle(0.8)
    controller.set_button("button_a", True)

    # Inform watchdog of detection
    watchdog.record_hand_detection()
    watchdog.record_camera_frame(time.perf_counter())

    # Wait past tracking timeout
    time.sleep(0.20)
    tracking_lost, camera_frozen = watchdog.evaluate_safety()

    assert tracking_lost is True
    # Verify controller state was forced to neutral
    assert controller.state.left_stick_x == 0
    assert controller.state.right_trigger == 0
    assert controller.state.button_a is False


def test_safety_emergency_stop():
    controller = VirtualXboxController()
    watchdog = SafetyWatchdog(controller)

    controller.set_steering(25000)
    controller.set_throttle(1.0)
    assert controller.state.right_trigger == 255

    # Engage emergency stop
    watchdog.set_emergency_stop(True)
    assert watchdog.emergency_stop is True
    assert controller.state.right_trigger == 0
    assert controller.state.left_stick_x == 0

    # Disengage
    watchdog.set_emergency_stop(False)
    assert watchdog.emergency_stop is False


def test_process_watcher_safe_execution():
    controller = VirtualXboxController()
    watchdog = SafetyWatchdog(controller)

    # Calling check_nfs_heat_process must succeed without throwing errors
    is_running, pid = watchdog.check_nfs_heat_process()
    assert isinstance(is_running, bool)
    assert pid is None or isinstance(pid, int)

