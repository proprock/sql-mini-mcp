# Checks

Fast checks:

```powershell
uv sync --all-groups --locked
uv run ruff format --check .
uv run ruff check .
uv run ty check
uv run pytest tests/unit tests/contract -q
```

Validate the example configuration after defining its documented environment variables:

```powershell
uv run sql-mini-mcp --config sql-mini-mcp.example.yaml --check-config
```

The normal Windows live gate starts or reuses the digest-pinned SQL Server 2022 container and keeps
it running between checks. Test SQL objects and credentials are uniquely named and cleaned after
each run:

```powershell
.\scripts\test-sqlserver.ps1
```

For an externally managed disposable SQL Server, define the admin URL directly:

```powershell
$env:SQL_MINI_MCP_TEST_SQLSERVER_URL = "mssql+pyodbc://..."
uv run pytest tests/integration/sqlserver -m integration
```

Explicit local Docker cleanup is separate from the gate and removes the test container and volume:

```powershell
.\scripts\test-sqlserver.ps1 -Reset
```

Security-fast, deep, and mutation commands belong to Milestone 2 and are intentionally absent from
this metadata-only branch.
