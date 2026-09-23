"""Logger dùng chung (rich)."""
import logging

from rich.logging import RichHandler


def get_logger(name: str = "hgr") -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.addHandler(RichHandler(rich_tracebacks=True, show_path=False))
        logger.setLevel(logging.INFO)
    return logger
