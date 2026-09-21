"""Runtime logging that works under Uvicorn and serverless ASGI hosts."""
from __future__ import annotations

import logging
import sys


def get_server_logger() -> logging.Logger:
    logger = logging.getLogger("uvicorn.error")
    logger.disabled = False
    if logger.level > logging.WARNING:
        logger.setLevel(logging.WARNING)
    if not logger.handlers or all(handler.level > logging.WARNING for handler in logger.handlers):
        handler = logging.StreamHandler(sys.stderr)
        handler.setLevel(logging.WARNING)
        handler.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
        logger.addHandler(handler)
        # This explicit stderr handler is the terminal output path on Vercel.
        logger.propagate = False
    return logger
