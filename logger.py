# logger.py
import logging
import sys
import os
from logging.handlers import RotatingFileHandler


def setup_logger(name='twitch_bot', level=logging.DEBUG, log_file='bot.log', max_bytes=5*1024*1024, backup_count=3):
    """Setup a centralized logger with log rotation for the bot."""
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Check if logger already has handlers (avoid duplicating handlers)
    if not logger.hasHandlers():
        # Create handlers
        logger.addHandler(create_console_handler())
        logger.addHandler(create_file_handler(log_file, max_bytes, backup_count))

    return logger


def create_console_handler():
    """Create a console handler for logging."""
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter('[%(asctime)s] %(levelname)s:%(name)s: %(message)s')
    console_handler.setFormatter(formatter)
    return console_handler


def create_file_handler(log_file, max_bytes, backup_count):
    """Create a file handler for logging with rotation."""
    file_handler = RotatingFileHandler(log_file, maxBytes=max_bytes, backupCount=backup_count, encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter('[%(asctime)s] %(levelname)s:%(name)s: %(message)s')
    file_handler.setFormatter(formatter)
    return file_handler


# Load log level from environment, default to DEBUG if not set
log_level = os.getenv('LOG_LEVEL', 'DEBUG').upper()
setup_logger(level=getattr(logging, log_level, logging.DEBUG))
