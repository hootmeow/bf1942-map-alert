import logging
import sys
from logging.handlers import RotatingFileHandler
import os

def setup_logger(name: str = "bf1942_bot", log_file: str = "bot.log", level: int = logging.INFO) -> logging.Logger:
    """
    Sets up a logger with both console and file handlers.
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # Console Handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # File Handler
    try:
        file_handler = RotatingFileHandler(
            log_file, maxBytes=5*1024*1024, backupCount=5, encoding='utf-8' # 5MB
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except Exception as e:
        print(f"Failed to setup file logging: {e}")

    return logger

# Create a default logger instance
logger = setup_logger()
