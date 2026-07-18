from __future__ import annotations

import logging
import os

from rich.console import Console
from rich.logging import RichHandler


_DEFAULT_LOG_LEVEL = "INFO"
_DEFAULT_SQL_LOG_LEVEL = "WARNING"
_LOG_LEVEL_ENV = "GABRIEL_LOG_LEVEL"
_SQL_LOG_LEVEL_ENV = "GABRIEL_SQL_LOG_LEVEL"
_configured = False


def _parse_level(raw_level: str | None, default: str) -> int:
    candidate = (raw_level or default).upper()
    level = logging.getLevelName(candidate)
    return level if isinstance(level, int) else logging.getLevelName(default)


def configure_logging(*, force: bool = False) -> None:
    global _configured

    if _configured and not force:
        return

    root_logger = logging.getLogger()
    handler = RichHandler(
        console=Console(stderr=True),
        rich_tracebacks=True,
        show_path=False,
        markup=False,
    )
    handler.setFormatter(logging.Formatter("%(message)s"))

    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(_parse_level(os.getenv(_LOG_LEVEL_ENV), _DEFAULT_LOG_LEVEL))

    sql_level = _parse_level(os.getenv(_SQL_LOG_LEVEL_ENV), _DEFAULT_SQL_LOG_LEVEL)
    logging.getLogger("sqlalchemy.engine").setLevel(sql_level)
    logging.getLogger("sqlalchemy.pool").setLevel(sql_level)
    logging.captureWarnings(True)
    _configured = True


def get_logger(name: str) -> logging.Logger:
    configure_logging()
    return logging.getLogger(name)