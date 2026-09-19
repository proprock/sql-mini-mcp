from sql_mini_mcp.errors import DomainError, ErrorCode


def test_domain_error_has_stable_public_format() -> None:
    error = DomainError(ErrorCode.NOT_FOUND, "Table was not found.", "Call list_tables first.")

    assert str(error) == "[NOT_FOUND] Table was not found. Hint: Call list_tables first."
