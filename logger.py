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
        logger.addHandler(create_console_handler(level))
        logger.addHandler(create_file_handler(log_file, max_bytes, backup_count, level))

    return logger

def create_console_handler(level):
    """Create a console handler for logging."""
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    formatter = logging.Formatter('[%(asctime)s] %(levelname)s:%(name)s: %(message)s')
    console_handler.setFormatter(formatter)
    return console_handler

def create_file_handler(log_file, max_bytes, backup_count, level):
    """Create a file handler for logging with rotation."""
    file_handler = RotatingFileHandler(log_file, maxBytes=max_bytes, backupCount=backup_count, encoding='utf-8')
    file_handler.setLevel(level)
    formatter = logging.Formatter('[%(asctime)s] %(levelname)s:%(name)s: %(message)s')
    file_handler.setFormatter(formatter)
    return file_handler

# Load log level from environment, default to DEBUG if not set
log_level_str = os.getenv('LOG_LEVEL', 'DEBUG').upper()
valid_levels = {
    'CRITICAL': logging.CRITICAL,
    'ERROR': logging.ERROR,
    'WARNING': logging.WARNING,
    'INFO': logging.INFO,
    'DEBUG': logging.DEBUG,
    'NOTSET': logging.NOTSET,
}
log_level = valid_levels.get(log_level_str, logging.DEBUG)
if log_level_str not in valid_levels:
    logging.warning(f"Invalid LOG_LEVEL '{log_level_str}' specified. Falling back to DEBUG level.")

setup_logger(level=log_level)
