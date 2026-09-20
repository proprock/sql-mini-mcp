<div align="center">

# sql-mini-mcp

A read-only SQL Server MCP server for coding agents: 6 metadata tools, no unrestricted SQL.

[![CI](https://github.com/proprock/sql-mini-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/proprock/sql-mini-mcp/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/proprock/sql-mini-mcp)](https://github.com/proprock/sql-mini-mcp/releases)
[![PyPI Version](https://img.shields.io/pypi/v/sql-mini-mcp)](https://pypi.org/project/sql-mini-mcp/)
[![Python](https://img.shields.io/badge/python-3.12%2B-blue)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

[![Model Context Protocol compatible](https://img.shields.io/badge/Model_Context_Protocol-compatible-000000?logo=modelcontextprotocol&logoColor=white)](https://modelcontextprotocol.io)
[![MCP Registry: io.github.proprock/sql-mini-mcp](https://img.shields.io/badge/MCP_Registry-io.github.proprock%2Fsql--mini--mcp-000000?logo=modelcontextprotocol&logoColor=white)](server.json)

<img src="https://raw.githubusercontent.com/proprock/sql-mini-mcp/master/images/luna-guard.jpg" alt="Read the data. Protect the identity." width="760">

<i>Read the data. Protect the identity.</i>

</div>

<!-- mcp-name: io.github.proprock/sql-mini-mcp -->

General-purpose database MCP servers hand the agent a raw SQL prompt and dozens of tools. This
server gives a coding agent the schema knowledge it needs to write correct code - servers,
databases, tables, columns, keys, indexes, stored procedures - and nothing that can change or leak
data.

- **6 tools, all read-only** - every one is annotated read-only and earns its place in context; see
  [tools](docs/tools.md).
<!-- - **Read-only by design. PII-safe by default.** [placeholder] -->
- **No caller-provided SQL** - the server never executes SQL an agent wrote. Metadata comes from
  SQLAlchemy Inspector and fixed catalog queries.
- **Your aliases, not your network** - the agent sees only the server aliases you configure. There
  is no network discovery, and the catalog is not published as MCP resources.
- **Secrets stay out of sight** - connection URLs live in YAML with `${NAME}` placeholders resolved
  from the environment. They never appear in logs or model-visible errors.
- **Compact, predictable output** - object-rooted results with stable sorting, literal
  case-insensitive name filters, and stored procedure lists that do not expand definitions.
- **Errors an agent can act on** - an ambiguous name lists the candidate schemas. Errors never
  contain connection details, credentials, or rows.
- **Fails closed** - security decisions are allowlists; anything unrecognized is refused.
- **On PyPI** - `uvx sql-mini-mcp`, no repo clone required.

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
> **Status:** SQL Server only. MySQL/MariaDB is planned; see [ARCHITECTURE.md](ARCHITECTURE.md).
> Configuration for MySQL/MariaDB is rejected until it ships.

- [Install](#install)
- [Configure](#configure)
- [Security](#security)
- [Contributing and security](#contributing-and-security)

More detail lives in [`docs/`](docs): the [configuration reference](docs/configuration.md) and
[what the tools return](docs/tools.md).

## Install

```bash
uvx sql-mini-mcp
```

or

```bash
pip install sql-mini-mcp
```

Pin a version when you want a fixed surface: `uvx sql-mini-mcp==1.1.0`.

Requires Python 3.12+, [uv](https://docs.astral.sh/uv/) (or `pip`), and
[Microsoft ODBC Driver 18 for SQL Server](https://learn.microsoft.com/sql/connect/odbc/download-odbc-driver-for-sql-server).

## Configure

Copy [sql-mini-mcp.example.yaml](sql-mini-mcp.example.yaml) to `sql-mini-mcp.yaml`, list your
servers, and keep credentials in environment variables:

```yaml
version: 1
servers:
  reporting:
    engine: sqlserver
    access_level: metadata
    connection_url: "${REPORTING_SQL_URL}"
```

Point the server at the file with `SQL_MINI_MCP_CONFIG` (or `--config`), and check it without
connecting to any database:

```bash
SQL_MINI_MCP_CONFIG=sql-mini-mcp.yaml uvx sql-mini-mcp --check-config
```

Configuration is validated at startup, and an error names the problem without printing a URL or
secret. Keep credentials in the host's own configuration and never commit them. The server acts
with the database account's permissions, so use a dedicated login with the least access the job
needs. Every setting, including the runtime limits, is in
[configuration.md](docs/configuration.md).

<details>
<summary><b>Claude Code</b></summary>

```bash
claude mcp add --env SQL_MINI_MCP_CONFIG=/path/to/sql-mini-mcp.yaml --env REPORTING_SQL_URL=mssql+pyodbc://... --transport stdio sql-mini -- uvx sql-mini-mcp
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
    "sql-mini": {
      "command": "uvx",
      "args": ["sql-mini-mcp"],
      "env": {
        "SQL_MINI_MCP_CONFIG": "/path/to/sql-mini-mcp.yaml",
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
codex mcp add sql-mini --env SQL_MINI_MCP_CONFIG=/path/to/sql-mini-mcp.yaml --env REPORTING_SQL_URL=mssql+pyodbc://... -- uvx sql-mini-mcp
```

</details>

<details>
<summary><b>Any other stdio host</b></summary>

Command `uvx`, argument `sql-mini-mcp`, and the environment variables your configuration
references, plus `SQL_MINI_MCP_CONFIG`. The server speaks MCP over stdio and logs only to stderr.

</details>

## Security

The MCP caller, SQL input, database metadata, rows, and tokens are untrusted; the operator, the
process environment, and the database credentials are the trusted boundary. Database permissions
remain the primary authorization control - this server never widens them. The full model, and how
to report a vulnerability, are in [SECURITY.md](SECURITY.md).

## Contributing and security

Setup, checks, the test commands, the branch and commit conventions, and the release model are in
[CONTRIBUTING.md](CONTRIBUTING.md). Report vulnerabilities privately as described in
[SECURITY.md](SECURITY.md). Changes that affect someone running the server are recorded in
[CHANGELOG.md](CHANGELOG.md).

## License

[MIT](LICENSE).
