from sql_safe_mcp.errors import DomainError, ErrorCode


def test_domain_error_has_stable_public_format() -> None:
    error = DomainError(ErrorCode.NOT_FOUND, "Table was not found.", "Call list_tables first.")

    assert str(error) == "[NOT_FOUND] Table was not found. Hint: Call list_tables first."


def test_unexpected_error_has_generic_message_and_unique_correlation_id() -> None:
    first = DomainError.unexpected()
    second = DomainError.unexpected()

    assert first.code is ErrorCode.DATABASE_ERROR
    assert first.public_message == "The database operation failed unexpectedly."
    assert first.correlation_id is not None
    assert len(first.correlation_id) == 32
    assert first.correlation_id != second.correlation_id
    assert "Traceback" not in str(first)
