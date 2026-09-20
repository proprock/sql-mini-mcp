from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from uuid import uuid4


class ErrorCode(StrEnum):
    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    UNKNOWN_SERVER = "UNKNOWN_SERVER"
    NOT_FOUND = "NOT_FOUND"
    AMBIGUOUS_OBJECT = "AMBIGUOUS_OBJECT"
    ACCESS_LEVEL_DENIED = "ACCESS_LEVEL_DENIED"
    CONFIG_ERROR = "CONFIG_ERROR"
    CONNECTION_FAILED = "CONNECTION_FAILED"
    ACCESS_DENIED = "ACCESS_DENIED"
    TIMEOUT = "TIMEOUT"
    METADATA_UNAVAILABLE = "METADATA_UNAVAILABLE"
    DEFINITION_TOO_LARGE = "DEFINITION_TOO_LARGE"
    QUERY_REJECTED = "QUERY_REJECTED"
    INVALID_PII_TOKEN = "INVALID_PII_TOKEN"
    RESULT_LIMIT_EXCEEDED = "RESULT_LIMIT_EXCEEDED"
    DATABASE_ERROR = "DATABASE_ERROR"


@dataclass(slots=True)
class DomainError(Exception):
    code: ErrorCode
    public_message: str
    hint: str | None = None
    retryable: bool = False
    correlation_id: str | None = None

    def __str__(self) -> str:
        parts = [f"[{self.code}] {self.public_message}"]
        if self.hint:
            parts.append(f"Hint: {self.hint}")
        if self.correlation_id:
            parts.append(f"Reference: {self.correlation_id}")
        return " ".join(parts)

    @classmethod
    def unexpected(cls) -> DomainError:
        return cls(
            ErrorCode.DATABASE_ERROR,
            "The database operation failed unexpectedly.",
            retryable=False,
            correlation_id=uuid4().hex,
        )
