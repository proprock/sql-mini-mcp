from __future__ import annotations

from dataclasses import dataclass

import sqlglot
from sqlglot import exp

from sql_mini_mcp.config import RuntimeConfig
from sql_mini_mcp.errors import DomainError, ErrorCode

DIALECT = "tsql"


@dataclass(frozen=True, slots=True)
class ParserLimits:
    max_sql_chars: int
    max_ast_nodes: int
    max_joins: int
    max_in_list_items: int

    @classmethod
    def from_runtime(cls, runtime: RuntimeConfig) -> ParserLimits:
        return cls(
            runtime.max_sql_chars,
            runtime.max_ast_nodes,
            runtime.max_joins,
            runtime.max_in_list_items,
        )


def reject(message: str) -> DomainError:
    return DomainError(
        ErrorCode.QUERY_REJECTED,
        f"Query rejected: {message}",
        "Rewrite the operation as a single, simpler SELECT query.",
    )


def check_limits(query: exp.Expression, limits: ParserLimits) -> None:
    """Enforce AST size limits; also used again after transformations."""
    for count, _ in enumerate(query.walk(), start=1):
        if count > limits.max_ast_nodes:
            raise reject("the query exceeds the configured complexity limit.")
    if sum(1 for _ in query.find_all(exp.Join)) > limits.max_joins:
        raise reject("the query has too many joins.")
    for node in query.find_all(exp.In):
        if len(node.expressions) > limits.max_in_list_items:
            raise reject("an IN list exceeds the configured item limit.")


def parse_select(sql: str, limits: ParserLimits) -> exp.Select:
    """Parse exactly one root SELECT; any failure becomes QUERY_REJECTED."""
    if len(sql) > limits.max_sql_chars:
        raise reject("the SQL exceeds the configured length limit.")
    try:
        statements = [s for s in sqlglot.parse(sql, dialect=DIALECT) if s is not None]
        if len(statements) != 1:
            raise reject("exactly one statement is required.")
        query = statements[0]
        if not isinstance(query, exp.Select):
            raise reject("only SELECT statements are supported.")
        check_limits(query, limits)
    except DomainError:
        raise
    except Exception as exc:
        raise reject("the SQL could not be parsed.") from exc
    return query
