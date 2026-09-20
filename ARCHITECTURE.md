# Architecture

`sql-mini-mcp` exposes a small typed MCP API over a `DatabaseService`. The service owns object
resolution and response normalization, `EngineRegistry` owns lazy SQLAlchemy engines, and
`DatabaseExtras` contains only operations that SQLAlchemy Inspector cannot portably express.

## Boundaries

```text
MCPServer -> DatabaseService -> EngineRegistry -> SQLAlchemy Core/Inspector -> DBAPI
                               -> DatabaseExtras
```

Milestone 1 exposes read-only metadata calls only. Milestone 2 will accept a strict `SELECT` subset
and reach its executor only as a `ValidatedQuery` produced by the security pipeline; the original
SQL will never be executed. PII keys and policies belong to a server alias, and future tokens are
authenticated with that alias as associated data so they cannot cross aliases.

## Milestones

1. SQL Server metadata.
2. SQL Server PII-safe `execute_sql` plus adversarial verification.
3. MySQL/MariaDB metadata and SQL dialect support.

PostgreSQL, views, HTTP transport, and unrestricted SQL are intentionally deferred.
