# Agent instructions

Read `ARCHITECTURE.md` before changing public contracts or security boundaries.

- Use TDD: add or update a failing focused test, implement minimally, then run the relevant suite.
- Use SQLAlchemy Core and Inspector only; do not add an ORM.
- Treat MCP arguments, SQL, database metadata, rows, and PII tokens as untrusted input.
- Security decisions are allowlists. Unknown SQL AST nodes and unresolved lineage fail closed.
- The executor accepts `ValidatedQuery`, never caller-provided SQL.
- Never log connection URLs, credentials, keys, SQL bind values, tokens, or result rows.
- Keep MCP tools few and responses compact; do not publish tables as MCP resources.
- Keep changes and Conventional Commits task-scoped.

See `CONVENTIONS.md`, `SECURITY.md`, `CHECKS.md`, and `WORKFLOW.md` for task-specific detail.
