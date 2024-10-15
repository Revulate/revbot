import logging
import sys
from logging.handlers import RotatingFileHandler
import codecs


def setup_logger(name, log_file="bot.log", level=logging.INFO):
    logger = logging.getLogger(name)
    logger.setLevel(level)

    formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # File handler with UTF-8 encoding
    file_handler = RotatingFileHandler(log_file, maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger


# Create a global logger instance
logger = setup_logger("twitch_bot")


def log_command(command_name, user, channel):
    """Utility function to log command usage."""
    logger.info(f"Command '{command_name}' used by {user} in channel {channel}")


def log_error(error_message, exc_info=False):
    """Utility function to log errors."""
    logger.error(error_message, exc_info=exc_info)


def log_info(message):
    """Utility function to log info messages."""
    logger.info(message)


def log_warning(message):
    """Utility function to log warning messages."""
    logger.warning(message)


def log_debug(message):
    """Utility function to log debug messages."""
    logger.debug(message)
