# Conventions

- Python 3.12–3.14, `src/` layout, Pydantic v2 models, explicit return types.
- Prefer small, explicit modules and existing dependencies. Do not introduce a dependency or an
  abstraction for speculative functionality or an unmeasured startup-time micro-optimization.
- Domain code raises `DomainError`; MCP handlers translate it to `ToolError`.
- Tool errors state the safe cause and corrective action when known, without exposing connection
  details, credentials, keys, SQL bind values, tokens, metadata, or rows.
- Public list results are object-rooted models with stable sorting.
- Metadata filters are case-insensitive literal substrings, not SQL patterns.
- Never concatenate identifiers or decrypted token values into SQL.
- SQL Server schema omission must resolve exactly one object or fail as ambiguous.
