# Architecture

`sql-safe-mcp` exposes a small typed MCP API over a `DatabaseService`. The service owns object
resolution and response normalization, `EngineRegistry` owns lazy SQLAlchemy engines, and
`DatabaseExtras` contains only operations that SQLAlchemy Inspector cannot portably express.

## Boundaries

```text
MCPServer -> DatabaseService -> EngineRegistry -> SQLAlchemy Core/Inspector -> DBAPI
                               -> DatabaseExtras
```

Milestone 1 exposes read-only metadata calls. `execute_sql` accepts a strict `SELECT` subset that
passes parse, raw-AST allowlist, reflection, lineage, and PII policy stages
(`security/pipeline.py`). The executor accepts only the resulting `ValidatedQuery`, runs the SQL
generated from the final AST with separate bind parameters, and never executes the original text.
PII keys and policies belong to a server alias, and tokens are authenticated with that alias as
associated data so they cannot cross aliases.

The pipeline is shared by every engine. A `SqlDialect` (`security/dialect.py`, chosen only from
the trusted server `engine`) supplies the SQLGlot dialect, whether objects have a schema level,
and the driver bind marker; policy, tokens, and `ValidatedQuery` contain no dialect logic.

## Milestones

1. SQL Server metadata.
2. SQL Server PII-safe `execute_sql` plus adversarial verification.
3. MySQL/MariaDB metadata (`engine: mysql` or `mariadb`, `mysql+pymysql`), then SQL dialect
   support. MySQL and MariaDB have no schema level: the database is the catalog and `schema` is
   always `null`; a `pii` rule for them must not set `schema`, and `db.table` names are rejected as
   cross-database references.

PostgreSQL, views, HTTP transport, and unrestricted SQL are intentionally deferred.
