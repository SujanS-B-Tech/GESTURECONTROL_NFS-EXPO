"""
Logger utility for GESTUREDRIVE X.
Provides console logging, rotating file logging, and an optional GUI log handler.
"""

import os
import sys
import logging
from logging.handlers import RotatingFileHandler
from typing import Optional, Callable

# Default log format
LOG_FORMAT = "%(asctime)s [%(levelname)s] [%(name)s]: %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

class GuiLogHandler(logging.Handler):
    """Custom logging handler that routes log records to a GUI callback function."""
    def __init__(self, callback: Optional[Callable[[str, str], None]] = None):
        super().__init__()
        self.callback = callback

    def emit(self, record: logging.LogRecord):
        if self.callback:
            try:
                msg = self.format(record)
                self.callback(record.levelname, msg)
            except Exception:
                pass


def setup_logger(
    name: str = "GestureDriveX",
    log_dir: str = "logs",
    log_filename: str = "gesturedrive.log",
    level: int = logging.INFO,
    gui_callback: Optional[Callable[[str, str], None]] = None
) -> logging.Logger:
    """Configures and returns a centralized logger instance."""
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Prevent duplicate handlers if already configured
    if logger.handlers:
        return logger

    formatter = logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT)

    # 1. Console Handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(level)
    logger.addHandler(console_handler)

    # 2. Rotating File Handler
    try:
        os.makedirs(log_dir, exist_ok=True)
        file_path = os.path.join(log_dir, log_filename)
        file_handler = RotatingFileHandler(
            file_path,
            maxBytes=5 * 1024 * 1024, # 5 MB
            backupCount=3,
            encoding="utf-8"
        )
        file_handler.setFormatter(formatter)
        file_handler.setLevel(level)
        logger.addHandler(file_handler)
    except Exception as e:
        logger.warning(f"Could not create file logger at {log_dir}: {e}")

    # 3. Optional GUI Handler
    if gui_callback:
        gui_handler = GuiLogHandler(gui_callback)
        gui_handler.setFormatter(formatter)
        gui_handler.setLevel(level)
        logger.addHandler(gui_handler)

    logger.propagate = False
    return logger

# Module-level default logger instance
logger = setup_logger()

