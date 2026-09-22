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
| `logging` | Optional; see [Logging](#logging). |

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

Because of that encoding, a variable must hold one URL part. Keep the host and the port in separate
variables; a `host:port` value would have its `:` encoded and the driver would look for a host that
does not exist, then fail after its login timeout. A startup error catches an encoded character in
the host:

```yaml
# DEV_SQL_HOST=10.12.11.107  DEV_SQL_PORT=1433
connection_url: "mssql+pyodbc://${DEV_SQL_USER}:${DEV_SQL_PASSWORD}@${DEV_SQL_HOST}:${DEV_SQL_PORT}/master?driver=ODBC+Driver+18+for+SQL+Server"
```


## PII-safe servers

`pii_safe` enables `execute_sql` for a server alias. Such an alias requires its own base64-encoded 32-byte key in the variable named by `pii_key_env`,
plus `pii.rules` listing the protected columns:

```
sql-safe-mcp --gen-pii-key
```

The command prints one key to stdout and exits without loading the configuration or connecting to a
database. Store that value in the secret environment or configuration used by your MCP host under
the variable named by `pii_key_env`; never put it in the YAML file. To generate a separate key for
each of several aliases, pass a positive count. The command prints exactly that many keys, one per
line:

```
sql-safe-mcp --gen-pii-key 3
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

## Logging

Optional, under `logging:`. The server writes to stderr only, using the standard `logging` module;
stdout carries MCP messages and nothing else. Claude Desktop keeps stderr in its MCP log, and other
hosts show it in their own MCP log or console.

```yaml
logging:
  level: INFO # DEBUG, INFO, WARNING or ERROR (uppercase)
```

| Level | What you see |
|---|---|
| `INFO` (default) | Each database connection (`connect ok` or `connect failed`, with server alias, database, and `elapsed_ms`) and each tool operation (`operation ok` or `operation failed`, with the tool name). |
| `DEBUG` | Also engine creation and eviction. |
| `WARNING`, `ERROR` | Failures only. |

A failed connection or operation logs the driver error class, the SQLSTATE or numeric code, and the
driver message. The connection URL's user name and password are replaced with `***` and its host with the
server alias in that message, control characters are replaced, and long messages are truncated. A `TIMEOUT` or
`CONNECTION_FAILED` error shown to the caller carries a `Reference`; the same value appears as
`reference=` on the matching log line.

Reading a failure: `connect failed ... elapsed_ms=` near the login timeout points at reaching or
logging in to the server, while `operation failed` after a `connect ok` points at the query itself.

Connection URLs, credentials, keys, tokens, SQL text, bind values, and result rows are never
logged. SQLAlchemy's own statement logging stays off at every level.
