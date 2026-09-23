# Workflow

## Task routing

- **Mechanical:** locate the target, patch it, verify the exact old/new pattern, and report. Do
  not add design work unless risk requires it.
- **Debug:** reproduce once, inspect evidence, form a hypothesis, make the smallest fix, run a
  focused test, then the relevant broader check. Before rerunning an expensive failed command,
  state what changed.
- **Feature:** use a focused branch when one is needed, plan, use TDD, implement, and validate.
- **UI:** use browser or visual verification; use native GUI automation only for a concrete
  inspection goal.
- **Docs/report:** refresh data and produce attributed Markdown; beyond documentation review, run
  only diff hygiene unless the changed documentation requires another check.

When an intended change is ambiguous after investigation, ask the user for a decision before
editing. This applies to code, public contracts, configuration, security, data, process, and
documentation changes.

## Ownership and delegation

The primary agent owns architecture, public MCP contracts, cross-module work, security-sensitive
changes, integration, final review, and acceptance criteria. Delegate only substantial, bounded,
decision-complete work with explicit scope, constraints, expected behavior, tests, and exclusions.
Review delegated output and independently verify relevant results before integration; do not
delegate tiny edits or tightly coupled decisions.

## Development and Git

Prefer explicit code, small public APIs, stable schemas, and compatibility over convenience. Avoid
speculative functionality and trivial new dependencies.

Use `feature/` branches. Write a focused failing test before each behavior change. Keep commits
small and use Conventional Commit subjects. The commit/PR fast gate runs for every task. The live SQL Server suite
is mandatory before a milestone is closed or merged, and during any task that changes SQL
generation, execution, result encoding, or reflection (see the milestone live gate in
[checks.md](checks.md)). Deep security checks run before merging the corresponding milestone.
Squash merge reviewed feature branches and delete them after merge.

Run the configured `prek` hooks before committing and never bypass them with `--no-verify`. Do not
commit process or instruction-document changes without the user's explicit approval.

Record each externally observable change under `## [Unreleased]` in `CHANGELOG.md` in the same
change: tool names, arguments, defaults, response schemas, configuration semantics, caller-visible
errors, and security behavior. Tests, fixtures, CI, refactors, dependency updates, documentation,
and internal helpers do not earn an entry.

GitHub Actions validates the non-Docker suite and clean package installations. Docker-backed SQL
Server integration tests remain an opt-in local gate. Release tags create a GitHub Release with the
checked wheel and source distribution and publish the package to PyPI and its metadata to the MCP
Registry. Creating or pushing a release tag requires the maintainer's explicit instruction.

## Milestone closure is a release

Closing a milestone always means cutting a release. Before the milestone's pull request is
opened, ask the user for the version number; do not choose it. The suggested bump follows
[CONTRIBUTING.md](../CONTRIBUTING.md) (additive capability is MINOR, a fix alone is PATCH), but the
user decides.

Make every release edit in the milestone pull request itself, so that after it merges only the tag
is left to create:

- rename `## [Unreleased]` in `CHANGELOG.md` to the version and date, leaving a fresh empty
  `## [Unreleased]` above it;
- bump `version` in `pyproject.toml`, both version fields in `server.json`, `__version__` in
  `src/sql_safe_mcp/__init__.py`, the server version in `src/sql_safe_mcp/mcp_server.py`, and the
  assertions in `tests/unit/test_version.py`, then run `uv lock`;
- update README and documentation status notes and pinned-version examples;
- run the commit/PR fast gate, the milestone/release security gate, and the prek hooks on that final state.

The release workflow creates a GitHub Release draft before publishing to PyPI and the MCP Registry.
If a downstream publication fails, rerun the failed job and its blocked downstream jobs. Use the
manual `registry` stage only after confirming the package version exists on PyPI; use
`github-release` only after confirming Registry publication. Neither recovery path republishes PyPI.

The tag itself is created and pushed only on the maintainer's explicit instruction after the merge,
and only from the merged commit on `master`.
