# Implementation roadmap

Each numbered task is independently reviewable and ends with focused tests.

1. [x] Bootstrap packaging, documentation, quality tools, and MCP entrypoint.
2. [x] Implement strict configuration loading, environment expansion, and per-server keys.
3. [x] Add response models and safe domain errors.
4. [x] Add lazy bounded engine lifecycle and concurrency control.
5. [x] Implement SQL Server database and stored-procedure extras.
6. [x] Implement portable table reflection and unambiguous schema resolution.
7. [x] Register and contract-test six metadata tools.
8. [x] Add opt-in SQL Server metadata integration tests.
9. [ ] Add SQL resource limits and the raw AST allowlist.
10. [ ] Add schema loading, qualification, star expansion, and output lineage.
11. [ ] Add per-server PII policy and authenticated token codec.
12. [ ] Add token-to-bind rewriting and the sealed `ValidatedQuery` boundary.
13. [ ] Add bounded execution, result encoding, and the `execute_sql` tool.
14. [ ] Build the adversarial corpus and property-based invariants.
15. [ ] Run mutation testing and triage every surviving security mutant.
16. [ ] Add SQL Server writable-canary integration tests.
17. [ ] Add MySQL/MariaDB metadata extras and contract tests.
18. [ ] Port the validated SQL pipeline to the MySQL dialect.

Milestone 1 is implemented on `feature/sqlserver-metadata`. Milestone 2 work is isolated on
`feature/sqlserver-pii-sql`; tasks 9-16 remain incomplete until its security gate passes.
