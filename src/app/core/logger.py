"""
Enhanced logging configuration with file rotation and configurable settings.

This module provides a centralized logging setup that:
- Supports console and file logging
- Uses RotatingFileHandler for automatic log rotation
- Respects environment-based configuration via LoggingSettings
- Provides colored console output for development
"""

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .config import LoggingSettings


# ANSI color codes for console output
class LogColors:
    """ANSI color codes for log level highlighting."""

    RESET = "\033[0m"
    DEBUG = "\033[36m"  # Cyan
    INFO = "\033[32m"  # Green
    WARNING = "\033[33m"  # Yellow
    ERROR = "\033[31m"  # Red
    CRITICAL = "\033[35m"  # Magenta


class ColoredFormatter(logging.Formatter):
    """Custom formatter that adds colors to log levels for console output."""

    LEVEL_COLORS = {
        logging.DEBUG: LogColors.DEBUG,
        logging.INFO: LogColors.INFO,
        logging.WARNING: LogColors.WARNING,
        logging.ERROR: LogColors.ERROR,
        logging.CRITICAL: LogColors.CRITICAL,
    }

    def format(self, record: logging.LogRecord) -> str:
        # Add color to the level name
        color = self.LEVEL_COLORS.get(record.levelno, LogColors.RESET)
        record.levelname = f"{color}{record.levelname}{LogColors.RESET}"
        return super().format(record)


def setup_logging(settings: "LoggingSettings") -> logging.Logger:
    """Configure and return the root logger based on settings.

    Parameters
    ----------
    settings : LoggingSettings
        Logging configuration settings.

    Returns
    -------
    logging.Logger
        Configured root logger instance.
    """
    # Create log directory if it doesn't exist
    log_dir = settings.LOG_DIR
    if not os.path.isabs(log_dir):
        # Make relative paths relative to the app directory
        log_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), log_dir)

    os.makedirs(log_dir, exist_ok=True)

    log_file_path = os.path.join(log_dir, settings.LOG_FILE)

    # Get numeric log level
    log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Remove existing handlers to avoid duplicates
    root_logger.handlers.clear()

    # Console handler with colors
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_formatter = ColoredFormatter(
        fmt=settings.LOG_FORMAT,
        datefmt=settings.LOG_DATE_FORMAT,
    )
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)

    # File handler with rotation
    file_handler = RotatingFileHandler(
        filename=log_file_path,
        maxBytes=settings.LOG_MAX_BYTES,
        backupCount=settings.LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setLevel(log_level)
    file_formatter = logging.Formatter(
        fmt=settings.LOG_FORMAT,
        datefmt=settings.LOG_DATE_FORMAT,
    )
    file_handler.setFormatter(file_formatter)
    root_logger.addHandler(file_handler)

    # Reduce noise from third-party libraries
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)

    return root_logger


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance for the given name.

    Parameters
    ----------
    name : str
        Name for the logger (typically __name__).

    Returns
    -------
    logging.Logger
        Logger instance.
    """
    return logging.getLogger(name)


# Default initialization for backwards compatibility
# This will be overridden when setup_logging is called with settings
LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

LOG_FILE_PATH = os.path.join(LOG_DIR, "app.log")
LOGGING_LEVEL = logging.INFO
LOGGING_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

logging.basicConfig(level=LOGGING_LEVEL, format=LOGGING_FORMAT)

_file_handler = RotatingFileHandler(LOG_FILE_PATH, maxBytes=10485760, backupCount=5)
_file_handler.setLevel(LOGGING_LEVEL)
_file_handler.setFormatter(logging.Formatter(LOGGING_FORMAT))
logging.getLogger("").addHandler(_file_handler)
