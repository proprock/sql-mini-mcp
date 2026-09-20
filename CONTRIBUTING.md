# Contributing

Thanks for helping. This server is deliberately small, so most of the work is deciding what *not*
to add. Read [Scope](#scope) before opening a pull request.

## Scope

- SQL Server only today. A new dialect (MySQL/MariaDB is planned, PostgreSQL is deferred), an HTTP
  transport, an ORM, or unrestricted SQL needs a concrete use case and maintainer approval first,
  so open an issue before writing code.
- Tools are read-only and few. There are no write tools, and tables are not published as MCP
  resources. Anything else that changes a database needs maintainer approval.
- A new or changed tool, argument, default, response schema, or configuration key is a public API
  change. Read [ARCHITECTURE.md](ARCHITECTURE.md) and [CONVENTIONS.md](CONVENTIONS.md) first, and
  keep published names and semantics unless a deliberate change is required.
- Security decisions are allowlists: unknown SQL AST nodes and unresolved lineage fail closed. Read
  [SECURITY-MODEL.md](SECURITY-MODEL.md) before touching a security boundary.

Agent-assisted contributions follow the same rules; the repository's [AGENTS.md](AGENTS.md) lists
them and links the detail documents.

## Setup

Requires Python 3.12+, [uv](https://docs.astral.sh/uv/), and Microsoft ODBC Driver 18 for SQL Server
for the live tests.

```bash
git clone https://github.com/proprock/sql-mini-mcp
cd sql-mini-mcp
uv sync --all-groups --locked
```

### Commit hooks

`.pre-commit-config.yaml` runs the fast checks on each commit. The runner is
[prek](https://github.com/j178/prek), a fast Rust drop-in for `pre-commit` that reads the same
config. It is a dev dependency, so `uv sync` already installed it:

```bash
uv run prek install
```

Run everything on demand with `uv run prek run --all-files`. Never bypass a failing hook with
`--no-verify`; fix the failure. The full test suite is not a hook.

## Checks

```bash
uv run ruff format --check .
uv run ruff check .
uv run ty check
uv run pytest tests/unit tests/contract -q
uv run pytest tests/unit tests/contract --cov=sql_mini_mcp --cov-branch --cov-report=term-missing
```

`uv run ruff format .` applies formatting. The last command reports statement and branch coverage
with missing lines; review it before closing a change. Coverage never replaces behavioral
assertions. The complete list of gates is in [CHECKS.md](CHECKS.md).

## Tests

The default suite is fully offline and needs no database or credentials. Write a failing focused
test first, then the minimal implementation.

- Fixtures trace to observations of a **local, disposable, or non-production** database. Each keeps
  the observed structure while every database name, schema, identifier, timestamp, and content value
  is synthetic, and records a short non-sensitive provenance note.
- Never commit a raw database capture, connection URL, result row, secret, or PII, even from a test
  database.
- Never log or assert on a connection URL, credential, key, token, or SQL bind value.

Docker-backed SQL Server tests never run in hosted CI. Run them locally against the digest-pinned
SQL Server 2022 container, which needs Docker Desktop in Linux-container mode:

```powershell
.\scripts\test-sqlserver.ps1
```

Each run creates uniquely named objects and removes them afterwards; `-Reset` also removes the
container and its volume. To use an external disposable server instead, set
`SQL_MINI_MCP_TEST_SQLSERVER_URL` and run `uv run pytest tests/integration/sqlserver -m integration`.
Details are in [CHECKS.md](CHECKS.md).

MySQL and MariaDB have their own digest-pinned containers and script, and the release matrix runs
all three engines together:

```powershell
.\scripts\test-mysql.ps1
.\scripts\test-matrix.ps1
```

## Architecture

```text
MCPServer -> DatabaseService -> EngineRegistry -> SQLAlchemy Core/Inspector -> DBAPI
                             -> DatabaseExtras
```

`DatabaseService` owns object resolution and response normalization, `EngineRegistry` owns lazy
engines, and `DatabaseExtras` holds only what SQLAlchemy Inspector cannot portably express. Use
SQLAlchemy Core and Inspector; there is no ORM. The executor will accept a `ValidatedQuery`, never
caller-provided SQL. See [ARCHITECTURE.md](ARCHITECTURE.md).

## Branches, commits, and pull requests

- Use a short-lived `feature/` branch per change. Do not develop directly on `master`.
- Write [Conventional Commits](https://www.conventionalcommits.org/): `feat`, `fix`, `refactor`,
  `test`, `docs`, `ci`, `chore`, `perf`, `build`. Describe the result, in the imperative mood.
- One pull request, one purpose. Before opening it, run the checks above and update the README and
  the docs when behavior changes.
- Pull requests are squash-merged and the branch is deleted afterwards.
- CI (format, lint, types, tests on Python 3.12 and 3.14, package build) must pass.

Full details: [WORKFLOW.md](WORKFLOW.md).

## Changelog

Record every externally observable change in [CHANGELOG.md](CHANGELOG.md) under `## [Unreleased]`,
in the same pull request that makes it. It is written for someone who runs the server, not for
someone reading the diff.

An entry is earned by a tool added, removed, or renamed; a changed argument, default, or response
schema; a configuration value added or changed; error behavior a caller must handle; and anything
security-relevant. Tests, fixtures, CI, refactors, dependency bumps, and documentation do not earn
one. Name the tool or setting in the entry.

## Release model

Semantic versioning, Conventional Commits, short-lived branches, pull-request CI, and tagged
releases. Each tag is a GitHub Release with CI-checked wheel and source distributions attached, and
it is published to [PyPI](https://pypi.org/project/sql-mini-mcp/) and the MCP Registry by the
release workflow.

Releases are cut by the maintainer, and closing a milestone always means a release (see
[WORKFLOW.md](WORKFLOW.md)):

- The `[Unreleased]` section decides the version: a new tool, setting, or other additive capability
  is a MINOR bump; a fix alone is a PATCH.
- A release renames `[Unreleased]` to the new version and date, and bumps `version` in
  `pyproject.toml` and both version fields in `server.json` to match, then runs `uv lock`.
- Creating or pushing a release tag happens only on the maintainer's explicit instruction.

Contributors do not bump versions or create tags.

## Security

Report vulnerabilities privately as described in [SECURITY.md](SECURITY.md), not in a public issue.

## License

By contributing you agree that your contribution is licensed under the project's
[MIT license](LICENSE).
