# Architecture

`sql-mini-mcp` exposes a small typed MCP API over a `DatabaseService`. The service owns object
resolution and response normalization, `EngineRegistry` owns lazy SQLAlchemy engines, and
`DatabaseExtras` contains only operations that SQLAlchemy Inspector cannot portably express.

## Boundaries

```text
MCPServer -> DatabaseService -> EngineRegistry -> SQLAlchemy Core/Inspector -> DBAPI
                               -> DatabaseExtras
```

Metadata calls are read-only. SQL execution accepts a strict `SELECT` subset and reaches the
executor only as a `ValidatedQuery` produced by the security pipeline. The original SQL is never
executed. PII keys and policies belong to a server alias; tokens are authenticated with that alias
as associated data and cannot cross aliases.

## Milestones

1. SQL Server metadata.
2. SQL Server PII-safe `execute_sql` plus adversarial verification.
3. MySQL/MariaDB metadata and SQL dialect support.

PostgreSQL, views, HTTP transport, and unrestricted SQL are intentionally deferred.
