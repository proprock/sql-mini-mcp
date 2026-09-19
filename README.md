# sql-mini-mcp

Compact MCP server for SQL Server metadata. The current Milestone 1 build is metadata-only;
PII-safe `execute_sql` is developed separately in Milestone 2.

## Tools

- `list_servers`
- `list_databases`
- `list_tables`
- `get_table_definition`
- `list_stored_procedures`
- `get_stored_procedure`

The server does not discover network servers, expose a full catalog as resources, use an ORM, or
execute caller-provided SQL.

## Install and run

Python 3.12–3.14 and `uv` are required. SQL Server uses `pyodbc` and needs an installed ODBC
driver.

```powershell
uv sync --all-groups
Copy-Item sql-mini-mcp.example.yaml sql-mini-mcp.yaml
$env:SQL_MINI_MCP_CONFIG = "$PWD\sql-mini-mcp.yaml"
uv run sql-mini-mcp --check-config
uv run sql-mini-mcp
```

`sql-mini-mcp` speaks MCP over stdio. Configure the same command and environment in the MCP host.
All logs go to stderr.

## Configuration and secrets

Connection topology stays in YAML while `${NAME}` placeholders read process environment values.
A placeholder occupying the entire `connection_url` may contain a complete SQLAlchemy URL;
embedded values are URL-encoded before substitution.

Every `pii_safe` alias requires its own base64-encoded 32-byte key:

```powershell
$bytes = New-Object byte[] 32
[System.Security.Cryptography.RandomNumberGenerator]::Fill($bytes)
$env:LEGACY_PROD_PII_KEY = [Convert]::ToBase64String($bytes)
```

Keys are rejected if reused by two aliases. Milestone 2 will authenticate the server alias as
AES-GCM associated data, so tokens cannot cross aliases even if keys are accidentally duplicated
outside normal config loading. Key rotation or alias renaming will invalidate existing tokens.

See [sql-mini-mcp.example.yaml](sql-mini-mcp.example.yaml) for a complete example.

## Development

```powershell
uv run ruff format --check .
uv run ruff check .
uv run ty check
uv run pytest tests/unit tests/contract -m "not integration"
```

Live and future Milestone 2 security gates are documented in [CHECKS.md](CHECKS.md). Architecture
and threat assumptions are in [ARCHITECTURE.md](ARCHITECTURE.md) and [SECURITY.md](SECURITY.md).
