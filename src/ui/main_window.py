"""
Main Desktop Application Window for GESTUREDRIVE X.
Assembles the complete AI touchless racing control system into a premium,
cyberpunk/racing dashboard desktop interface with real-time telemetry.
"""

import os
import sys
import time
from typing import Optional
import cv2
import numpy as np

from PySide6.QtCore import Qt, QTimer, Slot, Signal
from PySide6.QtGui import QFont, QIcon, QColor, QPalette, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QFrame, QMessageBox, QStatusBar, QScrollArea,
    QTextEdit, QSplitter
)

from src.camera.webcam import WebcamCapture
from src.camera.hand_tracker import HandTracker, FrameHandResult
from src.gestures.steering import VirtualSteeringWheel, SteeringState
from src.gestures.recognizer import GestureRecognizer, FrameGestureResult, HandGesture
from src.gestures.calibration import CalibrationManager
from src.controller.virtual_xbox import VirtualXboxController, GamepadState
from src.controller.input_mapper import InputMapper
from src.controller.safety import SafetyWatchdog
from src.utils.performance import PerformanceTracker
from src.utils.logger import logger

from src.ui.dashboard import VideoDisplayWidget, SteeringWheelWidget, TelemetryBarWidget, StatusBadge
from src.ui.calibration_ui import CalibrationWizardDialog
from src.ui.settings import SettingsDialog
from src.ui.controller_test_ui import ControllerTestDialog
from src.ui.overlay import InGameOverlayHUD


