# Checks

Fast checks:

```powershell
uv sync --all-groups --locked
uv run ruff format --check .
uv run ruff check .
uv run ty check
uv run pytest tests/unit tests/contract -q
```

Install the existing commit hooks once after syncing dependencies, then run them before a commit:

```powershell
uv run prek install
uv run prek run --all-files
```

Never bypass a failing hook with `--no-verify`; fix the failure. Hooks do not replace the focused
test suite.

For a behavior-changing implementation phase, review statement and branch coverage separately:

```powershell
uv run pytest tests/unit tests/contract --cov=sql_mini_mcp --cov-branch --cov-report=term-missing
```

Coverage does not replace behavioral assertions. Review the missing-line report, add relevant
tests or document an intentional exclusion, and report the result. Do not state that any check
passed unless it was executed.

GitHub Actions runs this fast suite on supported Python versions and builds both distribution
formats in a clean environment. Docker-backed SQL Server integration tests never run in hosted CI;
they remain an explicit local or externally managed disposable-database gate.

Validate the example configuration after defining its documented environment variables:

```powershell
uv run sql-mini-mcp --config sql-mini-mcp.example.yaml --check-config
```

### Milestone live gate

Per-task work runs the fast suite. A milestone is not closed, marked accepted in the roadmap, or
merged until the live suite also passes against the running SQL Server container with zero skips:

- every tool the milestone adds or changes has a live test through a real MCP client;
- every data path it changes (SQL generation, bind parameters, result types, reflection) is
  exercised with real SQL Server types and rows;
- rejected inputs are shown not to change a canary object;
- the run leaves no test logins or schemas behind.

Also run the live suite, or a focused `-k` subset, during a task that changes SQL generation,
execution, result encoding, reflection, or connection handling: fakes cannot prove those. Record
the date, image digest, ODBC driver, and test counts in the roadmap acceptance note. Passing is
never claimed from a skipped or partial run.

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

The security suite lives in `tests/security` and runs with the fast suite. Add it explicitly when
running a subset:

```powershell
uv run pytest tests/unit tests/contract tests/security -q
```

The deep, mutation, and writable-fixture gates belong to Milestone 2B and are not defined yet.
