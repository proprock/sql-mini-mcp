<div align="center">

# sql-safe-mcp

A read-only, PII-safe SQL Server, MySQL and MariaDB MCP server for coding agents: schema knowledge and safe queries, with no way to change or leak data.

[![CI](https://github.com/proprock/sql-safe-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/proprock/sql-safe-mcp/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/proprock/sql-safe-mcp)](https://github.com/proprock/sql-safe-mcp/releases)
[![PyPI Version](https://img.shields.io/pypi/v/sql-safe-mcp)](https://pypi.org/project/sql-safe-mcp/)
[![Python](https://img.shields.io/badge/python-3.12%2B-blue)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

[![Model Context Protocol compatible](https://img.shields.io/badge/Model_Context_Protocol-compatible-000000?logo=modelcontextprotocol&logoColor=white)](https://modelcontextprotocol.io)
[![MCP Registry: io.github.proprock/sql-safe-mcp](https://img.shields.io/badge/MCP_Registry-io.github.proprock%2Fsql--mini--mcp-000000?logo=modelcontextprotocol&logoColor=white)](server.json)

<img src="https://raw.githubusercontent.com/proprock/sql-safe-mcp/master/images/luna-guard.jpg" alt="Read the data. Protect the identity." width="760">

<i>Read the data. Protect the identity.</i>

</div>

<!-- mcp-name: io.github.proprock/sql-safe-mcp -->

General-purpose database MCP servers hand the agent a raw SQL prompt and dozens of tools. This
server gives a coding agent the schema knowledge it needs to write correct code - servers,
databases, tables, columns, keys, indexes, stored procedures - and, on servers you mark
`pii_safe`, a way to look at real rows without ever seeing the personal data in them.

## Read-only by design. PII-safe by default

- **Read-only by construction** - seven tools, all annotated read-only. No tool writes data, and
  the server never executes SQL an agent wrote: metadata comes from SQLAlchemy Inspector and fixed
  catalog queries, and `execute_sql` runs only a validated, regenerated `SELECT`.
- **PII-safe by default** - on a `pii_safe` server, the columns you configure come back as
  alias-bound, authenticated tokens (`pii:v1:...`), never as plaintext. An agent can still
  project, count, and filter on them with `=` and `IN` using tokens it was given, so it can follow
  a record without reading it. Tokens do not work on another server alias or with another key.
- **Fails closed** - SQL validation is an allowlist. Unknown syntax, unresolved lineage, and
  unsupported protected-value types are refused, not guessed at. The verification evidence is in
  the [security model](SECURITY-MODEL.md).
- **Least access first** - `access_level: metadata` (the default) exposes schema only;
  `execute_sql` needs an explicit `pii_safe` alias with its own key. Database permissions stay the
  primary control, so use a least-privilege login.

## Also

- **Your aliases, not your network** - the agent sees only the server aliases you configure. There
  is no network discovery, and the catalog is not published as MCP resources.
- **Secrets stay out of sight** - connection URLs live in YAML with `${NAME}` placeholders resolved
  from the environment. They never appear in logs or model-visible errors.
- **Compact, predictable output** - object-rooted results with stable sorting, literal
  case-insensitive name filters, and stored procedure lists that do not expand definitions.
- **Errors an agent can act on** - an ambiguous name lists the candidate schemas. Errors never
  contain connection details, credentials, keys, tokens, or rows.
- **On PyPI** - `uvx sql-safe-mcp`, no repo clone required.

| Tool | Access | Purpose |
|---|---|---|
| `list_servers` | 🟢 read | Configured server aliases |
| `list_databases` | 🟢 read | Databases visible to the credentials |
| `list_tables` | 🟢 read | Base tables, filtered by schema or name |
| `get_table_definition` | 🟢 read | Columns, keys, constraints, and indexes of one table |
| `list_stored_procedures` | 🟢 read | Stored procedures, without definitions |
| `get_stored_procedure` | 🟢 read | The definition of one stored procedure |
| `execute_sql` | 🟢 read | One restricted `SELECT` on a `pii_safe` server; protected columns return tokens |

> [!NOTE]
> **Status:** SQL Server supports every tool. MySQL and MariaDB (`engine: mysql` or `mariadb`,
> `mysql+pymysql` URLs) support every tool too. `schema` is always `null` there because the
> database is the catalog, and `execute_sql` uses `LIMIT` instead of `TOP`. See
> [ARCHITECTURE.md](ARCHITECTURE.md).

- [Install](#install)
- [Configure](#configure)
- [PII-safe queries](#pii-safe-queries)
- [Security](#security)
- [Contributing](#contributing)

More detail lives in [`docs/`](docs): the [configuration reference](docs/configuration.md),
[what the tools return](docs/tools.md), and the [security model](SECURITY-MODEL.md).

## Install

```bash
uvx sql-safe-mcp
```

or

```bash
pip install sql-safe-mcp
```

Pin a version when you want a fixed surface: `uvx sql-safe-mcp==1.2.0`.

Requires Python 3.12+, [uv](https://docs.astral.sh/uv/) (or `pip`), and
[Microsoft ODBC Driver 18 for SQL Server](https://learn.microsoft.com/sql/connect/odbc/download-odbc-driver-for-sql-server)
when you connect to SQL Server. MySQL and MariaDB use the bundled PyMySQL driver and need nothing
else.

Verified against SQL Server 2022, MySQL 8.4, and MariaDB 11.4 (see [CHECKS.md](CHECKS.md)).

## Configure

Copy [sql-safe-mcp.example.yaml](sql-safe-mcp.example.yaml) to `sql-safe-mcp.yaml`, list your
servers, and keep credentials in environment variables:

```yaml
version: 1
servers:
  reporting:
    engine: sqlserver
    access_level: metadata
    connection_url: "${REPORTING_SQL_URL}"
```

Point the server at the file with `SQL_SAFE_MCP_CONFIG` (or `--config`), and check it without
connecting to any database:

```bash
SQL_SAFE_MCP_CONFIG=sql-safe-mcp.yaml uvx sql-safe-mcp --check-config
```

Configuration is validated at startup, and an error names the problem without printing a URL or
secret. Keep credentials in the host's own configuration and never commit them. The server acts
with the database account's permissions, so use a dedicated login with the least access the job
needs. Every setting, including the runtime limits, is in
[configuration.md](docs/configuration.md).

<details>
<summary><b>Claude Code</b></summary>

```bash
claude mcp add --env SQL_SAFE_MCP_CONFIG=/path/to/sql-safe-mcp.yaml --env REPORTING_SQL_URL=mssql+pyodbc://... --transport stdio sql-safe -- uvx sql-safe-mcp
```

Put at least one other option between the last `--env` and the server name, as above - the CLI
otherwise reads the name as another `KEY=value` pair.

</details>

<details>
<summary><b>Claude Desktop</b></summary>

In `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "sql-safe": {
      "command": "uvx",
      "args": ["sql-safe-mcp"],
      "env": {
        "SQL_SAFE_MCP_CONFIG": "/path/to/sql-safe-mcp.yaml",
        "REPORTING_SQL_URL": "mssql+pyodbc://..."
      }
    }
  }
}
```

</details>

<details>
<summary><b>Codex CLI</b></summary>

```bash
codex mcp add sql-safe --env SQL_SAFE_MCP_CONFIG=/path/to/sql-safe-mcp.yaml --env REPORTING_SQL_URL=mssql+pyodbc://... -- uvx sql-safe-mcp
```

</details>

<details>
<summary><b>Any other stdio host</b></summary>

Command `uvx`, argument `sql-safe-mcp`, and the environment variables your configuration
references, plus `SQL_SAFE_MCP_CONFIG`. The server speaks MCP over stdio and logs only to stderr.

</details>

## PII-safe queries

Mark an alias `access_level: pii_safe`, give it its own key, and list the protected columns:

```yaml
servers:
  legacy_prod:
    engine: sqlserver
    access_level: pii_safe
    connection_url: "${LEGACY_PROD_SQL_URL}"
    pii_key_env: LEGACY_PROD_PII_KEY
    pii:
      rules:
        - database: "*"
          schema: dbo
          table: Users
          columns: [Email, FirstName, LastName]
```

`execute_sql` then accepts one restricted `SELECT`. Protected cells come back as tokens, and a
token is accepted only in `=` and `IN` predicates on the same alias. Protection covers the columns
you list, so list every column that holds personal data. The rule format, key generation, and the
accepted SQL are in [configuration.md](docs/configuration.md) and [tools.md](docs/tools.md).

## Security

The MCP caller, SQL input, database metadata, rows, and tokens are untrusted; the operator, the
process environment, and the database credentials are the trusted boundary. Database permissions
remain the primary authorization control - this server never widens them. The full model and its
verification are in [SECURITY-MODEL.md](SECURITY-MODEL.md). To report a vulnerability,
use the private channel in [SECURITY.md](SECURITY.md).

## Contributing

Setup, checks, the test commands, the branch and commit conventions, and the release model are in
[CONTRIBUTING.md](CONTRIBUTING.md). Changes that affect someone running the server are recorded in
[CHANGELOG.md](CHANGELOG.md).

## License

[MIT](LICENSE).
