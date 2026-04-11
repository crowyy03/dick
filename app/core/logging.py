import logging
import re

import structlog


def _mask_sensitive(message: str) -> str:
    """Best-effort redaction for logs (URLs, long tokens)."""
    s = message
    s = re.sub(r"(password|passwd|pwd)=[^&\s]+", r"\1=***", s, flags=re.I)
    s = re.sub(r"(token|secret|key)=[^&\s]+", r"\1=***", s, flags=re.I)
    s = re.sub(r"(vless|vmess|trojan|ss)://[^\s]+", r"\1://***", s, flags=re.I)
    return s


def setup_logging(log_level: str) -> None:
    logging.basicConfig(level=getattr(logging, log_level.upper(), logging.INFO))
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.dev.ConsoleRenderer(colors=False),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, log_level.upper(), logging.INFO)
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None):
    return structlog.get_logger(name)
