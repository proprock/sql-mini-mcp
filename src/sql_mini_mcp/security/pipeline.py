from __future__ import annotations

from sql_mini_mcp.config import PiiConfig, RuntimeConfig
from sql_mini_mcp.security.lineage import analyze_query
from sql_mini_mcp.security.parser import ParserLimits, parse_select
from sql_mini_mcp.security.policy import PiiPolicy
from sql_mini_mcp.security.schema import TableCatalog, resolve_tables
from sql_mini_mcp.security.tokens import TokenCodec
from sql_mini_mcp.security.validated_query import ValidatedQuery, issue_validated_query


def validate_sql(
    sql: str,
    *,
    alias: str,
    database: str,
    catalog: TableCatalog,
    pii_config: PiiConfig,
    codec: TokenCodec,
    runtime: RuntimeConfig,
    max_rows: int,
) -> ValidatedQuery:
    """Run caller SQL through parse, allowlist, reflection, lineage, and PII policy.

    Any rejection raises a DomainError before the catalog or database is used further.
    """
    limits = ParserLimits.from_runtime(runtime)
    query = parse_select(sql, limits)
    tables = resolve_tables(query, catalog)
    analyzed = analyze_query(query, tables, limits)
    decision = PiiPolicy(database, pii_config, codec).evaluate(analyzed)
    return issue_validated_query(
        analyzed,
        decision,
        alias=alias,
        database=database,
        max_rows=max_rows,
        runtime=runtime,
        limits=limits,
    )
