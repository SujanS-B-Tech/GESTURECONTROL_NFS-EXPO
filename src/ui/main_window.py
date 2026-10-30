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
            deadzone_angle=profile.deadzone_angle,
            max_angle=profile.max_right_angle
        )
        self.recognizer = GestureRecognizer()
        self.controller = VirtualXboxController()
        self.mapper = InputMapper(self.controller)
        self.watchdog = SafetyWatchdog(self.controller)

        # Active dialog references
        self._test_dialog: Optional[ControllerTestDialog] = None
        self._calibration_dialog: Optional[CalibrationWizardDialog] = None

        # State flags
        self.is_tracking = False

        # Build UI layout
        self._init_ui()

        # Keyboard shortcuts
        self._setup_shortcuts()

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

        # 2. Main Content Splitter (Left: Live Video & Controls, Right: Telemetry & Status)
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

        # Top Buttons: Test Controller, Calibrate, Settings
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

        # Driving Intent & Action Badge (Nitro, Drift Handbrake, Drive, Reverse)
        if gesture_res.one_open_one_closed_drift:
            self.badge_actions.set_status("DRIFT HANDBRAKE (X)", True, "#FF9100")
        elif self.controller.state.button_a:
            self.badge_actions.set_status("NITROUS BOOST (A)", True, "#00E676")
        elif gesture_res.both_open_reverse:
            self.badge_actions.set_status("STOP & REVERSE (LT)", True, "#00E5FF")
        elif gesture_res.both_closed_drive:
            self.badge_actions.set_status("DRIVING FORWARD (RT)", True, "#00FF66")
        else:
            self.badge_actions.set_status("COASTING / NEUTRAL", False)

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
        else:
            self.badge_nfs.set_status("NOT DETECTED (READY FOR LAUNCH)", False)

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

        # Update steering dynamics
        steer_cfg = cfg.get("steering", {})
        self.steering.deadzone_angle = steer_cfg.get("deadzone_angle", 3.0)
        self.steering.max_angle = steer_cfg.get("max_angle", 42.0)
        self.steering.sensitivity = steer_cfg.get("sensitivity", 1.15)
        self.steering.response_curve = steer_cfg.get("response_curve", "cubic")

        # Update safety
        safe_cfg = cfg.get("safety", {})
        self.watchdog.tracking_loss_timeout_s = safe_cfg.get("tracking_loss_timeout_ms", 250) / 1000.0

    def closeEvent(self, event):
        """Gracefully release camera, virtual controller, and worker threads."""
        self._stop_tracking()
        if self.tracker:
            self.tracker.release()
        self.controller.close()
        logger.info("Application closed safely.")
        event.accept()
