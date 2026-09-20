# Security policy

## Supported versions

Only the latest release receives security fixes. The project is a small, rolling 0.x line; upgrade
to the newest version from [PyPI](https://pypi.org/project/sql-mini-mcp/) or the
[Releases](https://github.com/proprock/sql-mini-mcp/releases) page.

## Reporting a vulnerability

Do not open a public issue for a security problem. Use GitHub's private vulnerability reporting
instead:

**[Report a vulnerability](https://github.com/proprock/sql-mini-mcp/security/advisories/new)**

Please include the affected version, what you observed, the steps to reproduce it against a
disposable, non-production database, and a suggested fix if you have one. Never include a real
connection URL, credential, PII key, token, or customer data in a report; redact them.

## What to expect

This is a small project with one maintainer, so timelines are best effort:

- an acknowledgment within about 7 days;
- an assessment and a plan once the report is understood;
- coordinated disclosure: the fix ships in a release before details are made public, and the
  reporter is credited in the advisory unless they prefer not to be.

There is no fixed patch deadline; severity decides the order of work.

## Security model

The MCP caller, SQL input, database metadata, rows, and tokens are untrusted. The operator, process
environment, host OS, configured database server, and credentials form the trusted boundary.
Database credentials remain the primary authorization control.

PII protection covers only configured columns. Each `pii_safe` server alias has a unique AES-256
key and a distinct authenticated token domain. Tokens are bearer secrets and must not be logged.

SQL validation is an allowlist. Unknown syntax, cross-database names, unresolved tables or columns,
unsupported lineage, and unsupported protected-value types fail closed. The executor accepts only a
`ValidatedQuery` created after the final AST check.

Errors must explain the safe cause and, when known, the caller's corrective action. Logs and
model-visible errors must not expose URLs, credentials, keys, tokens, SQL bind values, database
metadata, or result rows.

Before merging security changes, run the adversarial, property-based, integration, and mutation
gates described in [CHECKS.md](CHECKS.md). Every security-relaxing non-equivalent mutant must be
killed.

## In scope

Problems in this server's own code, such as:

- a connection URL, credential, PII key, token, SQL bind value, or result row reaching a log, a
  startup message, or a model-visible error;
- the server executing SQL that did not come from a `ValidatedQuery`, or any tool changing data;
- a name or filter reaching SQL by concatenation instead of a bound or quoted identifier;
- a PII token that decrypts under another server alias, or protected values leaving a `pii_safe`
  server in the clear;
- a configuration that is accepted but weaker than it declares, such as a duplicated PII key;
- an unknown or unresolved construct that is allowed instead of refused.

## Out of scope

- Vulnerabilities in SQL Server, ODBC drivers, or third-party dependencies (report those upstream).
- An attacker who already holds the database credentials or PII keys, or controls the host that
  runs the server.
- What the configured database account is allowed to do; this server never widens or narrows
  database permissions.
- PII outside the columns you configured. Protection covers configured columns only.
- Prompt injection carried in database content. Table data, stored procedure bodies, and metadata
  are untrusted input to the agent that reads them; treat them that way.

## Running the server safely

- Use a dedicated database login with the least permission the job needs. Prefer a login that can
  read metadata only.
- Keep connection URLs and PII keys in the host's own configuration or environment. Never commit
  them or a `.env` file, and rotate a credential or key at once if it is exposed.
- Give every `pii_safe` alias its own key. Rotating a key or renaming an alias invalidates its
  existing tokens.
- Use a local, disposable, or explicitly non-production database for development and testing, never
  stored production credentials or data, and never commit raw database captures; see
  [CONTRIBUTING.md](CONTRIBUTING.md).
