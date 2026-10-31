"""
Configuration and Settings Panel for GESTUREDRIVE X.
Allows runtime customization of camera parameters, steering sensitivities,
deadzones, response curves, and safety timeouts.
"""

import json
import os
from typing import Dict, Any, Callable, Optional
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
    QComboBox, QSlider, QCheckBox, QPushButton, QGroupBox, QFrame
)

from src.camera.webcam import WebcamCapture
from src.utils.logger import logger


class SettingsDialog(QDialog):
    """Application settings dialog."""

    def __init__(self, config_path: str = "config/settings.json", on_applied: Optional[Callable[[Dict[str, Any]], None]] = None, parent=None):
        super().__init__(parent)
        self.config_path = config_path
        self.on_applied = on_applied

        if not os.path.isabs(self.config_path):
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            self.config_path = os.path.join(base_dir, self.config_path)

        self.setWindowTitle("GESTUREDRIVE X — Settings & Configuration")
        self.setFixedSize(540, 520)
        self.setStyleSheet("""
            QDialog {
                background-color: #0E0E14;
                color: #FFFFFF;
            }
            QLabel {
                font-family: 'Segoe UI';
                color: #C0C0D0;
                font-size: 11px;
            }
            QGroupBox {
                border: 1px solid #252538;
                border-radius: 6px;
                margin-top: 10px;
                font-weight: bold;
                color: #FF1E27;
                padding-top: 14px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 4px;
            }
            QComboBox {
                background-color: #1A1A26;
                border: 1px solid #35354A;
                color: #FFFFFF;
                border-radius: 4px;
                padding: 4px 8px;
            }
            QSlider::groove:horizontal {
                height: 6px;
                background: #1C1C2A;
                border-radius: 3px;
            }
            QSlider::sub-page:horizontal {
                background: #FF1E27;
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: #FFFFFF;
                border: 1px solid #FF1E27;
                width: 14px;
                margin-top: -4px;
                margin-bottom: -4px;
                border-radius: 7px;
            }
            QPushButton {
                background-color: #1F1F2E;
                border: 1px solid #35354A;
                color: #FFFFFF;
                border-radius: 5px;
                padding: 8px 18px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #2D2D42;
                border: 1px solid #00E5FF;
            }
        """)

        self.config = self._load_config()
        self._init_ui()

    def _load_config(self) -> Dict[str, Any]:
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error reading config: {e}")
        return {}

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # 1. Camera Settings Group
        grp_cam = QGroupBox("CAMERA HARDWARE")
        cam_grid = QGridLayout(grp_cam)

        cam_grid.addWidget(QLabel("Camera Device:"), 0, 0)
        self.combo_cam = QComboBox()
        available = WebcamCapture.list_available_cameras()
        for idx in available:
            self.combo_cam.addItem(f"Camera Device {idx}", idx)
        if not available:
            self.combo_cam.addItem("Camera Device 0 (Default)", 0)
        cam_grid.addWidget(self.combo_cam, 0, 1)

        cam_grid.addWidget(QLabel("Resolution:"), 1, 0)
        self.combo_res = QComboBox()
        self.combo_res.addItem("1280 x 720 (High Precision)", (1280, 720))
        self.combo_res.addItem("640 x 480 (Low Latency / Performance)", (640, 480))
        cam_grid.addWidget(self.combo_res, 1, 1)

        self.chk_mirror = QCheckBox("Mirror Horizontal (Recommended)")
        self.chk_mirror.setChecked(self.config.get("camera", {}).get("mirror_horizontal", True))
        cam_grid.addWidget(self.chk_mirror, 2, 0, 1, 2)
        layout.addWidget(grp_cam)

        # 2. Steering Dynamics Group
        grp_steer = QGroupBox("STEERING DYNAMICS")
        steer_grid = QGridLayout(grp_steer)

        steer_cfg = self.config.get("steering", {})

        # Deadzone Slider
        steer_grid.addWidget(QLabel("Deadzone Angle:"), 0, 0)
        self.slider_deadzone = QSlider(Qt.Orientation.Horizontal)
        self.slider_deadzone.setRange(1, 8)  # 1.0 to 8.0 deg
        self.slider_deadzone.setValue(int(steer_cfg.get("deadzone_angle", 2.0)))
        self.lbl_deadzone_val = QLabel(f"{self.slider_deadzone.value()}°")
        self.slider_deadzone.valueChanged.connect(lambda v: self.lbl_deadzone_val.setText(f"{v}°"))
        steer_grid.addWidget(self.slider_deadzone, 0, 1)
        steer_grid.addWidget(self.lbl_deadzone_val, 0, 2)

        # Max Steering Angle Slider
        steer_grid.addWidget(QLabel("Max Lock Angle:"), 1, 0)
        self.slider_max_angle = QSlider(Qt.Orientation.Horizontal)
        self.slider_max_angle.setRange(16, 50)
        self.slider_max_angle.setValue(int(steer_cfg.get("max_angle", 24.0)))
        self.lbl_max_angle_val = QLabel(f"{self.slider_max_angle.value()}°")
        self.slider_max_angle.valueChanged.connect(lambda v: self.lbl_max_angle_val.setText(f"{v}°"))
        steer_grid.addWidget(self.slider_max_angle, 1, 1)
        steer_grid.addWidget(self.lbl_max_angle_val, 1, 2)

        # Steering Sensitivity Slider
        steer_grid.addWidget(QLabel("Sensitivity:"), 2, 0)
        self.slider_sens = QSlider(Qt.Orientation.Horizontal)
        self.slider_sens.setRange(50, 180)  # 0.50 to 1.80
        self.slider_sens.setValue(int(steer_cfg.get("sensitivity", 1.00) * 100))
        self.lbl_sens_val = QLabel(f"{self.slider_sens.value()/100:.2f}x")
        self.slider_sens.valueChanged.connect(lambda v: self.lbl_sens_val.setText(f"{v/100:.2f}x"))
        steer_grid.addWidget(self.slider_sens, 2, 1)
        steer_grid.addWidget(self.lbl_sens_val, 2, 2)

        # Steering Response Curve
        steer_grid.addWidget(QLabel("Response Curve:"), 3, 0)
        self.combo_curve = QComboBox()
        self.combo_curve.addItem("Hypercar Precision (Smooth S-Curve)", "hypercar_precision")
        self.combo_curve.addItem("Cubic (Progressive High Center Precision)", "cubic")
        self.combo_curve.addItem("Progressive Sharp (Snappy Turn-in)", "progressive_sharp")
        self.combo_curve.addItem("Linear (Direct 1:1)", "linear")
        self.combo_curve.addItem("Exponential (Fast Turn-in)", "exponential")
        steer_grid.addWidget(self.combo_curve, 3, 1, 1, 2)

        layout.addWidget(grp_steer)

        # 3. Safety Watchdog Group
        grp_safety = QGroupBox("SAFETY WATCHDOG")
        safe_grid = QGridLayout(grp_safety)
        safe_cfg = self.config.get("safety", {})

        safe_grid.addWidget(QLabel("Tracking Loss Cutoff:"), 0, 0)
        self.slider_safety_ms = QSlider(Qt.Orientation.Horizontal)
        self.slider_safety_ms.setRange(150, 600)  # 150ms to 600ms
        self.slider_safety_ms.setValue(int(safe_cfg.get("tracking_loss_timeout_ms", 250)))
        self.lbl_safety_val = QLabel(f"{self.slider_safety_ms.value()} ms")
        self.slider_safety_ms.valueChanged.connect(lambda v: self.lbl_safety_val.setText(f"{v} ms"))
        safe_grid.addWidget(self.slider_safety_ms, 0, 1)
        safe_grid.addWidget(self.lbl_safety_val, 0, 2)

        layout.addWidget(grp_safety)

        # Action Buttons
        btn_layout = QHBoxLayout()
        btn_cancel = QPushButton("CANCEL")
        btn_cancel.clicked.connect(self.reject)

        btn_save = QPushButton("SAVE & APPLY")
        btn_save.setStyleSheet("background-color: #C00810; border: none;")
        btn_save.clicked.connect(self._save_and_apply)

        btn_layout.addWidget(btn_cancel)
        btn_layout.addStretch()
        btn_layout.addWidget(btn_save)
        layout.addLayout(btn_layout)

    def _save_and_apply(self):
        res_val = self.combo_res.currentData()
        self.config["camera"]["device_index"] = self.combo_cam.currentData()
        self.config["camera"]["width"] = res_val[0]
        self.config["camera"]["height"] = res_val[1]
        self.config["camera"]["mirror_horizontal"] = self.chk_mirror.isChecked()

        self.config["steering"]["deadzone_angle"] = float(self.slider_deadzone.value())
        self.config["steering"]["max_angle"] = float(self.slider_max_angle.value())
        self.config["steering"]["sensitivity"] = float(self.slider_sens.value()) / 100.0
        self.config["steering"]["response_curve"] = self.combo_curve.currentData()

        self.config["safety"]["tracking_loss_timeout_ms"] = self.slider_safety_ms.value()

        try:
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=2)
            logger.info("Settings saved successfully.")
        except Exception as e:
            logger.error(f"Error saving settings: {e}")

        if self.on_applied:
            self.on_applied(self.config)

        self.accept()

