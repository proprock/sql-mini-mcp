# Changelog

All notable externally observable changes to this project are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and uses the
categories `Added`, `Changed`, `Deprecated`, `Removed`, `Fixed`, and `Security`.

## [Unreleased]

## [1.0.0] - 2026-09-20

### Added

- `execute_sql` tool for `pii_safe` SQL Server aliases. It runs one restricted `SELECT`, returns
  configured PII columns as alias-bound tokens, accepts those tokens only in `=` and `IN`
  predicates, and returns at most `max_rows` rows with a `truncated` flag. Servers with
  `access_level: metadata` return `ACCESS_LEVEL_DENIED`.

## [0.9.1] - 2026-09-20

### Added

- Publishing of release-tag packages to PyPI and their metadata to the MCP Registry.

### Fixed

- Source distributions now include only release files, excluding local development caches.

## [0.9.0] - 2026-09-20

### Added

- Read-only SQL Server metadata tools for configured server aliases, databases, tables, and
  stored procedures.
