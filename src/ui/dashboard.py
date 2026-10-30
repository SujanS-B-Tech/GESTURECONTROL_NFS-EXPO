"""
Dashboard Widgets and Telemetry Visualizers for GESTUREDRIVE X.
High-performance Qt custom widgets featuring a dark racing aesthetic,
custom steering wheel rotation gauge, telemetry bars, and camera canvas.
"""

import math
from typing import Optional, Tuple
from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QPainter, QColor, QPen, QBrush, QFont, QImage, QPixmap, QLinearGradient, QRadialGradient
from PySide6.QtWidgets import QWidget, QLabel, QVBoxLayout, QHBoxLayout, QFrame

from src.gestures.steering import SteeringState
from src.gestures.recognizer import FrameGestureResult, HandGesture
from src.controller.virtual_xbox import GamepadState


class VideoDisplayWidget(QWidget):
    """Renders real-time webcam feed with landmark overlays and telemetry overlay."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(640, 360)
        self._pixmap: Optional[QPixmap] = None
        self.setStyleSheet("background-color: #0A0A0E; border: 1px solid #2A2A38; border-radius: 8px;")

    def update_frame(self, frame_rgb, width: int, height: int):
        """Receives RGB frame numpy array and converts to QPixmap for rendering."""
        bytes_per_line = 3 * width
        q_img = QImage(frame_rgb.data, width, height, bytes_per_line, QImage.Format.Format_RGB888)
        self._pixmap = QPixmap.fromImage(q_img)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = self.rect()
        if self._pixmap and not self._pixmap.isNull():
            scaled = self._pixmap.scaled(rect.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            x = (rect.width() - scaled.width()) // 2
            y = (rect.height() - scaled.height()) // 2
            painter.drawPixmap(x, y, scaled)
        else:
            # Standby state
            painter.fillRect(rect, QColor("#0D0D12"))
            painter.setPen(QPen(QColor("#404050"), 1, Qt.PenStyle.DashLine))
            painter.drawRoundedRect(rect.adjusted(10, 10, -10, -10), 8, 8)

            painter.setPen(QColor("#808095"))
            painter.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "CAMERA STREAM STANDBY\nClick 'START TRACKING' to initialize")


class SteeringWheelWidget(QWidget):
    """Futuristic F1/GT3 inspired digital steering wheel arc gauge."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(220, 180)
        self._angle_deg = 0.0
        self._stick_val = 0
        self._active = False

    def set_steering(self, angle_deg: float, stick_val: int, active: bool):
        self._angle_deg = angle_deg
        self._stick_val = stick_val
        self._active = active
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()
        center = QPointF(w / 2.0, h / 2.0 + 10)
        radius = min(w, h) * 0.40

        # Background Dial Ring
        painter.setPen(QPen(QColor("#1E1E28"), 8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawArc(QRectF(center.x() - radius, center.y() - radius, radius * 2, radius * 2), 30 * 16, 120 * 16)

        # Center tick marker
        painter.setPen(QPen(QColor("#505060"), 2))
        painter.drawLine(QPointF(center.x(), center.y() - radius - 8), QPointF(center.x(), center.y() - radius + 8))

        # Active arc indicating current rotation
        if self._active:
            # Clamp display angle to [-45, 45]
            display_angle = max(-45.0, min(45.0, self._angle_deg))
            # Arc in Qt: 90 is 12 o'clock (top)
            # When steering right (positive), arc sweeps clockwise
            start_qt_angle = 90 * 16
            span_qt_angle = int(-display_angle * 16)

            arc_color = QColor("#FF1E27") if abs(self._angle_deg) > 15 else QColor("#00E5FF")
            pen = QPen(arc_color, 8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            painter.drawArc(QRectF(center.x() - radius, center.y() - radius, radius * 2, radius * 2), start_qt_angle, span_qt_angle)

            # Rotating Wheel Handle Indicator
            painter.save()
            painter.translate(center)
            painter.rotate(display_angle)

            # Left handle
            painter.setPen(QPen(QColor("#00E5FF"), 5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.drawLine(QPointF(-radius + 15, 0), QPointF(-radius - 10, 0))

            # Right handle
            painter.setPen(QPen(QColor("#FF1E27"), 5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.drawLine(QPointF(radius - 15, 0), QPointF(radius + 10, 0))

            # Center Hub
            hub_grad = QRadialGradient(0, 0, 18)
            hub_grad.setColorAt(0, QColor("#303040"))
            hub_grad.setColorAt(1, QColor("#14141C"))
            painter.setBrush(QBrush(hub_grad))
            painter.setPen(QPen(QColor("#404050"), 2))
            painter.drawEllipse(QPointF(0, 0), 16, 16)

            painter.restore()
        else:
            # Inactive Center
            painter.setBrush(QBrush(QColor("#181822")))
            painter.setPen(QPen(QColor("#303040"), 2))
            painter.drawEllipse(center, 14, 14)

        # Center Text (Angle & Stick X)
        painter.setFont(QFont("Consolas", 11, QFont.Weight.Bold))
        text_color = QColor("#FFFFFF") if self._active else QColor("#606070")
        painter.setPen(text_color)
        angle_str = f"{self._angle_deg:+.1f}°" if self._active else "CENTERED"
        painter.drawText(QRectF(0, h - 35, w, 20), Qt.AlignmentFlag.AlignCenter, angle_str)

        painter.setFont(QFont("Segoe UI", 8))
        painter.setPen(QColor("#707085"))
        stick_str = f"STICK X: {self._stick_val:+06d}"
        painter.drawText(QRectF(0, h - 18, w, 16), Qt.AlignmentFlag.AlignCenter, stick_str)


class TelemetryBarWidget(QWidget):
    """Vertical analog throttle or brake bar with racing gradient fill."""

    def __init__(self, title: str, color_hex: str = "#FF1E27", parent=None):
        super().__init__(parent)
        self.title = title
        self.color_hex = color_hex
        self._value = 0.0  # 0.0 to 1.0
        self.setMinimumSize(70, 180)

    def set_value(self, val: float):
        self._value = max(0.0, min(1.0, val))
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()
        bar_w = 26
        bar_x = (w - bar_w) // 2
        bar_y = 30
        bar_h = h - 65

        # Header Title
        painter.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        painter.setPen(QColor("#C0C0D0"))
        painter.drawText(QRectF(0, 5, w, 20), Qt.AlignmentFlag.AlignCenter, self.title)

        # Background track
        painter.setBrush(QBrush(QColor("#14141E")))
        painter.setPen(QPen(QColor("#252535"), 1))
        painter.drawRoundedRect(bar_x, bar_y, bar_w, bar_h, 4, 4)

        # Fill level (grows upward from bottom)
        fill_h = int(bar_h * self._value)
        if fill_h > 0:
            fill_y = bar_y + bar_h - fill_h

            grad = QLinearGradient(bar_x, bar_y + bar_h, bar_x, bar_y)
            base_col = QColor(self.color_hex)
            grad.setColorAt(0, base_col.darker(130))
            grad.setColorAt(1, base_col.lighter(120))

            painter.setBrush(QBrush(grad))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(bar_x + 2, fill_y, bar_w - 4, fill_h, 3, 3)

        # Percentage Text
        painter.setFont(QFont("Consolas", 10, QFont.Weight.Bold))
        painter.setPen(QColor(self.color_hex) if self._value > 0.05 else QColor("#606070"))
        pct_text = f"{int(self._value * 100)}%"
        painter.drawText(QRectF(0, h - 30, w, 20), Qt.AlignmentFlag.AlignCenter, pct_text)


class StatusBadge(QFrame):
    """Cyberpunk racing telemetry badge with glowing status dot."""

    def __init__(self, title: str, initial_status: str = "OFFLINE", initial_active: bool = False, parent=None):
        super().__init__(parent)
        self.title = title
        self._status = initial_status
        self._active = initial_active

        self.setStyleSheet("""
            QFrame {
                background-color: #12121A;
                border: 1px solid #20202E;
                border-radius: 6px;
                padding: 6px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(3)

        self.lbl_title = QLabel(title.upper())
        self.lbl_title.setStyleSheet("color: #707085; font-size: 10px; font-weight: bold; font-family: 'Segoe UI';")

        self.lbl_val = QLabel(initial_status)
        self.lbl_val.setStyleSheet("color: #E0E0F0; font-size: 12px; font-weight: bold; font-family: 'Segoe UI';")

        layout.addWidget(self.lbl_title)
        layout.addWidget(self.lbl_val)

    def set_status(self, text: str, is_active: bool, accent_color: str = "#00E5FF"):
        self._status = text
        self._active = is_active
        self.lbl_val.setText(text)
        if is_active:
            self.lbl_val.setStyleSheet(f"color: {accent_color}; font-size: 12px; font-weight: bold; font-family: 'Segoe UI';")
            self.setStyleSheet(f"QFrame {{ background-color: #151522; border: 1px solid {accent_color}55; border-radius: 6px; padding: 6px; }}")
        else:
            self.lbl_val.setStyleSheet("color: #707085; font-size: 12px; font-weight: bold; font-family: 'Segoe UI';")
            self.setStyleSheet("QFrame {{ background-color: #12121A; border: 1px solid #20202E; border-radius: 6px; padding: 6px; }}")

