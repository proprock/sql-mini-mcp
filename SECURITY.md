# Security model

The MCP caller, SQL input, database metadata, rows, and tokens are untrusted. The operator,
process environment, host OS, configured database server, and credentials form the trusted
boundary. Database credentials remain the primary authorization control.

PII protection covers only configured columns. Each `pii_safe` server alias has a unique AES-256
key and a distinct authenticated token domain. Tokens are bearer secrets and must not be logged.

SQL validation is an allowlist. Unknown syntax, cross-database names, unresolved tables or
columns, unsupported lineage, and unsupported protected-value types fail closed. The executor
accepts only a `ValidatedQuery` created after the final AST check.

Before merging security changes, run the adversarial, property-based, integration, and mutation
gates described in `CHECKS.md`. Every security-relaxing non-equivalent mutant must be killed.
