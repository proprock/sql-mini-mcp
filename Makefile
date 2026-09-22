SHELL := /bin/sh

.DEFAULT_GOAL := help

SQLSERVER_COMPOSE := compose.sqlserver.yml
MYSQL_COMPOSE := compose.mysql.yml

.PHONY: help sync format format-check lint typecheck test security security-deep coverage check \
	hooks-install hooks build package-check mutation config-check \
	db-up db-up-sqlserver db-up-mysql db-status db-logs db-down db-down-sqlserver db-down-mysql \
	test-sqlserver test-mysql test-matrix demo-seed

help:
	@printf '%s\n' \
		'Usage: make <target> [VARIABLE=value]' \
		'' \
		'Environment and quality:' \
		'  sync                 Install locked development dependencies.' \
		'  format               Apply Ruff formatting.' \
		'  format-check         Check Ruff formatting without changing files.' \
		'  lint                 Run Ruff lint checks.' \
		'  typecheck            Run ty.' \
		'  test                 Run offline unit and contract tests.' \
		'  security             Run the fast security suite.' \
		'  security-deep        Run the deep, expensive security suite.' \
		'  coverage             Report branch coverage for unit and contract tests.' \
		'  check                Run format-check, lint, typecheck, and test.' \
		'' \
		'Hooks and packaging:' \
		'  hooks-install        Install prek commit hooks.' \
		'  hooks                Run prek against all files.' \
		'  build                Build wheel and source distribution.' \
		'  package-check        Build, install each distribution in a temporary venv, and validate config.' \
		'  mutation             Run mutmut (Linux or WSL only).' \
		'' \
		'Configuration:' \
		'  config-check CONFIG=path/to/config.yaml' \
		'' \
		'Databases (Docker Compose):' \
		'  db-up                Start SQL Server, MySQL, and MariaDB test containers.' \
		'  db-up-sqlserver      Start the SQL Server test container.' \
		'  db-up-mysql          Start the MySQL and MariaDB test containers.' \
		'  db-status            Show all test container states.' \
		'  db-logs              Show the latest logs from all test containers.' \
		'  db-down              Remove all test containers and volumes.' \
		'  db-down-sqlserver    Remove the SQL Server test container and volume.' \
		'  db-down-mysql        Remove the MySQL and MariaDB test containers and volumes.' \
		'' \
		'Live tests and demo data:' \
		'  test-sqlserver [PYTEST_ARGS="..."]' \
		'  test-mysql [PYTEST_ARGS="..."]' \
		'  test-matrix [PYTEST_ARGS="..."]' \
		'  demo-seed [DEMO_ARGS="--reset"]'

sync:
	uv sync --all-groups --locked

format:
	uv run ruff format .

format-check:
	uv run ruff format --check .

lint:
	uv run ruff check .

typecheck:
	uv run ty check

test:
	uv run pytest tests/unit tests/contract -q

security:
	uv run pytest tests/unit tests/contract tests/security -m "not deep" -q

security-deep:
	uv run pytest tests/security -m deep

coverage:
	uv run pytest tests/unit tests/contract --cov=sql_safe_mcp --cov-branch --cov-report=term-missing

check: format-check lint typecheck test

hooks-install:
	uv run prek install

hooks:
	uv run prek run --all-files

build:
	uv build

package-check: build
	@set -eu; \
		temp_dir="$$(mktemp -d)"; \
		trap 'rm -rf "$$temp_dir"' EXIT HUP INT TERM; \
		config="$$temp_dir/sql-safe-mcp-config.yaml"; \
		printf '%s\n' \
			'version: 1' \
			'servers:' \
			'  package-check:' \
			'    engine: sqlserver' \
			'    connection_url: mssql+pyodbc://user:password@host/master?driver=x' > "$$config"; \
		sdist="$$(find dist -maxdepth 1 -type f -name 'sql_safe_mcp-*.tar.gz' -print | sort | tail -n 1)"; \
		wheel="$$(find dist -maxdepth 1 -type f -name 'sql_safe_mcp-*.whl' -print | sort | tail -n 1)"; \
		test -n "$$sdist" && test -n "$$wheel" || { echo 'Expected sql-safe-mcp wheel and sdist in dist/.' >&2; exit 1; }; \
		uv run python -m venv "$$temp_dir/sdist"; \
		"$$temp_dir/sdist/bin/pip" install --quiet "$$sdist"; \
		"$$temp_dir/sdist/bin/sql-safe-mcp" --config "$$config" --check-config; \
		uv run python -m venv "$$temp_dir/wheel"; \
		"$$temp_dir/wheel/bin/pip" install --quiet "$$wheel"; \
		"$$temp_dir/wheel/bin/sql-safe-mcp" --config "$$config" --check-config

