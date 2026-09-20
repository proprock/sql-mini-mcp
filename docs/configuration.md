# Configuration

Connection topology lives in a YAML file. Secrets live in the process environment and are pulled in
with `${NAME}` placeholders. A complete example is in
[sql-mini-mcp.example.yaml](../sql-mini-mcp.example.yaml).

## Locating and checking the file

The server reads `--config`, else `SQL_MINI_MCP_CONFIG`, else `sql-mini-mcp.yaml` in the working
directory. Validate the file and its environment without connecting to any database:

```bash
sql-mini-mcp --check-config
```

Errors name the missing or invalid setting without printing a URL, key, or secret.

## Servers

```yaml
version: 1
servers:
  reporting:
    engine: sqlserver
    access_level: metadata
    connection_url: "${REPORTING_SQL_URL}"
```

| Key | Meaning |
|---|---|
| alias (the map key) | Letters, digits, `.`, `_`, `-`; starts with a letter or digit. This is what the agent passes as `server`. |
| `engine` | `sqlserver` (`mssql+pyodbc`), `mysql` or `mariadb` (both `mysql+pymysql`). MySQL and MariaDB are `metadata` only: `pii_safe` is rejected, and `schema` is always `null`. |
| `access_level` | `metadata` (default) or `pii_safe`. |
| `connection_url` | A SQLAlchemy `mssql+pyodbc://` URL. Treated as a secret. |
| `pii_key_env`, `pii` | Only for `pii_safe`; see below. |

### Placeholders

`${NAME}` reads the environment variable `NAME`. A placeholder that occupies the whole
`connection_url` may hold a complete SQLAlchemy URL. A placeholder embedded in a longer URL is
URL-encoded before substitution, so a password containing `@` or `/` is safe. A missing variable is
a startup error.

## PII-safe servers

`pii_safe` enables `execute_sql` for a server alias. Such an alias requires its own base64-encoded 32-byte key in the variable named by `pii_key_env`,
plus `pii.rules` listing the protected columns:

```powershell
$bytes = New-Object byte[] 32
[System.Security.Cryptography.RandomNumberGenerator]::Fill($bytes)
$env:LEGACY_PROD_PII_KEY = [Convert]::ToBase64String($bytes)
```

```bash
export LEGACY_PROD_PII_KEY="$(openssl rand -base64 32)"
```

A key reused by two aliases is rejected. Tokens authenticate the alias as associated data, so
they cannot cross aliases even if keys are duplicated outside normal config loading. Rotating a key
or renaming an alias will invalidate existing tokens. A `metadata` server must not set
`pii_key_env` or `pii`.

## Runtime limits

Optional, under `runtime:`. A value outside its range is a startup error.

| Setting | Default | Range |
|---|---|---|
| `max_concurrent_db_operations` | 8 | 1-128 |
| `engine_cache_size` | 32 | 1-1024 |
| `pool_size` | 2 | 1-32 |
| `max_overflow` | 2 | 0-64 |
| `pool_timeout_seconds` | 10 | 1-300 |
| `statement_timeout_seconds` | 30 | 1-3600 |
| `max_definition_chars` | 262144 | 1024-10000000 |
| `default_max_rows` | 200 | 1-100000, at most `hard_max_rows` |
| `hard_max_rows` | 1000 | 1-100000 |

`max_sql_chars`, `max_ast_nodes`, `max_joins`, and `max_in_list_items` bound the SQL accepted by
`execute_sql`; a query at the limit is accepted and one above it is rejected. A PII rule without
`schema` protects the table in every schema.
