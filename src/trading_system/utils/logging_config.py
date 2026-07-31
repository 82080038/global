"""Structured logging configuration with rotation.

Configure once at startup via setup_logging(). Uses dictConfig for:
- Console handler: human-readable format (stdout)
- File handler: rotating files with detailed format
- Error file handler: separate file for ERROR+ messages

Log level configurable via LOG_LEVEL env var (default: INFO).
Log directory configurable via LOG_DIR env var (default: logs/).
"""

from __future__ import annotations

import logging
import logging.config
import os
from pathlib import Path


def setup_logging() -> None:
    """Configure structured logging with rotation. Call once at startup."""
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    log_dir = Path(os.getenv("LOG_DIR", "logs"))
    log_dir.mkdir(parents=True, exist_ok=True)

    config = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "standard": {
                "format": "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                "datefmt": "%Y-%m-%dT%H:%M:%S",
            },
            "detailed": {
                "format": "%(asctime)s [%(levelname)s] %(name)s %(filename)s:%(lineno)d: %(message)s",
                "datefmt": "%Y-%m-%dT%H:%M:%S",
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "level": log_level,
                "formatter": "standard",
                "stream": "ext://sys.stdout",
            },
            "file": {
                "class": "logging.handlers.RotatingFileHandler",
                "level": "DEBUG",
                "formatter": "detailed",
                "filename": str(log_dir / "trading_system.log"),
                "maxBytes": 10 * 1024 * 1024,  # 10 MB
                "backupCount": 5,
                "encoding": "utf-8",
            },
            "error_file": {
                "class": "logging.handlers.RotatingFileHandler",
                "level": "ERROR",
                "formatter": "detailed",
                "filename": str(log_dir / "errors.log"),
                "maxBytes": 5 * 1024 * 1024,  # 5 MB
                "backupCount": 10,
                "encoding": "utf-8",
            },
        },
        "loggers": {
            "trading_system": {
                "level": log_level,
                "handlers": ["console", "file", "error_file"],
                "propagate": False,
            },
            "uvicorn.access": {
                "level": "INFO",
                "handlers": ["console"],
                "propagate": False,
            },
            "apscheduler": {
                "level": "WARNING",
                "handlers": ["console"],
                "propagate": False,
            },
        },
        "root": {
            "level": "WARNING",
            "handlers": ["console"],
        },
    }

    logging.config.dictConfig(config)
