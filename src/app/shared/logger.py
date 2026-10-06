"""Structured application logger."""

import logging


def get_logger(name: str) -> logging.Logger:
    """Return a logger with a stable format."""
    logger: logging.Logger = logging.getLogger(name)
    if not logger.handlers:
        handler: logging.StreamHandler[None] = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s %(name)s %(levelname)s %(message)s"))
        logger.addHandler(handler)
    return logger
