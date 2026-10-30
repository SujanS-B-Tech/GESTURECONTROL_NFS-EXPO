"""
Guided Calibration Wizard for GESTUREDRIVE X.
Step-by-step interactive configuration of natural hand position, steering limits,
and gesture sensitivities.
"""

import time
from typing import Optional, Callable
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QProgressBar, QStackedWidget, QWidget, QFrame
)

from src.gestures.calibration import CalibrationManager, CalibrationProfile
from src.gestures.steering import SteeringState
from src.gestures.recognizer import FrameGestureResult


class CalibrationWizardDialog(QDialog):
    """Multi-step guided calibration dialog."""

    STEPS = [
        ("Step 1 of 6: Neutral Position", "Hold both hands in your natural, comfortable 9 and 3 o'clock steering position. Keep hands level.", "neutral"),
        ("Step 2 of 6: Left Steering Lock", "Turn your virtual steering wheel comfortably to your maximum left turn position.", "left_lock"),
        ("Step 3 of 6: Right Steering Lock", "Turn your virtual steering wheel comfortably to your maximum right turn position.", "right_lock"),
        ("Step 4 of 6: Acceleration Clench", "Form a tight closed fist with your Right hand to calibrate full throttle depth.", "throttle"),
        ("Step 5 of 6: Brake Open Palm", "Open your Left hand wide with fingers spread to calibrate full braking extension.", "brake"),
        ("Step 6 of 6: Verification & Save", "Calibration complete! Test your range of motion below, then save your profile.", "verify")
    ]

    def __init__(self, manager: CalibrationManager, parent=None):
        super().__init__(parent)
        self.manager = manager
        self.setWindowTitle("GESTUREDRIVE X — Guided Calibration Wizard")
        self.setFixedSize(580, 420)
        self.setStyleSheet("""
            QDialog {
                background-color: #0E0E14;
                color: #FFFFFF;
            }
            QLabel {
                font-family: 'Segoe UI';
                color: #D0D0E0;
            }
            QPushButton {
                background-color: #1E1E2C;
                border: 1px solid #35354A;
                color: #FFFFFF;
                border-radius: 6px;
                padding: 10px 20px;
                font-weight: bold;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #2E2E42;
                border: 1px solid #00E5FF;
            }
            QProgressBar {
                background-color: #14141E;
                border: 1px solid #282838;
                border-radius: 4px;
                text-align: center;
                color: #FFFFFF;
                font-weight: bold;
            }
            QProgressBar::chunk {
                background-color: #FF1E27;
                border-radius: 3px;
            }
        """)

        self.current_step_idx = 0
        self._is_sampling = False
        self._sample_countdown = 3
        self._sample_duration = 30  # 30 frames
        self._sample_counter = 0

        self._latest_steering: Optional[SteeringState] = None
        self._latest_gestures: Optional[FrameGestureResult] = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(16)

        # Header Title
        self.lbl_step_title = QLabel(self.STEPS[0][0])
        self.lbl_step_title.setStyleSheet("color: #FF1E27; font-size: 16px; font-weight: bold;")
        layout.addWidget(self.lbl_step_title)

        # Instruction Card
        card = QFrame()
        card.setStyleSheet("background-color: #141420; border: 1px solid #242436; border-radius: 8px; padding: 14px;")
        card_layout = QVBoxLayout(card)

        self.lbl_instruction = QLabel(self.STEPS[0][1])
        self.lbl_instruction.setWordWrap(True)
        self.lbl_instruction.setStyleSheet("font-size: 13px; line-height: 1.4; color: #E0E0F0;")
        card_layout.addWidget(self.lbl_instruction)

        self.lbl_live_metric = QLabel("Current Metric: Waiting for hands...")
        self.lbl_live_metric.setStyleSheet("color: #00E5FF; font-size: 12px; font-family: 'Consolas'; margin-top: 8px;")
        card_layout.addWidget(self.lbl_live_metric)

        layout.addWidget(card)

        # Progress / Countdown Bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("Ready to record")
        layout.addWidget(self.progress_bar)

        # Buttons
        btn_layout = QHBoxLayout()
        self.btn_action = QPushButton("RECORD SAMPLE (3s)")
        self.btn_action.setStyleSheet("background-color: #C00810; border: none; padding: 12px 24px;")
        self.btn_action.clicked.connect(self._on_action_clicked)

        self.btn_skip = QPushButton("SKIP / CANCEL")
        self.btn_skip.clicked.connect(self.reject)

        btn_layout.addWidget(self.btn_skip)
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_action)
        layout.addLayout(btn_layout)

        # Timer for sampling
        self.sample_timer = QTimer(self)
        self.sample_timer.setInterval(50)  # 20 Hz
        self.sample_timer.timeout.connect(self._on_sample_tick)

    def feed_telemetry(self, steering: SteeringState, gestures: FrameGestureResult):
        """Called by main loop to stream real-time tracking data into calibration."""
        self._latest_steering = steering
        self._latest_gestures = gestures

        if not self._is_sampling:
            step_key = self.STEPS[self.current_step_idx][2]
            if step_key in ["neutral", "left_lock", "right_lock"]:
                if steering.active:
                    self.lbl_live_metric.setText(f"Live Wheel Tilt: {steering.raw_angle_deg:+.1f}°")
                else:
                    self.lbl_live_metric.setText("Position both hands in front of the camera...")
            elif step_key == "throttle":
                if gestures.right:
                    self.lbl_live_metric.setText(f"Right Hand Curl: {gestures.right.overall_curl:.2f} (Fist: {gestures.right.is_fist})")
            elif step_key == "brake":
                if gestures.left:
                    self.lbl_live_metric.setText(f"Left Hand Extension: {gestures.left.overall_extension:.2f} (Open: {gestures.left.is_open})")

    def _on_action_clicked(self):
        step_key = self.STEPS[self.current_step_idx][2]
        if step_key == "verify":
            # Save and exit
            self.manager.save_profile()
            self.accept()
            return

        if not self._is_sampling:
            self._is_sampling = True
            self.manager.start_recording()
            self._sample_counter = 0
            self.progress_bar.setFormat("Recording samples... Hold steady!")
            self.btn_action.setEnabled(False)
            self.sample_timer.start()

    def _on_sample_tick(self):
        if not self._is_sampling:
            return

        self._sample_counter += 1
        pct = int((self._sample_counter / self._sample_duration) * 100)
        self.progress_bar.setValue(pct)

        step_key = self.STEPS[self.current_step_idx][2]
        if step_key in ["neutral", "left_lock", "right_lock"] and self._latest_steering and self._latest_steering.active:
            self.manager.record_sample(self._latest_steering.raw_angle_deg)
        elif step_key == "throttle" and self._latest_gestures and self._latest_gestures.right:
            self.manager.record_sample(self._latest_gestures.right.overall_curl)
        elif step_key == "brake" and self._latest_gestures and self._latest_gestures.left:
            self.manager.record_sample(self._latest_gestures.left.overall_extension)

        if self._sample_counter >= self._sample_duration:
            self.sample_timer.stop()
            self._is_sampling = False
            self._finalize_step(step_key)

    def _finalize_step(self, step_key: str):
        val = self.manager.compute_robust_angle()
        if step_key == "neutral":
            self.manager.profile.neutral_angle = round(val, 2)
        elif step_key == "left_lock":
            self.manager.profile.max_left_angle = round(abs(val - self.manager.profile.neutral_angle), 2)
        elif step_key == "right_lock":
            self.manager.profile.max_right_angle = round(abs(val - self.manager.profile.neutral_angle), 2)
        elif step_key == "throttle":
            self.manager.profile.fist_curl_threshold = round(val * 0.9, 2)
        elif step_key == "brake":
            self.manager.profile.open_palm_extension_threshold = round(val * 0.9, 2)

        # Move to next step
        self.current_step_idx += 1
        if self.current_step_idx >= len(self.STEPS):
            self.manager.save_profile()
            self.accept()
            return

        title, desc, next_key = self.STEPS[self.current_step_idx]
        self.lbl_step_title.setText(title)
        self.lbl_instruction.setText(desc)
        self.progress_bar.setValue(0)

        if next_key == "verify":
            p = self.manager.profile
            summary = (
                f"Calibrated Neutral Angle: {p.neutral_angle:+.1f}°\n"
                f"Left Lock Range: {p.max_left_angle:.1f}° | Right Lock Range: {p.max_right_angle:.1f}°\n"
                f"Fist Throttle Threshold: {p.fist_curl_threshold:.2f} | Brake Extension: {p.open_palm_extension_threshold:.2f}"
            )
            self.lbl_live_metric.setText(summary)
            self.progress_bar.setFormat("Profile ready to save")
            self.progress_bar.setValue(100)
            self.btn_action.setText("SAVE & APPLY CALIBRATION")
            self.btn_action.setEnabled(True)
        else:
            self.progress_bar.setFormat("Ready for next step")
            self.btn_action.setText("RECORD SAMPLE (3s)")
            self.btn_action.setEnabled(True)

