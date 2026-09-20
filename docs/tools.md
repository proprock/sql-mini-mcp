# Tools

Six read-only tools, each annotated `readOnlyHint=true`. Every tool takes a `server` alias from
your configuration. `schema` is optional everywhere: when omitted, the name must resolve to exactly
one object, otherwise the call fails as ambiguous and lists the candidate schemas.

| Tool | Arguments | Returns |
|---|---|---|
| `list_servers` | none | The configured server aliases |
| `list_databases` | `server`, `name_contains?` | Databases visible to the configured credentials |
| `list_tables` | `server`, `database`, `schema?`, `name_contains?` | Base tables |
| `get_table_definition` | `server`, `database`, `table`, `schema?` | Columns, keys, constraints, and indexes |
| `list_stored_procedures` | `server`, `database`, `schema?`, `name_contains?` | Procedure names, without definitions |
| `get_stored_procedure` | `server`, `database`, `name`, `schema?` | The original definition, when visible |

## Response conventions

- List results are object-rooted models with stable sorting.
- `name_contains` is a case-insensitive literal substring, not a SQL pattern: `%` and `_` match
  themselves.
- Stored procedure lists never expand definitions; fetch one with `get_stored_procedure`.
- A definition longer than `max_definition_chars` is refused with an error rather than silently
  truncated.
- `list_tables` returns base tables only.

## Errors

Errors state the safe cause and, when known, the corrective action - for example the candidate
schemas for an ambiguous name. They never contain connection URLs, credentials, keys, tokens, SQL
bind values, or result rows.

## What is not here

No tool executes SQL, writes data, or discovers servers, and the catalog is not published as MCP
resources. PII-safe `execute_sql` is planned; see [ARCHITECTURE.md](../ARCHITECTURE.md).
