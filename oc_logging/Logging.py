import os
from logging.config import dictConfig


def setup_logging():
    console_level = os.getenv("LOG_LEVEL")
    if not console_level:
        console_level = "DEBUG"

    if console_level not in ["DEBUG", "WARNING", "INFO", "ERROR", "CRITICAL"]:
        raise EnvironmentError("LOG_LEVEL must be DEBUG, WARNING, INFO, ERROR, or CRITICAL")

    dictConfig(
        {
            "version": 1,
            "formatters": {
                "default": {
                    "format": "[%(asctime)s] [%(levelname)s] %(message)s",
                }
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "stream": "ext://sys.stdout",
                    "formatter": "default",
                    "level": console_level,
                },
            },
            "root": {
                "level": "DEBUG",
                "handlers": ["console"],
            },
            "loggers": {
                "werkzeug": {
                    "level": console_level,
                    "propagate": False
                }
            }
        }
    )