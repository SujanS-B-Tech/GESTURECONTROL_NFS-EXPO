"""
Intuitive Input Mapping Engine for GESTUREDRIVE X.
Translates:
- Two-hand steering wheel -> Analog Left Stick X (works in forward, reverse, and drift)
- Both hands closed -> Drive forward (RT)
- Both palms open -> Stop & Reverse (LT)
- One closed, one open -> Drift Handbrake (Button X) + power
- Either hand thumbs up -> Nitrous Boost (Button A)
"""

import time
from typing import Optional

from src.gestures.steering import SteeringState
from src.gestures.recognizer import FrameGestureResult
from src.controller.virtual_xbox import VirtualXboxController
from src.utils.logger import logger


class InputMapper:
    """Coordinates intuitive driving gestures and virtual controller outputs."""

    def __init__(self, controller: VirtualXboxController):
        self.controller = controller

        # Nitrous Debounce / Cooldown
        self._last_nitro_time = 0.0
        self._nitro_cooldown_s = 0.60
        self._nitro_pulse_duration_s = 0.15
        self._nitro_active = False

    def process(
        self,
        steering: SteeringState,
        gestures: FrameGestureResult,
        emergency_stop: bool = False
    ):
        """Processes steering and gesture updates and dispatches XInput signals."""
        if emergency_stop:
            self.controller.reset_to_neutral()
            return

        now = time.perf_counter()

        # 1. Analog Steering (Always active in forward, reverse, and drift)
        self.controller.set_steering(steering.xbox_stick_x)

        # 2. Drift Handbrake (One hand closed + one hand open -> Button X)
        is_drifting = gestures.one_open_one_closed_drift
        self.controller.set_button("button_x", is_drifting)

        # 3. Throttle & Brake
        # If drifting, maintain power to keep wheels spinning
        self.controller.set_throttle(gestures.throttle_analog)
        self.controller.set_brake(gestures.brake_analog)

        # 4. Nitrous Boost (Either hand thumbs up -> Button A)
        if gestures.thumbs_up_nitro and not self._nitro_active:
            if (now - self._last_nitro_time) >= self._nitro_cooldown_s:
                self._nitro_active = True
                self._last_nitro_time = now
                self.controller.set_button("button_a", True)
                logger.info("Nitrous boost engaged (Xbox A)")

        if self._nitro_active and (now - self._last_nitro_time) >= self._nitro_pulse_duration_s:
            self._nitro_active = False
            self.controller.set_button("button_a", False)

        # Dispatch atomic controller packet
        self.controller.update()

    def reset(self):
        """Resets all debounce states and controller outputs."""
        self._nitro_active = False
        self.controller.reset_to_neutral()
