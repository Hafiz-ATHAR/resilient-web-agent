import logging
import logging.config
import sys
from typing import Any, Literal

import structlog

Environment = Literal["development", "testing", "staging", "production"]

_configured = False
LOGGING_CONFIG: dict[str, Any] = {}


def _build_processors(env: Environment, *, for_formatter: bool) -> list[Any]:
    processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
    ]
    if env == "development":
        processors.append(
            structlog.processors.CallsiteParameterAdder(
                {
                    structlog.processors.CallsiteParameter.FILENAME,
                    structlog.processors.CallsiteParameter.LINENO,
                    structlog.processors.CallsiteParameter.FUNC_NAME,
                }
            )
        )
    if for_formatter:
        processors.append(structlog.processors.format_exc_info)
    else:
        processors.append(structlog.processors.dict_tracebacks)
    return processors


def _renderer(env: Environment) -> Any:
    if env == "production":
        return structlog.processors.JSONRenderer()
    return structlog.dev.ConsoleRenderer(colors=True)


def configure_logging(env: Environment) -> None:
    global _configured, LOGGING_CONFIG
    if _configured:
        return

    root_level = "DEBUG" if env == "development" else "INFO"
    foreign_pre_chain = _build_processors(env, for_formatter=True)
    renderer = _renderer(env)

    LOGGING_CONFIG = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "structlog": {
                "()": structlog.stdlib.ProcessorFormatter,
                "processor": renderer,
                "foreign_pre_chain": foreign_pre_chain,
            },
        },
        "handlers": {
            "default": {
                "class": "logging.StreamHandler",
                "stream": sys.stderr,
                "formatter": "structlog",
            },
        },
        "loggers": {
            "": {"handlers": ["default"], "level": root_level},
            "uvicorn": {"handlers": ["default"], "level": "INFO", "propagate": False},
            "uvicorn.error": {"handlers": ["default"], "level": "INFO", "propagate": False},
            "uvicorn.access": {"handlers": ["default"], "level": "INFO", "propagate": False},
            "httpx": {"level": "WARNING"},
            "httpcore": {"level": "WARNING"},
            "mlflow": {"level": "WARNING"},
            "langchain": {"level": "INFO"},
            "langgraph": {"level": "INFO"},
            "aiosqlite": {"level": "WARNING"},
        },
    }

    logging.config.dictConfig(LOGGING_CONFIG)

    structlog.configure(
        processors=[
            *_build_processors(env, for_formatter=False),
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    _configured = True
