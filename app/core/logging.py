"""Logging configuration.

Called once at application start-up. Without this, ``logger.exception`` output
depends entirely on uvicorn's default handler, which is easy to lose in a
container.
"""

import logging
from logging.config import dictConfig

from app.core.config import settings

_DEPLOYED_ENVS = {"prod", "production", "staging"}


def configure_logging() -> None:
    is_deployed = settings.APP_ENV.lower() in _DEPLOYED_ENVS
    level = "INFO" if is_deployed else "DEBUG"

    dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "standard": {
                    "format": "%(asctime)s %(levelname)s [%(name)s] %(message)s",
                    "datefmt": "%Y-%m-%dT%H:%M:%S%z",
                },
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "formatter": "standard",
                    "stream": "ext://sys.stdout",
                },
            },
            "loggers": {
                "app": {"handlers": ["console"], "level": level, "propagate": False},
                "uvicorn.error": {"handlers": ["console"], "level": "INFO", "propagate": False},
                "uvicorn.access": {"handlers": ["console"], "level": "INFO", "propagate": False},
            },
            "root": {"handlers": ["console"], "level": "WARNING"},
        }
    )
    logging.getLogger("app").debug("Logging configured for APP_ENV=%s", settings.APP_ENV)
