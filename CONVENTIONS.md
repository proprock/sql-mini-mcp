# Conventions

- Python 3.12+, `src/` layout, Pydantic v2 models, explicit return types.
- Domain code raises `DomainError`; MCP handlers translate it to `ToolError`.
- Public list results are object-rooted models with stable sorting.
- Metadata filters are case-insensitive literal substrings, not SQL patterns.
- Never concatenate identifiers or decrypted token values into SQL.
- SQL Server schema omission must resolve exactly one object or fail as ambiguous.
