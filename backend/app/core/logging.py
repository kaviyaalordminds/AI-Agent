import logging
import sys

from app.core.config import get_settings


def configure_logging() -> None:
    settings = get_settings()
    level = logging.DEBUG if settings.debug else logging.INFO
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter("%(asctime)s | %(levelname)-8s | %(name)s | %(message)s")
    )
    root = logging.getLogger()
    root.setLevel(level)
    root.handlers = [handler]

    # Never let noisy libraries leak secrets/tokens into logs at DEBUG level.
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
