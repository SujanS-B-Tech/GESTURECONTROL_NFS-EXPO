"""
Persistent In-Game Floating Picture-in-Picture (PiP) Overlay HUD for GESTUREDRIVE X.
Engineered with native 64-bit Win32 HWND_TOPMOST, WS_EX_TOOLWINDOW, and WS_EX_NOACTIVATE
so it floats reliably over Need for Speed Heat (in Borderless / Windowed mode) without
stealing game focus or minimizing.
"""

import sys
from typing import Optional, Tuple
import numpy as np

from PySide6.QtCore import Qt, QPoint, QRectF, QTimer
from PySide6.QtGui import QPainter, QColor, QPen, QBrush, QFont, QImage, QPixmap, QScreen
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame, QApplication
)

from src.gestures.steering import SteeringState
from src.gestures.recognizer import FrameGestureResult
from src.controller.virtual_xbox import GamepadState

# Windows 64-bit API configuration
if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32

    # SetWindowPos types
    user32.SetWindowPos.argtypes = [
        wintypes.HWND, wintypes.HWND,
        ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
        wintypes.UINT
    ]
    user32.SetWindowPos.restype = wintypes.BOOL

    # 64-bit / 32-bit WindowLong compatibility
    if hasattr(user32, "GetWindowLongPtrW"):
        user32.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
        user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
        user32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
        user32.SetWindowLongPtrW.restype = ctypes.c_ssize_t
        _get_window_long = user32.GetWindowLongPtrW
        _set_window_long = user32.SetWindowLongPtrW
    else:
        user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
        user32.GetWindowLongW.restype = ctypes.c_long
        user32.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]
        user32.SetWindowLongW.restype = ctypes.c_long
        _get_window_long = user32.GetWindowLongW
        _set_window_long = user32.SetWindowLongW

    HWND_TOPMOST = wintypes.HWND(-1)
    SWP_NOSIZE = 0x0001
    SWP_NOMOVE = 0x0002
    SWP_NOACTIVATE = 0x0010
    SWP_SHOWWINDOW = 0x0040
    GWL_EXSTYLE = -20
    WS_EX_TOPMOST = 0x00000008
    WS_EX_NOACTIVATE = 0x08000000
    WS_EX_TOOLWINDOW = 0x00000080


