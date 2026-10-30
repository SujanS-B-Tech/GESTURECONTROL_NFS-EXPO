"""
Standalone Controller Visualizer and Testing Mode for GESTUREDRIVE X.
Permits complete verification of all analog axes, triggers, and digital buttons
without launching Need for Speed Heat.
"""

from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QPainter, QColor, QPen, QBrush, QFont, QRadialGradient
from PySide6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGridLayout,
    QProgressBar, QPushButton, QFrame, QGroupBox
)

from src.controller.virtual_xbox import GamepadState, VirtualXboxController


class GamepadVisualizerWidget(QWidget):
    """Draws a live 2D diagram of the Xbox 360 controller highlighting pressed buttons and stick positions."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(420, 260)
        self.state = GamepadState()

    def update_state(self, state: GamepadState):
        self.state = state
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()
        center_x, center_y = w / 2.0, h / 2.0

        # Draw Controller Outline
        painter.setBrush(QBrush(QColor("#161622")))
        painter.setPen(QPen(QColor("#35354A"), 2))
        body_rect = QRectF(center_x - 170, center_y - 90, 340, 180)
        painter.drawRoundedRect(body_rect, 40, 40)

        # 1. Left Stick (Steering)
        ls_center = QPointF(center_x - 90, center_y - 20)
        painter.setBrush(QBrush(QColor("#0E0E16")))
        painter.setPen(QPen(QColor("#3A3A50"), 2))
        painter.drawEllipse(ls_center, 35, 35)

        # Left stick thumb position offset (-32768 to 32767 mapped to -22 to +22 px)
        stick_offset_x = (self.state.left_stick_x / 32767.0) * 20.0
        stick_offset_y = -(self.state.left_stick_y / 32767.0) * 20.0
        thumb_pos = QPointF(ls_center.x() + stick_offset_x, ls_center.y() + stick_offset_y)

        # Thumb cap
        cap_col = QColor("#00E5FF") if self.state.button_lsb else QColor("#28283C")
        painter.setBrush(QBrush(cap_col))
        painter.setPen(QPen(QColor("#00E5FF") if self.state.button_lsb else QColor("#505068"), 2))
        painter.drawEllipse(thumb_pos, 16, 16)

        # 2. ABXY Face Buttons
        btn_center_x = center_x + 95
        btn_center_y = center_y - 20

        # Button Y (Top, Yellow, Camera)
        self._draw_button(painter, QPointF(btn_center_x, btn_center_y - 28), "Y", self.state.button_y, "#FFD700")
        # Button A (Bottom, Green, Nitro)
        self._draw_button(painter, QPointF(btn_center_x, btn_center_y + 28), "A", self.state.button_a, "#00E676")
        # Button X (Left, Blue, Handbrake)
        self._draw_button(painter, QPointF(btn_center_x - 28, btn_center_y), "X", self.state.button_x, "#2979FF")
        # Button B (Right, Red)
        self._draw_button(painter, QPointF(btn_center_x + 28, btn_center_y), "B", self.state.button_b, "#FF1744")

        # 3. Center Guide & Menu/Start
        # Xbox Guide / Menu
        self._draw_button(painter, QPointF(center_x - 30, center_y - 15), "BACK", self.state.button_back, "#B0B0C0", radius=10, font_size=6)
        self._draw_button(painter, QPointF(center_x + 30, center_y - 15), "START", self.state.button_start, "#00E5FF", radius=10, font_size=6)

        # 4. Triggers (Top Bumper / Triggers)
        # Left Trigger (LT - Brake)
        lt_val_pct = self.state.left_trigger / 255.0
        painter.setBrush(QBrush(QColor("#0E0E16")))
        painter.setPen(QPen(QColor("#3A3A50"), 1))
        lt_rect = QRectF(center_x - 130, center_y - 82, 60, 16)
        painter.drawRoundedRect(lt_rect, 3, 3)
        if lt_val_pct > 0.01:
            painter.setBrush(QBrush(QColor("#00E5FF")))
            painter.drawRoundedRect(QRectF(lt_rect.x(), lt_rect.y(), lt_rect.width() * lt_val_pct, lt_rect.height()), 3, 3)
        painter.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
        painter.setPen(QColor("#FFFFFF"))
        painter.drawText(lt_rect, Qt.AlignmentFlag.AlignCenter, f"LT: {self.state.left_trigger}")

        # Right Trigger (RT - Throttle)
        rt_val_pct = self.state.right_trigger / 255.0
        rt_rect = QRectF(center_x + 70, center_y - 82, 60, 16)
        painter.setBrush(QBrush(QColor("#0E0E16")))
        painter.setPen(QPen(QColor("#3A3A50"), 1))
        painter.drawRoundedRect(rt_rect, 3, 3)
        if rt_val_pct > 0.01:
            painter.setBrush(QBrush(QColor("#FF1E27")))
            painter.drawRoundedRect(QRectF(rt_rect.x(), rt_rect.y(), rt_rect.width() * rt_val_pct, rt_rect.height()), 3, 3)
        painter.drawText(rt_rect, Qt.AlignmentFlag.AlignCenter, f"RT: {self.state.right_trigger}")

    def _draw_button(self, painter: QPainter, pos: QPointF, label: str, active: bool, color_hex: str, radius=12, font_size=9):
        col = QColor(color_hex)
        if active:
            painter.setBrush(QBrush(col))
            painter.setPen(QPen(QColor("#FFFFFF"), 2))
        else:
            painter.setBrush(QBrush(QColor("#20202E")))
            painter.setPen(QPen(col.darker(150), 1))

        painter.drawEllipse(pos, radius, radius)
        painter.setFont(QFont("Segoe UI", font_size, QFont.Weight.Bold))
        painter.setPen(QColor("#FFFFFF") if active else col)
        painter.drawText(QRectF(pos.x() - radius, pos.y() - radius, radius * 2, radius * 2), Qt.AlignmentFlag.AlignCenter, label)


class ControllerTestDialog(QDialog):
    """Standalone dialog for testing and verifying all Xbox controller inputs in real time."""

    def __init__(self, controller: VirtualXboxController, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.setWindowTitle("GESTUREDRIVE X — Standalone Controller Verification")
        self.setFixedSize(540, 480)
        self.setStyleSheet("""
            QDialog {
                background-color: #0F0F14;
                color: #E0E0E8;
            }
            QLabel {
                color: #C0C0D0;
                font-family: 'Segoe UI';
            }
            QPushButton {
                background-color: #1F1F2C;
                border: 1px solid #35354A;
                color: #FFFFFF;
                border-radius: 5px;
                padding: 8px 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #2D2D40;
                border: 1px solid #00E5FF;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # Header
        lbl_head = QLabel("VIRTUAL XBOX 360 CONTROLLER LIVE MONITOR")
        lbl_head.setStyleSheet("color: #FF1E27; font-size: 14px; font-weight: bold;")
        layout.addWidget(lbl_head)

        lbl_sub = QLabel("Move hands or trigger gestures to verify that analog axes and buttons illuminate.")
        lbl_sub.setStyleSheet("color: #707085; font-size: 11px;")
        layout.addWidget(lbl_sub)

        # 2D Controller Visualizer
        self.visualizer = GamepadVisualizerWidget(self)
        layout.addWidget(self.visualizer)

        # Status readout grid
        grid_frame = QFrame()
        grid_frame.setStyleSheet("background-color: #14141E; border: 1px solid #252535; border-radius: 6px; padding: 6px;")
        grid = QGridLayout(grid_frame)

        self.lbl_stick = QLabel("Left Stick X: 0 (Centered)")
        self.lbl_throttle = QLabel("Throttle (RT): 0 (0%)")
        self.lbl_brake = QLabel("Brake (LT): 0 (0%)")
        self.lbl_nitro = QLabel("Nitrous (A): Inactive")
        self.lbl_handbrake = QLabel("Handbrake (X): Inactive")
        self.lbl_camera = QLabel("Camera (Y): Inactive")

        grid.addWidget(self.lbl_stick, 0, 0)
        grid.addWidget(self.lbl_throttle, 0, 1)
        grid.addWidget(self.lbl_brake, 1, 0)
        grid.addWidget(self.lbl_nitro, 1, 1)
        grid.addWidget(self.lbl_handbrake, 2, 0)
        grid.addWidget(self.lbl_camera, 2, 1)

        layout.addWidget(grid_frame)

        # Hardware connection badge
        self.lbl_driver = QLabel()
        if self.controller.driver_installed:
            self.lbl_driver.setText("✓ VIRTUAL CONTROLLER ACTIVE — ViGEmBus driver is functioning correctly.")
            self.lbl_driver.setStyleSheet("color: #00E676; font-size: 11px; font-weight: bold;")
        else:
            self.lbl_driver.setText("⚠ VIRTUAL DRIVER OFFLINE — Run 'install_driver.bat' as Admin to send signals to NFS Heat.")
            self.lbl_driver.setStyleSheet("color: #FF9100; font-size: 11px; font-weight: bold;")
        layout.addWidget(self.lbl_driver)

        # Close button
        btn_close = QPushButton("CLOSE MONITOR")
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close)

    def update_telemetry(self, state: GamepadState):
        """Update live telemetry readout and visualizer."""
        self.visualizer.update_state(state)
        self.lbl_stick.setText(f"Left Stick X: {state.left_stick_x:+06d}")
        self.lbl_throttle.setText(f"Throttle (RT): {state.right_trigger} ({int(state.right_trigger/2.55)}%)")
        self.lbl_brake.setText(f"Brake (LT): {state.left_trigger} ({int(state.left_trigger/2.55)}%)")
        self.lbl_nitro.setText(f"Nitrous (A): {'ACTIVE' if state.button_a else 'Inactive'}")
        self.lbl_handbrake.setText(f"Handbrake (X): {'ACTIVE' if state.button_x else 'Inactive'}")
        self.lbl_camera.setText(f"Camera (Y): {'ACTIVE' if state.button_y else 'Inactive'}")

