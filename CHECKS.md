# Checks

Fast checks:

```powershell
uv run ruff format --check .
uv run ruff check .
uv run ty check
uv run pytest tests/unit tests/contract tests/security -m "not deep"
```

Live SQL Server checks require `SQL_MINI_MCP_TEST_SQLSERVER_URL`:

```powershell
uv run pytest tests/integration/sqlserver -m integration
```

Deep security checks:

```powershell
uv run pytest tests/security -m deep
```

`mutmut` requires fork support. Run it in Linux CI or WSL:

```text
uv run mutmut run
uv run mutmut results
```

There must be no unexplained surviving mutant in a security decision branch.
