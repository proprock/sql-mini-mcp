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
small and use Conventional Commit subjects. Fast checks run for every task. The live SQL Server suite
is mandatory before a milestone is closed or merged, and during any task that changes SQL
generation, execution, result encoding, or reflection (see the milestone live gate in
[CHECKS.md](CHECKS.md)). Deep security checks run before merging the corresponding milestone.
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
