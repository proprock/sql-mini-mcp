# Tools

Seven read-only tools, each annotated `readOnlyHint=true`. Every tool takes a `server` alias from
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
| `execute_sql` | `server`, `database`, `sql`, `max_rows?` | Columns, rows, `row_count`, `truncated` |

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

No tool writes data or discovers servers, and the catalog is not published as MCP resources.

## execute_sql

Available only for `access_level: pii_safe` servers; a `metadata` server returns
`ACCESS_LEVEL_DENIED`. It accepts one `SELECT` from a small allowlist: local base tables, direct
columns and aliases, literals, `COUNT(*)` without `GROUP BY`, `INNER`/`LEFT JOIN ... ON`, `WHERE`
with `AND`/`OR`, comparisons, `IN` and `IS NULL`, `ORDER BY` on a direct column, and `TOP`.
Everything else is rejected with `QUERY_REJECTED`: CTEs, subqueries, unions, `DISTINCT`, `GROUP BY`,
functions, `CASE`, `CAST`, hints, `SELECT INTO`, variables, temporary tables, cross-database
names, and any syntax not listed.

- `max_rows` defaults to `default_max_rows` and may not exceed `hard_max_rows`. `truncated` is true
  when more rows existed.
- A protected column may be projected (with or without an alias) and compared with `=` or `IN`
  against tokens issued for the same server alias. Plaintext comparison, `ORDER BY`, join keys,
  functions, and arithmetic on protected columns are rejected.
- Protected cells are returned as `pii:v1:...` tokens; `NULL` stays `null`. A malformed, tampered,
  wrong-key, or other-alias token fails with the single error `INVALID_PII_TOKEN`.
- Each result column reports `name`, `source` (`schema`, `table`, `column`, or `null`),
  `protected`, and `encoding` (`json`, `token`, `decimal`, `date`, `time`, `datetime`, `uuid`,
  `base64`).
- Token values are sent to the database only as bind parameters, never inside the SQL text.
