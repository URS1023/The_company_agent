from __future__ import annotations

import logging
import sys


def configure_logging() -> None:
    """Configure one predictable stdout handler for local and worker processes."""

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        stream=sys.stdout,
        force=True,
    )


__all__ = ["configure_logging"]
