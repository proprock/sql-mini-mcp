from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from sql_mini_mcp.config import load_config
from sql_mini_mcp.errors import DomainError
from sql_mini_mcp.mcp_server import create_server


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the sql-mini-mcp stdio server.")
    parser.add_argument(
        "--config",
        type=Path,
        default=os.environ.get("SQL_MINI_MCP_CONFIG", "sql-mini-mcp.yaml"),
        help="YAML configuration path (default: SQL_MINI_MCP_CONFIG or sql-mini-mcp.yaml)",
    )
    parser.add_argument(
        "--check-config",
        action="store_true",
        help="Validate configuration and secrets without connecting to databases.",
    )
    return parser


def main() -> None:
    args = _parser().parse_args()
    try:
        config = load_config(args.config)
    except DomainError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(2) from None
    if args.check_config:
        print(f"Configuration valid: {len(config.servers)} server alias(es).")
        return
    create_server(config).run("stdio")


if __name__ == "__main__":
    main()
