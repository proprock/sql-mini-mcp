# Configuration

Connection topology lives in a YAML file. Secrets live in the process environment and are pulled in
with `${NAME}` placeholders. A complete example is in
[sql-safe-mcp.example.yaml](../sql-safe-mcp.example.yaml).

## Locating and checking the file

The server reads `--config`, else `SQL_SAFE_MCP_CONFIG`, else `sql-safe-mcp.yaml` in the working
directory. Validate the file and its environment without connecting to any database:

```bash
sql-safe-mcp --check-config
```

Errors name the missing or invalid setting without printing a URL, key, or secret.

## Top-level keys

| Key | Meaning |
|---|---|
| `version` | Required. Must be `1`. |
| `servers` | Required. A non-empty map of alias to server settings. |
| `runtime` | Optional limits; see [Runtime limits](#runtime-limits). |

Unknown keys anywhere in the file are a startup error.

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
| `engine` | `sqlserver` (`mssql+pyodbc`), `mysql` or `mariadb` (both `mysql+pymysql`). MySQL and MariaDB have no schema level: `schema` is always `null`, and a `pii` rule for them must not set `schema` (the table is matched by `database` and `table`). |
| `access_level` | `metadata` (default) or `pii_safe`. |
| `connection_url` | Required. A SQLAlchemy `mssql+pyodbc://` (SQL Server) or `mysql+pymysql://` (MySQL, MariaDB) URL whose dialect must match `engine`. Treated as a secret. |
| `pii_key_env` | Required for `pii_safe`, forbidden otherwise. The name of the environment variable holding the alias key; matches `^[A-Z_][A-Z0-9_]*$`. |
| `pii` | Required for `pii_safe`, forbidden otherwise. Holds `rules`; see [PII rules](#pii-rules). |

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

### PII rules

`pii.rules` is a non-empty list. Each rule protects columns of one table:

| Key | Meaning |
|---|---|
| `database` | Required. An exact database name, or `"*"` for every database. `"*"` is the only wildcard allowed anywhere in a rule. |
| `schema` | Optional, SQL Server only. Omitted means the table is protected in every schema. Must not be set for `mysql` or `mariadb`. |
| `table` | Required. An exact table name. |
| `columns` | Required. A non-empty list of column names, unique ignoring case. |

Names match case-insensitively. Only listed columns are protected, so list every column that holds
personal data. On MySQL and MariaDB the database is the catalog: `database` is the MySQL database
name and the rule has no `schema`.

SQL Server, every database, one table:

```yaml
pii:
  rules:
    - database: "*"
      schema: dbo
      table: Users
      columns: [Email, FirstName, LastName]
```

SQL Server, several tables, one of them limited to a single database:

```yaml
pii:
  rules:
    - database: "*"
      schema: dbo
      table: Users
      columns: [Email, Phone]
    - database: Billing
      schema: dbo
      table: Cards
      columns: [HolderName, LastFour]
    - database: Billing
      schema: audit
      table: Logins
      columns: [IpAddress]
```

SQL Server, `schema` omitted, so `Customers` is protected in every schema:

```yaml
pii:
  rules:
    - database: Crm
      table: Customers
      columns: [Email, BirthDate]
```

MySQL or MariaDB (no `schema`):

```yaml
pii:
  rules:
    - database: shop
      table: customers
      columns: [email, full_name, address]
    - database: "*"
      table: sessions
      columns: [ip_address]
```

These are startup errors:

```yaml
pii:
  rules:
    - database: "*"
      table: "Users*"          # wildcards only in database
      columns: [Email]
    - database: shop
      schema: dbo              # invalid for mysql and mariadb
      table: customers
      columns: [email, EMAIL]  # duplicate column
```

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
| `max_sql_chars` | 65536 | 256-1000000 |
| `max_ast_nodes` | 2000 | 10-100000 |
| `max_joins` | 8 | 0-100 |
| `max_in_list_items` | 500 | 1-100000 |

The last four bound the SQL accepted by `execute_sql`; a query at the limit is accepted and one
above it is rejected.
