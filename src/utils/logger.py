"""
Logging utility for BDO Trainer
Provides centralized logging configuration and helper functions
"""

import logging
import os
from datetime import datetime
from pathlib import Path


def setup_logger(
    name: str = "bdo_trainer",
    log_level: str = "INFO",
    log_to_file: bool = True,
    log_directory: str = "./logs",
    max_bytes: int = 10 * 1024 * 1024,  # 10MB
    backup_count: int = 5,
) -> logging.Logger:
    """
    Set up and configure a logger instance

    Args:
        name: Logger name
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_to_file: Whether to log to file in addition to console
        log_directory: Directory to store log files
        max_bytes: Maximum size of each log file before rotation
        backup_count: Number of backup log files to keep

    Returns:
        Configured logger instance
    """
    # Create logger
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    # Clear any existing handlers
    logger.handlers.clear()

    # Create formatter
    formatter = logging.Formatter(
        fmt="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # File handler (if enabled)
    if log_to_file:
        # Create log directory if it doesn't exist
        log_path = Path(log_directory)
        log_path.mkdir(parents=True, exist_ok=True)

        # Create log filename with date
        log_filename = f"{name}_{datetime.now().strftime('%Y%m%d')}.log"
        log_filepath = log_path / log_filename

        try:
            from logging.handlers import RotatingFileHandler

            file_handler = RotatingFileHandler(
                log_filepath,
                maxBytes=max_bytes,
                backupCount=backup_count,
                encoding="utf-8",
            )
            file_handler.setLevel(logging.DEBUG)
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
        except Exception as e:
            logger.warning(f"Could not create file handler: {e}")

    logger.info(f"Logger '{name}' initialized with level {log_level}")
    return logger


def get_logger(name: str = "bdo_trainer") -> logging.Logger:
    """
    Get an existing logger instance

    Args:
        name: Logger name

    Returns:
        Logger instance
    """
    return logging.getLogger(name)


class LoggerMixin:
    """
    Mixin class to add logging capabilities to any class

    Usage:
        class MyClass(LoggerMixin):
            def __init__(self):
                super().__init__()
                self.log_info("MyClass initialized")
    """

    @property
    def logger(self) -> logging.Logger:
        """Get logger for this class"""
        if not hasattr(self, "_logger"):
            self._logger = logging.getLogger(self.__class__.__name__)
        return self._logger

    def log_debug(self, message: str, *args, **kwargs):
        """Log a debug message"""
        self.logger.debug(message, *args, **kwargs)

    def log_info(self, message: str, *args, **kwargs):
        """Log an info message"""
        self.logger.info(message, *args, **kwargs)

    def log_warning(self, message: str, *args, **kwargs):
        """Log a warning message"""
        self.logger.warning(message, *args, **kwargs)

    def log_error(self, message: str, *args, **kwargs):
        """Log an error message"""
        self.logger.error(message, *args, **kwargs)

    def log_critical(self, message: str, *args, **kwargs):
        """Log a critical message"""
        self.logger.critical(message, *args, **kwargs)

    def log_exception(self, message: str, *args, **kwargs):
        """Log an exception with traceback"""
        self.logger.exception(message, *args, **kwargs)


# Example usage
if __name__ == "__main__":
    # Setup logger
    logger = setup_logger(
        name="test_logger",
        log_level="DEBUG",
        log_to_file=True,
        log_directory="./logs",
    )

    # Test logging
    logger.debug("This is a debug message")
    logger.info("This is an info message")
    logger.warning("This is a warning message")
    logger.error("This is an error message")
    logger.critical("This is a critical message")

    # Test LoggerMixin
    class TestClass(LoggerMixin):
        def __init__(self):
            self.log_info("TestClass initialized")

        def do_something(self):
            self.log_debug("Doing something...")
            self.log_info("Something done!")

    test = TestClass()
    test.do_something()
