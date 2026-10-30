"""
Application Entrypoint and PySide6 Runtime Initializer for GESTUREDRIVE X.
"""

import sys
import os
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon

from src.ui.main_window import MainWindow
from src.utils.logger import logger


def run_app():
    """Initializes Qt Application, configures High-DPI attributes, and executes main event loop."""
    # Ensure correct working directory
    proj_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.chdir(proj_root)

    # Enable High DPI scaling
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setApplicationName("GESTUREDRIVE X")
    app.setApplicationVersion("1.0.0")
    app.setOrganizationName("GestureDrive")

    icon_path = os.path.join(proj_root, "assets", "icon.ico")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    logger.info("Initializing GESTUREDRIVE X Desktop Interface...")

    window = MainWindow()
    window.show()

    logger.info("GESTUREDRIVE X UI rendered and operational.")
    return app.exec()


if __name__ == "__main__":
    sys.exit(run_app())