mutation:
	@case "$$(uname -s)" in \
		Linux) ;; \
		*) echo 'mutation is supported only on Linux or WSL.' >&2; exit 2 ;; \
	esac
	HYPOTHESIS_PROFILE=security-mutation uv run mutmut run

config-check:
	@if [ -z "$(CONFIG)" ]; then \
		echo 'CONFIG is required. Example: make config-check CONFIG=sql-safe-mcp.example-simple.yaml' >&2; \
		exit 2; \
	fi
	uv run sql-safe-mcp --config "$(CONFIG)" --check-config

db-up: db-up-sqlserver db-up-mysql

db-up-sqlserver:
	@set -eu; \
		if [ -z "$${SQL_SAFE_MCP_DOCKER_SA_PASSWORD+x}" ]; then \
			command -v openssl >/dev/null || { echo 'openssl is required to generate a test password.' >&2; exit 1; }; \
			SQL_SAFE_MCP_DOCKER_SA_PASSWORD="SqlSafeMcp!A1$$(openssl rand -hex 16)"; \
		fi; \
		export SQL_SAFE_MCP_DOCKER_SA_PASSWORD; \
		docker compose -f "$(SQLSERVER_COMPOSE)" up -d --wait

db-up-mysql:
	@set -eu; \
		if [ -z "$${SQL_SAFE_MCP_DOCKER_ROOT_PASSWORD+x}" ]; then \
			command -v openssl >/dev/null || { echo 'openssl is required to generate a test password.' >&2; exit 1; }; \
			SQL_SAFE_MCP_DOCKER_ROOT_PASSWORD="SqlSafeMcp$$(openssl rand -hex 16)"; \
		fi; \
		export SQL_SAFE_MCP_DOCKER_ROOT_PASSWORD; \
		docker compose -f "$(MYSQL_COMPOSE)" up -d --wait

db-status:
	@SQL_SAFE_MCP_DOCKER_SA_PASSWORD="$${SQL_SAFE_MCP_DOCKER_SA_PASSWORD:-inspect}" \
		docker compose -f "$(SQLSERVER_COMPOSE)" ps
	@SQL_SAFE_MCP_DOCKER_ROOT_PASSWORD="$${SQL_SAFE_MCP_DOCKER_ROOT_PASSWORD:-inspect}" \
		docker compose -f "$(MYSQL_COMPOSE)" ps

db-logs:
	@SQL_SAFE_MCP_DOCKER_SA_PASSWORD="$${SQL_SAFE_MCP_DOCKER_SA_PASSWORD:-inspect}" \
		docker compose -f "$(SQLSERVER_COMPOSE)" logs --tail=100
	@SQL_SAFE_MCP_DOCKER_ROOT_PASSWORD="$${SQL_SAFE_MCP_DOCKER_ROOT_PASSWORD:-inspect}" \
		docker compose -f "$(MYSQL_COMPOSE)" logs --tail=100

db-down: db-down-sqlserver db-down-mysql

db-down-sqlserver:
	@SQL_SAFE_MCP_DOCKER_SA_PASSWORD="$${SQL_SAFE_MCP_DOCKER_SA_PASSWORD:-cleanup}" \
		docker compose -f "$(SQLSERVER_COMPOSE)" down --volumes --remove-orphans

db-down-mysql:
	@SQL_SAFE_MCP_DOCKER_ROOT_PASSWORD="$${SQL_SAFE_MCP_DOCKER_ROOT_PASSWORD:-cleanup}" \
		docker compose -f "$(MYSQL_COMPOSE)" down --volumes --remove-orphans

test-sqlserver:
	./scripts/test-sqlserver $(PYTEST_ARGS)

test-mysql:
	./scripts/test-mysql $(PYTEST_ARGS)

test-matrix:
	./scripts/test-matrix $(PYTEST_ARGS)

demo-seed:
	@set -eu; \
		export SQL_SAFE_MCP_DOCKER_SA_PASSWORD="$${SQL_SAFE_MCP_DOCKER_SA_PASSWORD:-inspect}"; \
		container="$$(docker compose -f "$(SQLSERVER_COMPOSE)" ps -q sqlserver)"; \
		test -n "$$container" || { echo 'SQL Server is not running. Run make db-up-sqlserver first.' >&2; exit 1; }; \
		./scripts/seed-data --container "$$container" $(DEMO_ARGS)
