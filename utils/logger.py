import logging
import os
import sys
from logging.handlers import RotatingFileHandler

def setup_logger(name: str = "meeting_assistant") -> logging.Logger:
    """
    Configures and returns a hierarchical logging instance.
    Sets up a RotatingFileHandler for disk persistence (at DEBUG level)
    and a StreamHandler for stdout console printing (at INFO level).
    Also configures filters to prevent Azure SDK log flooding.
    
    Args:
        name (str): Name of the logger namespace. Defaults to 'meeting_assistant'.

    Returns:
        logging.Logger: Configured logger instance.
    """
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    # Prevent duplicate handlers if helper is called multiple times
    if logger.handlers:
        return logger

    # Log Formatter
    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s (%(filename)s:%(lineno)d) - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Create logs directory if it doesn't exist
    log_dir = "logs"
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    # File Handler - Rotating File (Max 5MB, keep 3 backup logs)
    log_file_path = os.path.join(log_dir, "app.log")
    file_handler = RotatingFileHandler(
        filename=log_file_path,
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8"
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # Console Handler - Stream output to stdout
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # Azure SDK Log Suppression
    # Suppress verbose HTTP request/response headers logging from azure.core.pipeline
    logging.getLogger("azure.core.pipeline.policies.http_logging_policy").setLevel(logging.WARNING)
    logging.getLogger("azure").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)

    logger.debug("Logger initialized successfully. Console level: INFO, File level: DEBUG.")
    return logger

# Export a default root logger for application-wide ease of use
logger = setup_logger()
