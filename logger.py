"""Logging utilities for IRC Ebook Fetcher."""

import sys
import time
from typing import Optional


class Logger:
    """Thread-safe logger with timestamps."""

    def __init__(self, name: str, debug: bool = False):
        """
        Initialize logger.

        Args:
            name: Logger name (typically thread/component name)
            debug: Whether to show debug messages
        """
        self.name = name
        self.debug_enabled = debug

    def log(self, message: str) -> None:
        """
        Log a message with timestamp.

        Args:
            message: Message to log
        """
        timestamp = time.strftime("%H:%M:%S", time.gmtime())
        sys.stdout.write(f"[{timestamp} {self.name:12}] {message}\n")
        sys.stdout.flush()

    def debug(self, message: str) -> None:
        """
        Log a debug message (only if debug is enabled).

        Args:
            message: Debug message to log
        """
        if self.debug_enabled:
            self.log(f"DEBUG: {message}")

    def error(self, message: str) -> None:
        """
        Log an error message.

        Args:
            message: Error message to log
        """
        self.log(f"ERROR: {message}")

    def info(self, message: str) -> None:
        """
        Log an info message.

        Args:
            message: Info message to log
        """
        self.log(message)
