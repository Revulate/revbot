import logging
import sys
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler
import json
from datetime import datetime
import os


class CustomJsonFormatter(logging.Formatter):
    def format(self, record):
        log_record = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        if record.exc_info:
            log_record["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_record)


def setup_logger(name, log_file="bot.log", level=logging.INFO):
    logger = logging.getLogger(name)

    # Clear any existing handlers to prevent duplicate logging
    if logger.hasHandlers():
        logger.handlers.clear()

    logger.setLevel(level)

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(CustomJsonFormatter())
    logger.addHandler(console_handler)

    # File handler with rotation
    file_handler = TimedRotatingFileHandler(log_file, when="midnight", interval=1, backupCount=7, encoding="utf-8")
    file_handler.setFormatter(CustomJsonFormatter())
    logger.addHandler(file_handler)

    # Prevent propagation to avoid duplicate logs
    logger.propagate = False

    return logger


# Create a global logger instance
logger = setup_logger("twitch_bot")


def log_command(command_name, user, channel):
    """Utility function to log command usage."""
    logger.info(f"Command '{command_name}' used", extra={"user": user, "channel": channel, "command": command_name})


def log_error(error_message, exc_info=False, **kwargs):
    """Utility function to log errors."""
    logger.error(error_message, exc_info=exc_info, extra=kwargs)


def log_info(message, **kwargs):
    """Utility function to log info messages."""
    logger.info(message, extra=kwargs)


def log_warning(message, **kwargs):
    """Utility function to log warning messages."""
    logger.warning(message, extra=kwargs)


def log_debug(message, **kwargs):
    """Utility function to log debug messages."""
    logger.debug(message, extra=kwargs)


def log_critical(message, **kwargs):
    """Utility function to log critical messages."""
    logger.critical(message, extra=kwargs)


def get_logger(name):
    """Get a named logger."""
    return logging.getLogger(name)


# Environment-based logging level
log_level = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=getattr(logging, log_level))


# Function to change log level dynamically
def set_log_level(level):
    logger.setLevel(level)
    for handler in logger.handlers:
        handler.setLevel(level)
    log_info(f"Log level changed to {level}")
