# logger.py
import logging
import sys
import os
from logging.handlers import RotatingFileHandler
from threading import Lock

# Create a lock for thread safety
_logger_setup_lock = Lock()

# Define a common formatter for all handlers
_formatter = logging.Formatter('[%(asctime)s] %(levelname)s:%(name)s: %(message)s')

def setup_logger(name='twitch_bot', level=logging.DEBUG, log_file='bot.log', max_bytes=5*1024*1024, backup_count=3, handlers=None):
    """Setup a centralized logger with log rotation for the bot.
    
    Args:
        name (str): Name of the logger.
        level (int): Logging level.
        log_file (str): Path to the log file.
        max_bytes (int): Maximum size of the log file in bytes before rotation.
        backup_count (int): Number of backup files to keep.
        handlers (list): List of custom handlers to add to the logger.
    """
    logger = logging.getLogger(name)

    with _logger_setup_lock:
        # Check if logger already has handlers (avoid duplicating handlers)
        if not logger.hasHandlers():
            if handlers:
                for handler in handlers:
                    logger.addHandler(handler)
            else:
                # Create default handlers if no custom handlers are provided
                logger.addHandler(create_console_handler(level))
                logger.addHandler(create_file_handler(log_file, max_bytes, backup_count, level))
            # Set logger level after adding handlers
            logger.setLevel(level)

    return logger

def create_console_handler(level):
    """Create a console handler for logging."""
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(_formatter)
    return console_handler

def create_file_handler(log_file, max_bytes, backup_count, level):
    """Create a file handler for logging with rotation."""
    file_handler = RotatingFileHandler(log_file, maxBytes=max_bytes, backupCount=backup_count, encoding='utf-8')
    file_handler.setLevel(level)
    file_handler.setFormatter(_formatter)
    return file_handler

# Load log level from environment, default to DEBUG if not set
log_level_str = os.getenv('LOG_LEVEL', 'DEBUG').upper()
if log_level_str not in ['CRITICAL', 'ERROR', 'WARNING', 'INFO', 'DEBUG', 'NOTSET']:
    temp_logger = logging.getLogger('temporary_logger')
    temp_logger.setLevel(logging.DEBUG)
    temp_handler = logging.StreamHandler(sys.stdout)
    temp_handler.setFormatter(_formatter)
    temp_logger.addHandler(temp_handler)
    temp_logger.warning(f"Invalid LOG_LEVEL '{log_level_str}' specified. Falling back to DEBUG level.")
    log_level_str = 'DEBUG'

valid_levels = {
    'CRITICAL': logging.CRITICAL,
    'ERROR': logging.ERROR,
    'WARNING': logging.WARNING,
    'INFO': logging.INFO,
    'DEBUG': logging.DEBUG,
    'NOTSET': logging.NOTSET,
}
log_level = valid_levels[log_level_str]

setup_logger(level=log_level)