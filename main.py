"""
GESTUREDRIVE X — AI-Powered Touchless Racing Control for Need for Speed Heat
Master Entry Point
"""

import sys
import argparse
import os

from src.utils.logger import logger, setup_logger


def parse_args():
    parser = argparse.ArgumentParser(
        description="GESTUREDRIVE X — Touchless Control System for Need for Speed Heat"
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="Run self-diagnostic unit tests and verify all modules"
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable detailed debug logging to console and logfile"
    )
    return parser.parse_args()


def main():
    args = parse_args()

    if args.debug:
        import logging
        setup_logger(level=logging.DEBUG)
        logger.debug("Debug logging enabled.")

    if args.test:
        logger.info("Executing GESTUREDRIVE X diagnostic test suite...")
        import pytest
        exit_code = pytest.main(["-v", "tests"])
        sys.exit(exit_code)

    from src.app import run_app
    sys.exit(run_app())


if __name__ == "__main__":
    main()

