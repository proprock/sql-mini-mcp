# Security model

The MCP caller, SQL input, database metadata, rows, and tokens are untrusted. The operator,
process environment, host OS, configured database server, and credentials form the trusted
boundary. Database credentials remain the primary authorization control.

PII protection covers only configured columns. Each `pii_safe` server alias has a unique AES-256
key and a distinct authenticated token domain. Tokens are bearer secrets and must not be logged.

SQL validation is an allowlist. Unknown syntax, cross-database names, unresolved tables or
columns, unsupported lineage, and unsupported protected-value types fail closed. The executor
accepts only a `ValidatedQuery` created after the final AST check.

Development, observation, and integration testing use only local, disposable, or explicitly
non-production databases. Never use stored production credentials or data, and never commit raw
database captures, connection URLs, result rows, secrets, or PII. Fixtures preserve the needed
behavior while replacing database names, schemas, identifiers, timestamps, and content with
synthetic values; record a short non-sensitive provenance note when a fixture derives from an
observation.

Errors must explain the safe cause and, when known, the caller's corrective action. Logs and
model-visible errors must not expose URLs, credentials, keys, tokens, SQL bind values, database
metadata, or result rows.

Before merging security changes, run the adversarial, property-based, integration, and mutation
gates described in `CHECKS.md`. Every security-relaxing non-equivalent mutant must be killed.
