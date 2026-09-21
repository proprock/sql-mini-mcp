# Changelog

All notable externally observable changes to this project are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and uses the
categories `Added`, `Changed`, `Deprecated`, `Removed`, `Fixed`, and `Security`.

## [Unreleased]

### Added

- Diagnostic logging to stderr, controlled by the new `logging.level` setting (`DEBUG`, `INFO`,
  `WARNING`, or `ERROR`; default `INFO`). It records each database connection attempt (server alias,
  database, elapsed time, and on failure the driver error class, SQLSTATE or code, and message with
  the connection URL's user name, password, and host removed) and each tool operation's outcome.
  Connection URLs, credentials, keys, tokens, SQL, bind values, and rows are never logged.

### Changed

- `TIMEOUT` and `CONNECTION_FAILED` errors now carry a `Reference` that matches the `reference=`
  field of the log line for the same failure.

## [1.2.0] - 2026-09-20

### Added

- MySQL and MariaDB support: `engine: mysql` or `engine: mariadb` with a `mysql+pymysql://` URL.
  All seven tools work on them. MySQL and MariaDB have no schema level, so `schema` is always
  `null` in responses and a `db.table` name is rejected as a cross-database reference.
- `execute_sql` and `pii_safe` on MySQL and MariaDB, with `LIMIT` in place of `TOP`. A `pii` rule
  for these engines must not set `schema`. `TIME` results are returned as `time` values within a
  day; longer values fail with `DATABASE_ERROR`.
- Stored procedures on MySQL and MariaDB report the body from `information_schema.ROUTINES`, which
  is `null` when the login may not see it.
- `COUNT(*)` is accepted on the `mysql` dialect.

### Changed

- **Breaking:** the project is renamed from `sql-mini-mcp` to `sql-safe-mcp`. The package, the
  Python module (`sql_safe_mcp`), the command (`sql-safe-mcp`), the example configuration file, and
  every environment variable (`SQL_MINI_MCP_CONFIG` is now `SQL_SAFE_MCP_CONFIG`) change; the old
  names are not kept as aliases. The `sql-mini-mcp` package on PyPI becomes a deprecated shim that
  depends on `sql-safe-mcp`.
- The `QUERY_REJECTED` reason for a non-integer row limit now reads
  `TOP/LIMIT must be a non-negative integer literal`.

### Security

- MySQL and MariaDB sessions drop `NO_BACKSLASH_ESCAPES`, so the string escaping in the generated
  SQL always means what the validated query means, even if the server enables that mode.
- The validation pipeline takes its SQL dialect only from the trusted server configuration and
  requires it explicitly; policy, tokens, and the validated query are shared by every engine.

## [1.1.0] - 2026-09-20

### Changed

- `QUERY_REJECTED` errors from `execute_sql` now come from a fixed catalog of reasons. The wording
  for unsupported syntax names the construct as `unsupported construct: <Node>` or
  `unsupported option: <Node>.<argument>`; other reasons keep their earlier text.

### Security

- `execute_sql` no longer forwards comments from the caller's SQL to the database. The executed
  statement is generated only from the validated query, so comment text can never become
  executable text.

## [1.0.0] - 2026-09-20

### Added

- `execute_sql` tool for `pii_safe` SQL Server aliases. It runs one restricted `SELECT`, returns
  configured PII columns as alias-bound tokens, accepts those tokens only in `=` and `IN`
  predicates, and returns at most `max_rows` rows with a `truncated` flag. Servers with
  `access_level: metadata` return `ACCESS_LEVEL_DENIED`.

## [0.9.1] - 2026-09-20

### Added

- Publishing of release-tag packages to PyPI and their metadata to the MCP Registry.

### Fixed

- Source distributions now include only release files, excluding local development caches.

## [0.9.0] - 2026-09-20

### Added

- Read-only SQL Server metadata tools for configured server aliases, databases, tables, and
  stored procedures.