class InGameOverlayHUD(QWidget):
    """
    Hardware-level always-on-top floating mini-HUD designed for fullscreen borderless games.
    Uses Win32 HWND_TOPMOST enforcement so NFS Heat cannot hide or minimize it.
    """

    def __init__(self, parent=None):
        # Qt.WindowType.Tool ensures Windows treats this as a floating tool palette
        # which does NOT minimize when a borderless/windowed game receives focus.
        super().__init__(
            None,
            Qt.WindowType.Tool |
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.WindowDoesNotAcceptFocus
        )

        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        self.setWindowTitle("GESTUREDRIVE X — In-Game HUD")
        self.setFixedSize(340, 245)

        self._drag_pos = QPoint()
        self._pixmap: Optional[QPixmap] = None
        self._steering_angle = 0.0
        self._corner_idx = 0  # 0: Top-Right, 1: Top-Left, 2: Bottom-Left, 3: Bottom-Right
        self._opacities = [0.95, 0.80, 1.0]
        self._opacity_idx = 0

        self._init_ui()

        # Win32 Periodic Topmost Re-assert Timer (400ms)
        # Prevents DirectX full-window swap chains from burying the overlay
        self._topmost_timer = QTimer(self)
        self._topmost_timer.setInterval(400)
        self._topmost_timer.timeout.connect(self._enforce_topmost)
        self._topmost_timer.start()

    def _init_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(6, 6, 6, 6)
        root_layout.setSpacing(4)

        # Container Frame
        self.card = QFrame(self)
        self.card.setStyleSheet("""
            QFrame {
                background-color: rgba(10, 10, 16, 240);
                border: 2px solid #00E5FF;
                border-radius: 10px;
            }
        """)
        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(8, 6, 8, 6)
        card_layout.setSpacing(4)

        # Header Title bar with drag handle and corner snap
        top_bar = QHBoxLayout()
        top_bar.setContentsMargins(0, 0, 0, 0)
        top_bar.setSpacing(6)

        lbl_title = QLabel("GESTUREDRIVE X")
        lbl_title.setStyleSheet("color: #00E5FF; font-size: 10px; font-weight: 900; letter-spacing: 1px;")
        top_bar.addWidget(lbl_title)
        top_bar.addStretch()

        self.lbl_fps = QLabel("FPS: 30")
        self.lbl_fps.setStyleSheet("color: #707085; font-size: 9px; font-family: 'Consolas';")
        top_bar.addWidget(self.lbl_fps)

        # Opacity Cycle button
        btn_opacity = QPushButton("◐")
        btn_opacity.setToolTip("Cycle Opacity (95% / 80% / 100%)")
        btn_opacity.setFixedSize(20, 20)
        btn_opacity.setStyleSheet("""
            QPushButton {
                background: #181824;
                color: #00E5FF;
                font-weight: bold;
                border: 1px solid #282838;
                border-radius: 3px;
                font-size: 11px;
            }
            QPushButton:hover {
                background: #242438;
                border: 1px solid #00E5FF;
            }
        """)
        btn_opacity.clicked.connect(self._cycle_opacity)
        top_bar.addWidget(btn_opacity)

        # Corner Snap button
        btn_snap = QPushButton("◰")
        btn_snap.setToolTip("Snap to Next Corner (Top-Right, Top-Left, Bottom-Left, Bottom-Right)")
        btn_snap.setFixedSize(20, 20)
        btn_snap.setStyleSheet("""
            QPushButton {
                background: #181824;
                color: #FFFFFF;
                font-weight: bold;
                border: 1px solid #282838;
                border-radius: 3px;
                font-size: 11px;
            }
            QPushButton:hover {
                background: #242438;
                border: 1px solid #FF1E27;
            }
        """)
        btn_snap.clicked.connect(self.snap_next_corner)
        top_bar.addWidget(btn_snap)

        # Close button
        btn_close = QPushButton("✕")
        btn_close.setToolTip("Hide Overlay HUD (F10 in-game)")
        btn_close.setFixedSize(20, 20)
        btn_close.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #A0A0B0;
                font-weight: bold;
                border: none;
                font-size: 12px;
            }
            QPushButton:hover {
                color: #FF1E27;
            }
        """)
        btn_close.clicked.connect(self.hide)
        top_bar.addWidget(btn_close)
        card_layout.addLayout(top_bar)

        # Video Canvas
        self.video_label = QLabel()
        self.video_label.setFixedSize(308, 150)
        self.video_label.setStyleSheet("background-color: #08080C; border: 1px solid #20202C; border-radius: 6px;")
        self.video_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(self.video_label)

        # Bottom Telemetry Bar
        bot_bar = QHBoxLayout()
        bot_bar.setContentsMargins(0, 0, 0, 0)

        self.lbl_steer = QLabel("STEER: 0.0°")
        self.lbl_steer.setStyleSheet("color: #FFFFFF; font-size: 11px; font-weight: bold; font-family: 'Consolas';")
        bot_bar.addWidget(self.lbl_steer)
        bot_bar.addStretch()

        self.lbl_mode = QLabel("DRIVE (RT)")
        self.lbl_mode.setStyleSheet("color: #00FF66; font-size: 11px; font-weight: bold;")
        bot_bar.addWidget(self.lbl_mode)

        card_layout.addLayout(bot_bar)

        # Hint text for Borderless mode
        self.lbl_tip = QLabel("TIP: Press [Alt + Enter] in NFS Heat for Borderless Mode")
        self.lbl_tip.setStyleSheet("color: #666680; font-size: 8px;")
        self.lbl_tip.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(self.lbl_tip)

        root_layout.addWidget(self.card)

    def showEvent(self, event):
        super().showEvent(event)
        self._enforce_topmost()

    def _cycle_opacity(self):
        """Cycles window opacity level."""
        self._opacity_idx = (self._opacity_idx + 1) % len(self._opacities)
        op = self._opacities[self._opacity_idx]
        self.setWindowOpacity(op)

    def snap_next_corner(self):
        """Cycles placement across the four corners of the active screen."""
        self._corner_idx = (self._corner_idx + 1) % 4
        self.snap_to_corner(self._corner_idx)

    def snap_to_corner(self, corner: int):
        """
        Positions the HUD in the specified corner.
        0: Top-Right
        1: Top-Left
        2: Bottom-Left
        3: Bottom-Right
        """
        self._corner_idx = corner % 4
        screen = QApplication.primaryScreen()
        if not screen:
            return
        geo = screen.availableGeometry()

        margin_x = 24
        margin_y = 40
        w = self.width()
        h = self.height()

        if self._corner_idx == 0:  # Top-Right
            x = geo.x() + geo.width() - w - margin_x
            y = geo.y() + margin_y
        elif self._corner_idx == 1:  # Top-Left
            x = geo.x() + margin_x
            y = geo.y() + margin_y
        elif self._corner_idx == 2:  # Bottom-Left
            x = geo.x() + margin_x
            y = geo.y() + geo.height() - h - margin_y
        else:  # Bottom-Right
            x = geo.x() + geo.width() - w - margin_x
            y = geo.y() + geo.height() - h - margin_y

        self.move(int(x), int(y))
        self._enforce_topmost()

    def _enforce_topmost(self):
        """Forces the window to the absolute top of the Windows Z-Order."""
        if not self.isVisible():
            return

        # Qt level raise
        self.raise_()

        # Windows 64-bit level HWND_TOPMOST enforcement
        if sys.platform == "win32":
            try:
                hwnd = int(self.winId())
                if hwnd:
                    old_style = _get_window_long(hwnd, GWL_EXSTYLE)
                    new_style = old_style | WS_EX_TOPMOST | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW
                    if new_style != old_style:
                        _set_window_long(hwnd, GWL_EXSTYLE, new_style)

                    user32.SetWindowPos(
                        hwnd,
                        HWND_TOPMOST,
                        0, 0, 0, 0,
                        SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_SHOWWINDOW
                    )
            except Exception:
                pass

    def update_telemetry(
        self,
        frame_rgb: np.ndarray,
        steering: SteeringState,
        gestures: FrameGestureResult,
        gamepad: GamepadState,
        fps: float
    ):
        """Update live camera image and racing telemetry inside the floating HUD."""
        # Convert RGB image to Pixmap
        h, w, _ = frame_rgb.shape
        bytes_per_line = 3 * w
        q_img = QImage(frame_rgb.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
        pix = QPixmap.fromImage(q_img).scaled(
            self.video_label.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.FastTransformation
        )
        self.video_label.setPixmap(pix)

        # Update Steering Text
        self._steering_angle = steering.relative_angle_deg
        self.lbl_steer.setText(f"STEER: {self._steering_angle:+.1f}°")
        if abs(self._steering_angle) > 2.0:
            steer_col = "#00E5FF" if self._steering_angle < 0 else "#FF1E27"
            self.lbl_steer.setStyleSheet(f"color: {steer_col}; font-size: 11px; font-weight: bold; font-family: 'Consolas';")
        else:
            self.lbl_steer.setStyleSheet("color: #A0A0B0; font-size: 11px; font-weight: bold; font-family: 'Consolas';")

        # Update Mode Badge and Card border
        if gestures.one_open_one_closed_drift:
            self.lbl_mode.setText("DRIFT (X)")
            self.lbl_mode.setStyleSheet("color: #FF9100; font-size: 11px; font-weight: bold;")
            self.card.setStyleSheet("QFrame { background-color: rgba(10, 10, 16, 240); border: 2px solid #FF9100; border-radius: 10px; }")
        elif gamepad.button_a:
            self.lbl_mode.setText("NITRO (A)")
            self.lbl_mode.setStyleSheet("color: #00E5FF; font-size: 11px; font-weight: bold;")
            self.card.setStyleSheet("QFrame { background-color: rgba(10, 10, 16, 240); border: 2px solid #00E5FF; border-radius: 10px; }")
        elif gestures.both_open_reverse:
            self.lbl_mode.setText("REVERSE (LT)")
            self.lbl_mode.setStyleSheet("color: #00E5FF; font-size: 11px; font-weight: bold;")
            self.card.setStyleSheet("QFrame { background-color: rgba(10, 10, 16, 240); border: 2px solid #00E5FF; border-radius: 10px; }")
        elif gestures.both_closed_drive:
            self.lbl_mode.setText("DRIVE (RT)")
            self.lbl_mode.setStyleSheet("color: #00FF66; font-size: 11px; font-weight: bold;")
            self.card.setStyleSheet("QFrame { background-color: rgba(10, 10, 16, 240); border: 2px solid #00FF66; border-radius: 10px; }")
        else:
            self.lbl_mode.setText("COAST")
            self.lbl_mode.setStyleSheet("color: #707085; font-size: 11px; font-weight: bold;")
            self.card.setStyleSheet("QFrame { background-color: rgba(10, 10, 16, 220); border: 2px solid #35354A; border-radius: 10px; }")

        self.lbl_fps.setText(f"FPS: {fps:.0f}")

    # Window drag logic so user can position it anywhere on their screen
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()
