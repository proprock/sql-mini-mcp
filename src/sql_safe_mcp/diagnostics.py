from __future__ import annotations

import logging
import re
from collections.abc import Iterable
from urllib.parse import quote

from sqlalchemy.engine import make_url

_MAX_MESSAGE_CHARS = 500
_CONTROL_CHARACTERS = re.compile(r"[\x00-\x1f\x7f]+")


def configure_logging(level: str) -> None:
    logging.getLogger("sql_safe_mcp").setLevel(level)
    # SQLAlchemy inherits the root level and would echo statements with bind values at DEBUG.
    logging.getLogger("sqlalchemy").setLevel(logging.WARNING)


def secrets_for(url: str) -> tuple[str, ...]:
    """Password, user name, and host of a connection URL, raw and URL-quoted."""
    try:
        parsed = make_url(url)
    except Exception:
        return ()
    values = (parsed.password, parsed.username, parsed.host)
    found: dict[str, None] = {}
    for value in values:
        if value:
            found[value] = None
            found[quote(value, safe="")] = None
    return tuple(found)


def _driver_parts(exc: BaseException) -> tuple[str, str, str]:
    orig = getattr(exc, "orig", None) or exc
    args = orig.args
    if len(args) >= 2 and isinstance(args[0], int):
        return type(orig).__name__, f" code={args[0]}", str(args[1])
    if len(args) >= 2 and isinstance(args[0], str) and isinstance(args[1], str):
        return type(orig).__name__, f" sqlstate={args[0]}", args[1]
    return type(orig).__name__, "", str(orig)


def _secret_pattern(secret: str) -> str:
    # Whole-word only where the edge is a word character, so "sa" spares "usage" but a
    # password ending in punctuation is still removed.
    start = r"(?<!\w)" if re.match(r"\w", secret[0]) else ""
    end = r"(?!\w)" if re.match(r"\w", secret[-1]) else ""
    return f"{start}{re.escape(secret)}{end}"


def describe_error(exc: BaseException, secrets: Iterable[str]) -> str:
    """One log-safe line for a driver error: class, SQLSTATE or code, redacted message."""
    name, code, message = _driver_parts(exc)
    for secret in sorted({value for value in secrets if value}, key=len, reverse=True):
        message = re.sub(_secret_pattern(secret), "***", message, flags=re.IGNORECASE)
    message = _CONTROL_CHARACTERS.sub(" ", message).strip()
    if len(message) > _MAX_MESSAGE_CHARS:
        message = message[:_MAX_MESSAGE_CHARS] + "..."
    return f"{name}{code} message={message}"