class MainWindow(QMainWindow):
    """Primary application window for GESTUREDRIVE X."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("GESTUREDRIVE X — AI-Powered Touchless Control for Need for Speed Heat")
        self.resize(1380, 860)
        self.setMinimumSize(1100, 720)

        icon_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "assets", "icon.ico")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        # Apply Global Dark Racing Stylesheet
        self._apply_theme()

        # Core Engines Initialization
        self.performance = PerformanceTracker()
        self.calibration_mgr = CalibrationManager()
        profile = self.calibration_mgr.profile

        self.webcam = WebcamCapture(device_index=0, width=1280, height=720, fps=30, mirror_horizontal=True)
        self.tracker: Optional[HandTracker] = None
        self.steering = VirtualSteeringWheel(
            neutral_angle=profile.neutral_angle,
            deadzone_angle=profile.deadzone_angle if profile.is_calibrated else 1.5,
            max_angle=profile.max_right_angle if profile.is_calibrated else 24.0,
            max_left_angle=profile.max_left_angle if profile.is_calibrated else 24.0,
            max_right_angle=profile.max_right_angle if profile.is_calibrated else 24.0,
            sensitivity=1.00,
            smoothing_factor=0.45,
            response_curve="hypercar_precision",
            adaptive_smoothing=True
        )
        self.recognizer = GestureRecognizer(
            throttle_smoothing=0.75,
            brake_smoothing=0.85
        )
        self.controller = VirtualXboxController()
        self.mapper = InputMapper(self.controller)
        self.watchdog = SafetyWatchdog(self.controller)

        # Sensitivity Presets (Optimized for Hypercar Stability & Progressive Smoothness)
        self._sens_presets = [
            ("STEERING: HYPERCAR SMOOTH (1.0x)", 1.00),
            ("STEERING: PRECISION PRO (0.85x)", 0.85),
            ("STEERING: SPORT (1.15x)", 1.15),
            ("STEERING: SHARP (1.40x)", 1.40)
        ]
        self._sens_idx = 0  # Hypercar Smooth default

        # Active dialog references
        self._test_dialog: Optional[ControllerTestDialog] = None
        self._calibration_dialog: Optional[CalibrationWizardDialog] = None
        self.overlay: Optional[InGameOverlayHUD] = None

        # State flags
        self.is_tracking = False

        # Global Hotkey State (Windows GetAsyncKeyState Edge Detection)
        self._key_down_states = {}

        # Build UI layout
        self._init_ui()

        # Keyboard shortcuts
        self._setup_shortcuts()

        # Global Windows Hotkey Polling Timer (Checks F10, F9, F12, C every 25ms even when NFS Heat has focus)
        self._hotkey_timer = QTimer(self)
        self._hotkey_timer.setInterval(25)
        self._hotkey_timer.timeout.connect(self._poll_global_hotkeys)
        self._hotkey_timer.start()

        # High-frequency Processing Loop Timer (30-60 FPS)
        self.process_timer = QTimer(self)
        self.process_timer.setInterval(16)  # ~60 Hz tick
        self.process_timer.timeout.connect(self._process_frame_tick)

        # Process Watcher Timer (1 Hz check for NFS Heat)
        self.proc_timer = QTimer(self)
        self.proc_timer.setInterval(1500)
        self.proc_timer.timeout.connect(self._check_nfs_heat_tick)
        self.proc_timer.start()

    def _apply_theme(self):
        """Sets modern dark charcoal & racing red styling."""
        self.setStyleSheet("""
            QMainWindow {
                background-color: #0A0A0E;
            }
            QWidget {
                color: #E2E2EC;
                font-family: 'Segoe UI', Arial, sans-serif;
            }
            QFrame#card {
                background-color: #12121A;
                border: 1px solid #1E1E2A;
                border-radius: 8px;
            }
            QFrame#panel {
                background-color: #0F0F16;
                border: 1px solid #222230;
                border-radius: 8px;
            }
            QPushButton {
                background-color: #1A1A26;
                border: 1px solid #2E2E40;
                color: #FFFFFF;
                border-radius: 6px;
                padding: 8px 16px;
                font-weight: bold;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #262638;
                border: 1px solid #00E5FF;
            }
            QPushButton#btn_danger {
                background-color: #7A0A10;
                border: 1px solid #C00810;
                color: #FFFFFF;
                font-size: 12px;
            }
            QPushButton#btn_danger:hover {
                background-color: #A00A14;
                border: 1px solid #FF1E27;
            }
            QPushButton#btn_start {
                background-color: #0A5A30;
                border: 1px solid #10B050;
            }
            QPushButton#btn_start:hover {
                background-color: #0E7840;
                border: 1px solid #00FF66;
            }
            QStatusBar {
                background-color: #08080C;
                border-top: 1px solid #1A1A24;
                color: #707085;
                font-size: 11px;
            }
        """)

    def _init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(16, 12, 16, 12)
        main_layout.setSpacing(12)

        # 1. Header Toolbar
        main_layout.addLayout(self._create_header())

        # 2. NFS Heat Borderless Mode Setup Banner
        self.banner_nfs = QFrame()
        self.banner_nfs.setStyleSheet("""
            QFrame {
                background-color: #0E1622;
                border: 1px solid #00E5FF;
                border-radius: 6px;
            }
        """)
        banner_layout = QHBoxLayout(self.banner_nfs)
        banner_layout.setContentsMargins(12, 6, 12, 6)
        banner_layout.setSpacing(10)

        lbl_icon = QLabel("🎮")
        lbl_icon.setStyleSheet("font-size: 14px;")
        banner_layout.addWidget(lbl_icon)

        self.lbl_banner_msg = QLabel(
            "<b>NFS HEAT OVERLAY GUIDE:</b> Press <b>[Alt + Enter]</b> in NFS Heat (or set Video to <b>'Borderless'</b>) "
            "so this floating HUD can render directly over your game! Press <b>[F10]</b> to toggle HUD anytime."
        )
        self.lbl_banner_msg.setStyleSheet("color: #DDE2EC; font-size: 11px;")
        banner_layout.addWidget(self.lbl_banner_msg, stretch=1)

        btn_guide = QPushButton("HOW TO ENABLE BORDERLESS")
        btn_guide.setStyleSheet("background-color: #1A2838; border: 1px solid #00E5FF; color: #00E5FF; font-size: 10px; padding: 4px 10px;")
        btn_guide.clicked.connect(self._show_borderless_help)
        banner_layout.addWidget(btn_guide)

        main_layout.addWidget(self.banner_nfs)

        # 3. Main Content Splitter (Left: Live Video & Controls, Right: Telemetry & Status)
        content_layout = QHBoxLayout()
        content_layout.setSpacing(14)

        # Left Column: Video Preview + Quick Action Bar
        left_col = QVBoxLayout()
        left_col.setSpacing(10)

        self.video_display = VideoDisplayWidget(self)
        left_col.addWidget(self.video_display, stretch=1)

        # Quick Control Bar underneath camera
        left_col.addLayout(self._create_camera_toolbar())

        content_layout.addLayout(left_col, stretch=6)

        # Right Column: Racing Telemetry Dashboard
        right_col = QVBoxLayout()
        right_col.setSpacing(10)

        right_col.addWidget(self._create_telemetry_panel())
        right_col.addWidget(self._create_status_grid())

        content_layout.addLayout(right_col, stretch=4)
        main_layout.addLayout(content_layout, stretch=1)

        # Status Bar
        self.statusBar().showMessage("Ready. Click 'START TRACKING' to begin camera input.")

    def _create_header(self) -> QHBoxLayout:
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 4)

        title_layout = QVBoxLayout()
        title_layout.setSpacing(1)

        lbl_title = QLabel("GESTUREDRIVE X")
        lbl_title.setStyleSheet("font-size: 22px; font-weight: 900; letter-spacing: 2px; color: #FFFFFF; font-family: 'Segoe UI Black', Arial;")

        lbl_sub = QLabel("AI-POWERED TOUCHLESS RACING CONTROL — NEED FOR SPEED HEAT")
        lbl_sub.setStyleSheet("font-size: 10px; font-weight: bold; letter-spacing: 1.5px; color: #FF1E27;")

        title_layout.addWidget(lbl_title)
        title_layout.addWidget(lbl_sub)
        header.addLayout(title_layout)

        header.addStretch()

        # Top Buttons: Overlay HUD, Test Controller, Calibrate, Settings
        self.btn_overlay = QPushButton("IN-GAME OVERLAY (F10)")
        self.btn_overlay.setStyleSheet("background-color: #0E3A4A; border: 1px solid #00E5FF; color: #FFFFFF;")
        self.btn_overlay.clicked.connect(self._toggle_overlay)
        header.addWidget(self.btn_overlay)

        self.btn_test_mode = QPushButton("CONTROLLER MONITOR")
        self.btn_test_mode.clicked.connect(self._open_controller_monitor)
        header.addWidget(self.btn_test_mode)

        self.btn_calibrate = QPushButton("CALIBRATE WIZARD")
        self.btn_calibrate.clicked.connect(self._open_calibration_wizard)
        header.addWidget(self.btn_calibrate)

        self.btn_settings = QPushButton("SETTINGS")
        self.btn_settings.clicked.connect(self._open_settings)
        header.addWidget(self.btn_settings)

        return header

    def _create_camera_toolbar(self) -> QHBoxLayout:
        bar = QHBoxLayout()
        bar.setSpacing(10)

        self.btn_toggle_tracking = QPushButton("START TRACKING")
        self.btn_toggle_tracking.setObjectName("btn_start")
        self.btn_toggle_tracking.setMinimumHeight(38)
        self.btn_toggle_tracking.clicked.connect(self._toggle_tracking)
        bar.addWidget(self.btn_toggle_tracking, stretch=2)

        self.btn_sens = QPushButton(self._sens_presets[self._sens_idx][0])
        self.btn_sens.setMinimumHeight(38)
        self.btn_sens.setStyleSheet("background-color: #202030; border: 1px solid #FF9100; color: #FF9100;")
        self.btn_sens.clicked.connect(self._cycle_sensitivity)
        bar.addWidget(self.btn_sens, stretch=2)

        self.btn_recenter = QPushButton("RECENTER WHEEL (C)")
        self.btn_recenter.setMinimumHeight(38)
        self.btn_recenter.setStyleSheet("background-color: #1A2838; border: 1px solid #00E5FF;")
        self.btn_recenter.clicked.connect(self._recenter_steering)
        bar.addWidget(self.btn_recenter, stretch=2)

        self.btn_emergency_stop = QPushButton("EMERGENCY STOP (F12)")
        self.btn_emergency_stop.setObjectName("btn_danger")
        self.btn_emergency_stop.setMinimumHeight(38)
        self.btn_emergency_stop.clicked.connect(self._toggle_emergency_stop)
        bar.addWidget(self.btn_emergency_stop, stretch=2)

        return bar

    def _create_telemetry_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("panel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(10)

        lbl_hdr = QLabel("LIVE VEHICLE TELEMETRY")
        lbl_hdr.setStyleSheet("color: #FF1E27; font-size: 11px; font-weight: bold; letter-spacing: 1px;")
        layout.addWidget(lbl_hdr)

        telemetry_row = QHBoxLayout()
        telemetry_row.setSpacing(12)

        # Steering Wheel Gauge
        self.wheel_widget = SteeringWheelWidget(self)
        telemetry_row.addWidget(self.wheel_widget, stretch=3)

        # Throttle Bar (RT)
        self.throttle_bar = TelemetryBarWidget("THROTTLE\n(RT)", "#FF1E27", self)
        telemetry_row.addWidget(self.throttle_bar, stretch=1)

        # Brake Bar (LT)
        self.brake_bar = TelemetryBarWidget("BRAKE\n(LT)", "#00E5FF", self)
        telemetry_row.addWidget(self.brake_bar, stretch=1)

        layout.addLayout(telemetry_row)
        return panel

    def _create_status_grid(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("card")
        layout = QGridLayout(frame)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # Row 0: Hand Trackers
        self.badge_left_hand = StatusBadge("LEFT HAND (BRAKE / 9 O'CLOCK)", "NO HAND DETECTED", False)
        self.badge_right_hand = StatusBadge("RIGHT HAND (THROTTLE / 3 O'CLOCK)", "NO HAND DETECTED", False)
        layout.addWidget(self.badge_left_hand, 0, 0)
        layout.addWidget(self.badge_right_hand, 0, 1)

        # Row 1: Controller & Game Connection
        drv_text = "CONNECTED (VIGEMBUS)" if self.controller.driver_installed else "DRIVER REQUIRED"
        self.badge_gamepad = StatusBadge("VIRTUAL XBOX 360", drv_text, self.controller.driver_installed)
        self.badge_nfs = StatusBadge("NEED FOR SPEED HEAT", "CHECKING PROCESS...", False)
        layout.addWidget(self.badge_gamepad, 1, 0)
        layout.addWidget(self.badge_nfs, 1, 1)

        # Row 2: Performance & Special Controls (Nitro / Handbrake)
        self.badge_perf = StatusBadge("SYSTEM TELEMETRY", "FPS: 0.0 | Latency: 0.0 ms", True)
        self.badge_actions = StatusBadge("ACTIVE BOOST / BRAKE", "STANDBY", False)
        layout.addWidget(self.badge_perf, 2, 0)
        layout.addWidget(self.badge_actions, 2, 1)

        return frame

    def _setup_shortcuts(self):
        shortcut_f12 = QShortcut(QKeySequence("F12"), self)
        shortcut_f12.activated.connect(self._toggle_emergency_stop)

        shortcut_space = QShortcut(QKeySequence("Space"), self)
        shortcut_space.activated.connect(self._toggle_tracking)

        shortcut_c = QShortcut(QKeySequence("C"), self)
        shortcut_c.activated.connect(self._recenter_steering)

        shortcut_f10 = QShortcut(QKeySequence("F10"), self)
        shortcut_f10.activated.connect(self._toggle_overlay)

        shortcut_f9 = QShortcut(QKeySequence("F9"), self)
        shortcut_f9.activated.connect(self._snap_overlay_next_corner)

        shortcut_s = QShortcut(QKeySequence("S"), self)
        shortcut_s.activated.connect(self._cycle_sensitivity)

    def _poll_global_hotkeys(self):
        """
        Polls global asynchronous key states via Win32 GetAsyncKeyState.
        Allows F10 (overlay toggle), F9 (snap corner), F12 (emergency stop),
        and C (recenter) to function globally even while NFS Heat has foreground focus!
        """
        if sys.platform != "win32":
            return

        import ctypes
        user32 = ctypes.windll.user32

        # Virtual Key Codes
        VK_F10 = 0x79
        VK_F9 = 0x78
        VK_F12 = 0x7B
        VK_C = 0x43

        keys_to_check = [
            (VK_F10, self._toggle_overlay),
            (VK_F9, self._snap_overlay_next_corner),
            (VK_F12, self._toggle_emergency_stop),
        ]

        # Only allow 'C' recenter if tracking is active to avoid interfering with normal text typing
        if self.is_tracking:
            keys_to_check.append((VK_C, self._recenter_steering))

        for vk, callback in keys_to_check:
            # 0x8000 is set if the key is currently held down
            is_down = bool(user32.GetAsyncKeyState(vk) & 0x8000)
            was_down = self._key_down_states.get(vk, False)
            self._key_down_states[vk] = is_down

            # Clean edge trigger on initial press transition only
            if is_down and not was_down:
                callback()

    def _toggle_overlay(self):
        """Toggles the floating in-game picture-in-picture overlay on/off."""
        if self.overlay is None:
            self.overlay = InGameOverlayHUD()
            self.overlay.snap_to_corner(0)  # Top-Right by default

        if self.overlay.isVisible():
            self.overlay.hide()
            self.btn_overlay.setText("IN-GAME OVERLAY (F10)")
            self.btn_overlay.setStyleSheet("background-color: #0E3A4A; border: 1px solid #00E5FF; color: #FFFFFF;")
            self.statusBar().showMessage("In-Game Overlay HUD hidden.")
        else:
            self.overlay.show()
            self.overlay._enforce_topmost()
            self.btn_overlay.setText("OVERLAY VISIBLE (F10)")
            self.btn_overlay.setStyleSheet("background-color: #00A3B4; border: 1px solid #FFFFFF; color: #000000; font-weight: bold;")
            self.statusBar().showMessage("In-Game Overlay HUD ACTIVE! Floats on top of Need for Speed Heat.")

    def _snap_overlay_next_corner(self):
        """Snaps overlay to the next corner (Top-Right, Top-Left, Bottom-Left, Bottom-Right)."""
        if self.overlay and self.overlay.isVisible():
            self.overlay.snap_next_corner()
            self.statusBar().showMessage(f"In-Game Overlay snapped to corner position {self.overlay._corner_idx + 1}/4")

    def _show_borderless_help(self):
        """Displays step-by-step guidance on setting NFS Heat to Borderless mode."""
        msg = (
            "<h3>🎮 How to Display the In-Game Overlay over Need for Speed Heat</h3>"
            "<p>DirectX games running in <b>Exclusive Fullscreen</b> mode bypass the Windows Desktop Window Manager (DWM), "
            "which prevents external overlays from rendering on top of the screen.</p>"
            "<p><b>To enable overlay support in 3 seconds:</b></p>"
            "<ol>"
            "<li>While inside <b>Need for Speed Heat</b>, press <b>Alt + Enter</b> on your keyboard.<br>"
            "This immediately switches the game to Borderless / Windowed mode.</li>"
            "<li><b>OR</b> from the game menu: Go to <b>Settings &rarr; Graphics / Video &rarr; Display Mode &rarr; 'Borderless'</b>.</li>"
            "<li>Press <b>F10</b> anytime (even in the middle of a race) to toggle the GESTUREDRIVE X floating HUD!</li>"
            "<li>Press <b>F9</b> to snap the HUD between screen corners so it never blocks your mini-map or speedometer.</li>"
            "</ol>"
            "<p style='color: #00E5FF;'><i>Borderless mode gives you full native resolution, 100% graphics fidelity, zero input lag, and the live gesture HUD floating over your car!</i></p>"
        )
        QMessageBox.information(self, "NFS Heat Overlay Setup Guide", msg)

    def _cycle_sensitivity(self):
        """Cycles through steering sensitivity presets."""
        self._sens_idx = (self._sens_idx + 1) % len(self._sens_presets)
        label, mult = self._sens_presets[self._sens_idx]
        self.steering.sensitivity = mult
        self.btn_sens.setText(label)
        self.statusBar().showMessage(f"Steering Sensitivity changed to: {label}")
        logger.info(f"Steering sensitivity set to {mult:.2f}x ({label})")

    def _recenter_steering(self):
        """Immediately zeros out any resting angle so the current hand tilt is dead center."""
        raw = self.steering._last_valid_state.raw_angle_deg
        self.steering.set_neutral_now(raw)
        self.statusBar().showMessage(f"Wheel Recentered! Neutral angle set to {raw:+.1f}°")

    def _toggle_tracking(self):
        if not self.is_tracking:
            self._start_tracking()
        else:
            self._stop_tracking()

    def _start_tracking(self):
        if not self.webcam.start():
            QMessageBox.critical(self, "Camera Error", "Could not open webcam device. Check connection in Settings.")
            return

        if self.tracker is None:
            try:
                self.tracker = HandTracker()
            except Exception as e:
                QMessageBox.critical(self, "AI Model Error", f"Failed to initialize MediaPipe model:\n{e}")
                self.webcam.stop()
                return

        self.is_tracking = True
        self.btn_toggle_tracking.setText("STOP TRACKING")
        self.btn_toggle_tracking.setStyleSheet("background-color: #A01018; border: 1px solid #FF1E27;")
        self.process_timer.start()
        self.statusBar().showMessage("Tracking ACTIVE. Hands controlling virtual Xbox 360 gamepad.")
        logger.info("Tracking loop started.")

    def _stop_tracking(self):
        self.is_tracking = False
        self.process_timer.stop()
        self.webcam.stop()
        self.mapper.reset()
        self.controller.reset_to_neutral()

        self.btn_toggle_tracking.setText("START TRACKING")
        self.btn_toggle_tracking.setObjectName("btn_start")
        self.btn_toggle_tracking.setStyleSheet("")

        # Reset visualizers
        self.wheel_widget.set_steering(0.0, 0, False)
        self.throttle_bar.set_value(0.0)
        self.brake_bar.set_value(0.0)
        self.badge_left_hand.set_status("OFFLINE", False)
        self.badge_right_hand.set_status("OFFLINE", False)
        self.badge_actions.set_status("STANDBY", False)

        self.statusBar().showMessage("Tracking STOPPED. Controller inputs safely neutralized.")
        logger.info("Tracking loop stopped.")

    def _toggle_emergency_stop(self):
        new_state = not self.watchdog.emergency_stop
        self.watchdog.set_emergency_stop(new_state)

        if new_state:
            self.btn_emergency_stop.setText("ENGAGED! CLICK TO RESUME (F12)")
            self.btn_emergency_stop.setStyleSheet("background-color: #FF0015; border: 2px solid #FFFFFF; color: #FFFFFF;")
            self.statusBar().showMessage("EMERGENCY STOP ACTIVE! All controller outputs locked to zero.")
        else:
            self.btn_emergency_stop.setText("EMERGENCY STOP (F12)")
            self.btn_emergency_stop.setStyleSheet("")
            self.statusBar().showMessage("Emergency Stop released. Controls operational.")

    def _process_frame_tick(self):
        """High-speed processing tick: grabs frame, infers hands, maps inputs, updates telemetry."""
        if not self.is_tracking or self.tracker is None:
            return

        t_start = self.performance.start_frame()

        ret, frame, frame_ts = self.webcam.read_latest()
        if not ret or frame is None:
            self.performance.record_dropped_frame()
            self.watchdog.evaluate_safety()
            return

        self.watchdog.record_camera_frame(frame_ts)

        # 1. MediaPipe Two-Hand Tracking
        hand_res = self.tracker.process_frame(frame, frame_ts)

        if hand_res.any_hand_detected:
            self.watchdog.record_hand_detection()

        # 2. Evaluate Safety Timeouts
        tracking_lost, camera_frozen = self.watchdog.evaluate_safety()

        # 3. Steering Wheel Calculation
        steering_state = self.steering.update(hand_res)

        # 4. Gesture Recognition
        gesture_res = self.recognizer.process_frame(hand_res)

        # 5. Virtual Controller Input Mapping
        self.mapper.process(steering_state, gesture_res, emergency_stop=self.watchdog.emergency_stop)

        # 6. Render HUD Overlays onto Camera Preview
        annotated_frame = self.tracker.draw_landmarks(frame, hand_res, steering_wheel_active=steering_state.active)
        rgb_frame = cv2.cvtColor(annotated_frame, cv2.COLOR_BGR2RGB)
        h, w, _ = rgb_frame.shape
        self.video_display.update_frame(rgb_frame, w, h)

        # 7. Update UI Telemetry Widgets
        self.wheel_widget.set_steering(
            steering_state.relative_angle_deg,
            steering_state.xbox_stick_x,
            steering_state.active
        )
        self.throttle_bar.set_value(gesture_res.throttle_analog)
        self.brake_bar.set_value(gesture_res.brake_analog)

        # Update Badges
        if hand_res.left_hand:
            conf = int(hand_res.left_hand.confidence * 100)
            gest_name = gesture_res.left.gesture.value.replace("_", " ").upper()
            self.badge_left_hand.set_status(f"LOCKED ({conf}%) — {gest_name}", True, "#00E5FF")
        else:
            self.badge_left_hand.set_status("SEARCHING...", False)

        if hand_res.right_hand:
            conf = int(hand_res.right_hand.confidence * 100)
            gest_name = gesture_res.right.gesture.value.replace("_", " ").upper()
            self.badge_right_hand.set_status(f"LOCKED ({conf}%) — {gest_name}", True, "#FF1E27")
        else:
            self.badge_right_hand.set_status("SEARCHING...", False)

        # Driving Intent & Action Badge (Nitro, Drive, Reverse)
        if self.controller.state.button_a:
            self.badge_actions.set_status("NITROUS BOOST (A)", True, "#00E676")
        elif gesture_res.both_open_reverse:
            self.badge_actions.set_status("STOP & REVERSE (LT)", True, "#00E5FF")
        elif gesture_res.both_closed_drive:
            self.badge_actions.set_status("DRIVING FORWARD (RT)", True, "#00FF66")
        else:
            self.badge_actions.set_status("COASTING / NEUTRAL", False)

        # Stream to in-game overlay HUD if open
        if self.overlay and self.overlay.isVisible():
            self.overlay.update_telemetry(
                rgb_frame,
                steering_state,
                gesture_res,
                self.controller.state,
                self.performance.fps
            )

        # Stream to test dialog if open
        if self._test_dialog and self._test_dialog.isVisible():
            self._test_dialog.update_telemetry(self.controller.state)

        # Stream to calibration wizard if open
        if self._calibration_dialog and self._calibration_dialog.isVisible():
            self._calibration_dialog.feed_telemetry(steering_state, gesture_res)

        # 8. Record Performance Metrics
        self.performance.end_frame(t_start)
        fps, lat_ms, _, _ = self.performance.get_stats()
        self.badge_perf.set_status(f"FPS: {fps:.1f} | Latency: {lat_ms:.1f} ms", True, "#00E5FF")

    def _check_nfs_heat_tick(self):
        """Checks if NFS Heat process is detected on Windows."""
        is_running, pid = self.watchdog.check_nfs_heat_process()
        if is_running:
            self.badge_nfs.set_status(f"RUNNING (PID: {pid})", True, "#00E676")
            self.banner_nfs.setStyleSheet("""
                QFrame {
                    background-color: #0A2415;
                    border: 1px solid #00FF66;
                    border-radius: 6px;
                }
            """)
            self.lbl_banner_msg.setText(
                f"<b>NFS HEAT DETECTED (PID: {pid}):</b> Press <b>[Alt + Enter]</b> in-game (or set Video to <b>'Borderless'</b>) "
                "so the HUD stays visible on top! Press <b>[F10]</b> to toggle HUD."
            )
        else:
            self.badge_nfs.set_status("NOT DETECTED (READY FOR LAUNCH)", False)
            self.banner_nfs.setStyleSheet("""
                QFrame {
                    background-color: #0E1622;
                    border: 1px solid #00E5FF;
                    border-radius: 6px;
                }
            """)
            self.lbl_banner_msg.setText(
                "<b>NFS HEAT OVERLAY GUIDE:</b> Press <b>[Alt + Enter]</b> in NFS Heat (or set Video to <b>'Borderless'</b>) "
                "so this floating HUD can render directly over your game! Press <b>[F10]</b> to toggle HUD anytime."
            )

    def _open_controller_monitor(self):
        if not self._test_dialog:
            self._test_dialog = ControllerTestDialog(self.controller, self)
        self._test_dialog.show()
        self._test_dialog.raise_()

    def _open_calibration_wizard(self):
        self._calibration_dialog = CalibrationWizardDialog(self.calibration_mgr, self)
        if self._calibration_dialog.exec():
            # Apply calibrated profile to active steering wheel
            p = self.calibration_mgr.profile
            self.steering.neutral_angle = p.neutral_angle
            self.steering.max_angle = p.max_right_angle
            logger.info("Updated steering engine with newly calibrated profile.")

    def _open_settings(self):
        dlg = SettingsDialog("config/settings.json", on_applied=self._on_settings_applied, parent=self)
        dlg.exec()

    def _on_settings_applied(self, cfg):
        # Update camera settings if not running
        if not self.is_tracking:
            cam_cfg = cfg.get("camera", {})
            self.webcam.device_index = cam_cfg.get("device_index", 0)
            self.webcam.target_width = cam_cfg.get("width", 1280)
            self.webcam.target_height = cam_cfg.get("height", 720)
            self.webcam.mirror_horizontal = cam_cfg.get("mirror_horizontal", True)

        # Update steering dynamics with sharp defaults
        steer_cfg = cfg.get("steering", {})
        self.steering.deadzone_angle = steer_cfg.get("deadzone_angle", 1.0)
        self.steering.max_angle = steer_cfg.get("max_angle", 14.0)
        self.steering.sensitivity = steer_cfg.get("sensitivity", 1.40)
        self.steering.smoothing_factor = steer_cfg.get("smoothing_factor", 0.92)
        self.steering.response_curve = steer_cfg.get("response_curve", "progressive_sharp")

        # Update throttle & brake dynamics
        throt_cfg = cfg.get("throttle", {})
        self.recognizer.throttle_smoothing = throt_cfg.get("smoothing_factor", 0.75)

        brake_cfg = cfg.get("brake", {})
        self.recognizer.brake_smoothing = brake_cfg.get("smoothing_factor", 0.85)

        # Update safety
        safe_cfg = cfg.get("safety", {})
        self.watchdog.tracking_loss_timeout_s = safe_cfg.get("tracking_loss_timeout_ms", 250) / 1000.0

    def closeEvent(self, event):
        """Gracefully release camera, virtual controller, and worker threads."""
        self._stop_tracking()
        if self.overlay:
            self.overlay.close()
        if self.tracker:
            self.tracker.release()
        self.controller.close()
        logger.info("Application closed safely.")
        event.accept()
