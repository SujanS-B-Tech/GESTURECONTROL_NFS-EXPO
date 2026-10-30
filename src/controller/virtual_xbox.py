"""
Virtual Xbox 360 Controller Interface for GESTUREDRIVE X.
Interfaces with ViGEmBus via vgamepad to generate genuine hardware-level XInput signals.
Includes graceful fallback, connection diagnostics, and state caching.
"""

from dataclasses import dataclass
import threading
import time
from typing import Optional, Dict

from src.utils.logger import logger


@dataclass
class GamepadState:
    """Current state of the virtual gamepad."""
    left_stick_x: int = 0      # -32768 to 32767
    left_stick_y: int = 0      # -32768 to 32767
    right_stick_x: int = 0
    right_stick_y: int = 0
    left_trigger: int = 0      # 0 to 255 (Brake)
    right_trigger: int = 0     # 0 to 255 (Throttle)
    button_a: bool = False     # Nitro
    button_b: bool = False
    button_x: bool = False     # Handbrake
    button_y: bool = False     # Camera
    button_start: bool = False # Pause / Menu
    button_back: bool = False
    button_lsb: bool = False   # Horn (Left Stick Click)
    button_rsb: bool = False


class VirtualXboxController:
    """
    Manages the virtual Xbox 360 controller device.
    Generates genuine XInput commands recognized natively by Need for Speed Heat.
    """

    def __init__(self):
        self._pad = None
        self._vg_module = None
        self._lock = threading.Lock()
        self._is_connected = False
        self._driver_installed = False
        self._last_error = ""
        self.state = GamepadState()

        self._init_controller()

    def _init_controller(self):
        """Attempts connection to ViGEmBus."""
        try:
            import vgamepad as vg
            self._vg_module = vg
            self._pad = vg.VX360Gamepad()
            self._is_connected = True
            self._driver_installed = True
            logger.info("Virtual Xbox 360 Controller successfully created via ViGEmBus!")
        except Exception as e:
            self._is_connected = False
            self._last_error = str(e)
            if "VIGEM_ERROR_BUS_NOT_FOUND" in str(e) or "bus" in str(e).lower():
                self._driver_installed = False
                logger.warning(
                    "ViGEmBus driver is not active on this Windows system. "
                    "Run 'install_driver.bat' as Administrator to enable virtual controller emulation."
                )
            else:
                logger.error(f"Failed to initialize virtual controller: {e}")

    @property
    def is_connected(self) -> bool:
        return self._is_connected

    @property
    def driver_installed(self) -> bool:
        return self._driver_installed

    @property
    def last_error(self) -> str:
        return self._last_error

    def retry_connection(self) -> bool:
        """Retry connection to ViGEmBus (e.g. after user installs driver)."""
        with self._lock:
            self._init_controller()
            return self._is_connected

    def set_steering(self, value: int):
        """Sets analog left stick X (-32768 to 32767)."""
        with self._lock:
            self.state.left_stick_x = int(max(-32768, min(32767, value)))
            if self._is_connected and self._pad:
                self._pad.left_joystick(x_value=self.state.left_stick_x, y_value=self.state.left_stick_y)

    def set_throttle(self, normalized: float):
        """Sets analog right trigger (0.0 to 1.0 -> 0 to 255)."""
        with self._lock:
            val_byte = int(max(0.0, min(1.0, normalized)) * 255.0)
            self.state.right_trigger = val_byte
            if self._is_connected and self._pad:
                self._pad.right_trigger(value=val_byte)

    def set_brake(self, normalized: float):
        """Sets analog left trigger (0.0 to 1.0 -> 0 to 255)."""
        with self._lock:
            val_byte = int(max(0.0, min(1.0, normalized)) * 255.0)
            self.state.left_trigger = val_byte
            if self._is_connected and self._pad:
                self._pad.left_trigger(value=val_byte)

    def set_button(self, button_name: str, pressed: bool):
        """Sets a digital Xbox button state."""
        with self._lock:
            button_name = button_name.lower()
            if hasattr(self.state, button_name):
                setattr(self.state, button_name, pressed)

            if not self._is_connected or not self._pad or not self._vg_module:
                return

            vg = self._vg_module
            btn_map = {
                "button_a": vg.XUSB_BUTTON.XUSB_GAMEPAD_A,
                "button_b": vg.XUSB_BUTTON.XUSB_GAMEPAD_B,
                "button_x": vg.XUSB_BUTTON.XUSB_GAMEPAD_X,
                "button_y": vg.XUSB_BUTTON.XUSB_GAMEPAD_Y,
                "button_start": vg.XUSB_BUTTON.XUSB_GAMEPAD_START,
                "button_back": vg.XUSB_BUTTON.XUSB_GAMEPAD_BACK,
                "button_lsb": vg.XUSB_BUTTON.XUSB_GAMEPAD_LEFT_THUMB,
                "button_rsb": vg.XUSB_BUTTON.XUSB_GAMEPAD_RIGHT_THUMB,
            }

            if button_name in btn_map:
                vg_btn = btn_map[button_name]
                if pressed:
                    self._pad.press_button(button=vg_btn)
                else:
                    self._pad.release_button(button=vg_btn)

    def update(self):
        """Dispatches all pending controller updates to the OS."""
        with self._lock:
            if self._is_connected and self._pad:
                self._pad.update()

    def reset_to_neutral(self):
        """Safely resets all sticks to center, triggers to 0, and releases all buttons."""
        with self._lock:
            self.state.left_stick_x = 0
            self.state.left_stick_y = 0
            self.state.right_stick_x = 0
            self.state.right_stick_y = 0
            self.state.left_trigger = 0
            self.state.right_trigger = 0
            self.state.button_a = False
            self.state.button_b = False
            self.state.button_x = False
            self.state.button_y = False
            self.state.button_start = False
            self.state.button_back = False
            self.state.button_lsb = False
            self.state.button_rsb = False

            if self._is_connected and self._pad:
                try:
                    self._pad.reset()
                    self._pad.update()
                except Exception as e:
                    logger.warning(f"Error resetting virtual gamepad: {e}")

    def close(self):
        """Release virtual controller on application exit."""
        self.reset_to_neutral()
        with self._lock:
            if self._pad:
                del self._pad
                self._pad = None
            self._is_connected = False
        logger.info("Virtual Xbox 360 Controller closed.")

