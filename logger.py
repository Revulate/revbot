# logger.py

import logging
import sys
import os
from logging.handlers import RotatingFileHandler
from threading import Lock
from logdna import LogDNAHandler
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Use environment variables
LOGDNA_KEY = os.getenv('LOGDNA_INGESTION_KEY')
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO').upper()
LOG_FILE = os.getenv('LOG_FILE', 'bot.log')
LOG_MAX_BYTES = int(os.getenv('LOG_MAX_BYTES', '5242880'))
LOG_BACKUP_COUNT = int(os.getenv('LOG_BACKUP_COUNT', '3'))

# Create a lock for thread safety
_logger_setup_lock = Lock()

# Define a common formatter for all handlers
_formatter = logging.Formatter('[%(asctime)s] %(levelname)s:%(name)s: %(message)s')

# Define a new log level for user messages
USER_MESSAGE_LEVEL = 25
logging.addLevelName(USER_MESSAGE_LEVEL, 'MESSAGE')

def setup_logger(name='twitch_bot', level=None, log_file=None, max_bytes=None, backup_count=None):
    """Setup a centralized logger with log rotation for the bot."""
    logger = logging.getLogger(name)

    # Use default values if not provided
    level = level or getattr(logging, LOG_LEVEL, logging.INFO)
    log_file = log_file or LOG_FILE
    max_bytes = max_bytes or LOG_MAX_BYTES
    backup_count = backup_count or LOG_BACKUP_COUNT

    with _logger_setup_lock:
        if not logger.handlers:
            logger.addHandler(create_console_handler(level))
            logger.addHandler(create_file_handler(log_file, max_bytes, backup_count, level))
            if LOGDNA_KEY:
                logger.addHandler(create_logdna_handler(level))
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

def create_logdna_handler(level):
    """Create a LogDNA handler for logging."""
    if LOGDNA_KEY:
        logdna_options = {
            'app': 'TwitchBot',
            'env': 'production'
        }
        logdna_handler = LogDNAHandler(LOGDNA_KEY, options=logdna_options)
        logdna_handler.setLevel(level)
        return logdna_handler
    return None

def log_user_message(logger, message):
    """Logs user messages for debugging purposes."""
    if logger.isEnabledFor(USER_MESSAGE_LEVEL):
        logger.log(USER_MESSAGE_LEVEL, f"User message: {message}")

# Create a global logger instance
logger = setup_logger()