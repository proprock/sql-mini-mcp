# Agent instructions

Read `ARCHITECTURE.md` before changing public contracts or security boundaries.

- Keep the milestone scope narrow. Do not add database dialects, write tools, HTTP transport, an
  ORM, unrestricted SQL, or other speculative capability without a concrete use case and the
  user's explicit approval.
- Preserve published MCP tool names, arguments, defaults, response schemas, and configuration
  semantics unless a deliberate public contract change is required. Read every linked document
  relevant to the behavior being changed before editing it.
- If, after relevant investigation, the goal, scope, compatibility, security impact, data
  handling, behavior, or implementation choice is unclear, stop and ask the user for a decision
  before making a change. Do not resolve an ambiguity by assumption.
- Use TDD: add or update a failing focused test, implement minimally, then run the relevant suite.
- Use SQLAlchemy Core and Inspector only; do not add an ORM.
- Treat MCP arguments, SQL, database metadata, rows, and PII tokens as untrusted input.
- Security decisions are allowlists. Unknown SQL AST nodes and unresolved lineage fail closed.
- The executor accepts `ValidatedQuery`, never caller-provided SQL.
- Never log connection URLs, credentials, keys, SQL bind values, tokens, or result rows.
- Keep MCP tools few and responses compact; do not publish tables as MCP resources.
- Keep changes and Conventional Commits task-scoped.
- Do not commit process or instruction-document changes without the user's explicit approval.
- Closing a milestone always means a release: ask the user for the version number and put every
  release edit in the milestone PR so only the tag remains (see `WORKFLOW.md`).
- Create a Git worktree only when the source checkout has uncommitted source changes that must be
  preserved, and only after the user explicitly approves it. Use the existing checkout otherwise.
- Do not modify `.gitignore` without the user's explicit approval.

See `CONVENTIONS.md`, `SECURITY-MODEL.md`, `CHECKS.md`, `WORKFLOW.md`, and `CHANGELOG.md` for
task-specific detail. For a small mechanical documentation-only edit, this file and the target
document are sufficient.
