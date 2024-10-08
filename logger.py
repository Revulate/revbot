# logger.py
import logging
import sys
import os
from logging.handlers import RotatingFileHandler
from threading import Lock
from logdna import LogDNAHandler  # Import LogDNAHandler for logging to LogDNA
import configparser

# Load configuration from config.ini
config = configparser.ConfigParser()
config.read('config.ini')

# Set LOGDNA_INGESTION_KEY from config.ini if not already set in environment variables
if 'Logging' in config and 'LOGDNA_INGESTION_KEY' in config['Logging']:
    os.environ.setdefault('LOGDNA_INGESTION_KEY', config['Logging']['LOGDNA_INGESTION_KEY'])

# Create a lock for thread safety
_logger_setup_lock = Lock()

# Define a common formatter for all handlers
_formatter = logging.Formatter('[%(asctime)s] %(levelname)s:%(name)s: %(message)s')

# Define a new log level for user messages
USER_MESSAGE_LEVEL = 25
logging.addLevelName(USER_MESSAGE_LEVEL, 'MESSAGE')

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
                logger.addHandler(create_logdna_handler(level))
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

def create_logdna_handler(level):
    """Create a LogDNA handler for logging."""
    logdna_ingestion_key = os.getenv('LOGDNA_INGESTION_KEY')
    if logdna_ingestion_key:
        logdna_options = {
            'app': 'TwitchBot',
            'env': 'production'
        }
        logdna_handler = LogDNAHandler(logdna_ingestion_key, options=logdna_options)
        logdna_handler.setLevel(level)
        return logdna_handler
    else:
        # If LogDNA key is not provided, create a handler that logs this issue
        missing_logdna_handler = logging.StreamHandler(sys.stdout)
        missing_logdna_handler.setLevel(logging.WARNING)
        missing_logdna_handler.setFormatter(_formatter)
        missing_logdna_handler.handle(logging.LogRecord(
            name='logdna',
            level=logging.WARNING,
            pathname=__file__,
            lineno=0,
            msg='LOGDNA_INGESTION_KEY environment variable is missing. LogDNA logging will not be enabled.',
            args=None,
            exc_info=None
        ))
        return missing_logdna_handler

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

# Log user messages
def log_user_message(logger, message):
    """Logs user messages for debugging purposes."""
    if logger.isEnabledFor(USER_MESSAGE_LEVEL):
        logger.log(USER_MESSAGE_LEVEL, f"User message: {message}")