from __future__ import annotations

from dataclasses import dataclass, field

from sqlglot import exp

from sql_mini_mcp.config import PiiConfig
from sql_mini_mcp.security.lineage import AnalyzedQuery, ColumnRef, SourceColumn
from sql_mini_mcp.security.parser import reject
from sql_mini_mcp.security.reasons import Reason
from sql_mini_mcp.security.tokens import PREFIX, TokenCodec


@dataclass(frozen=True, slots=True)
class TokenSite:
    """A token literal in an allowed predicate position and its decrypted bind value."""

    literal: exp.Literal
    value: object = field(repr=False)


@dataclass(frozen=True, slots=True)
class PolicyDecision:
    protected: tuple[bool, ...]
    token_sites: tuple[TokenSite, ...]


class PiiPolicy:
    """Decides protected-column usage from source lineage and configured rules only."""

    def __init__(self, database: str, config: PiiConfig, codec: TokenCodec) -> None:
        self._database = database.casefold()
        self._config = config
        self._codec = codec

    def is_protected(self, source: SourceColumn) -> bool:
        schema = source.schema.casefold()
        table = source.table.casefold()
        column = source.column.casefold()
        for rule in self._config.rules:
            if rule.database != "*" and rule.database.casefold() != self._database:
                continue
            if rule.schema_ is not None and rule.schema_.casefold() != schema:
                continue
            if rule.table.casefold() == table and column in {c.casefold() for c in rule.columns}:
                return True
        return False

    def evaluate(self, analyzed: AnalyzedQuery) -> PolicyDecision:
        sites: list[TokenSite] = []
        for ref in analyzed.references:
            if self.is_protected(ref.source):
                sites.extend(self._check_protected(ref))
        consumed = {id(site.literal) for site in sites}
        for literal in analyzed.query.find_all(exp.Literal):
            if (
                literal.is_string
                and str(literal.this).startswith(PREFIX)
                and id(literal) not in consumed
            ):
                raise reject(Reason.TOKEN_OUTSIDE_PROTECTED)
        protected = tuple(
            output.source is not None and self.is_protected(output.source)
            for output in analyzed.outputs
        )
        return PolicyDecision(protected, tuple(sites))

    def _check_protected(self, ref: ColumnRef) -> list[TokenSite]:
        column = ref.node
        parent = column.parent
        if isinstance(parent, exp.Select):
            return []
        if isinstance(parent, exp.Alias) and isinstance(parent.parent, exp.Select):
            return []
        if not _in_where(column):
            raise reject(Reason.PROTECTED_POSITION)
        if isinstance(parent, exp.EQ) and parent.this is column:
            return [self._token_site(parent.expression)]
        if isinstance(parent, exp.In) and parent.this is column and parent.expressions:
            return [self._token_site(item) for item in parent.expressions]
        raise reject(Reason.PROTECTED_POSITION)

    def _token_site(self, node: exp.Expression) -> TokenSite:
        if (
            not isinstance(node, exp.Literal)
            or not node.is_string
            or not str(node.this).startswith(PREFIX)
        ):
            raise reject(Reason.PROTECTED_NEEDS_TOKEN)
        return TokenSite(node, self._codec.decrypt(str(node.this)))


def _in_where(node: exp.Expression) -> bool:
    current = node.parent
    while current is not None:
        if isinstance(current, exp.Where):
            return True
        if isinstance(current, exp.Join | exp.Order | exp.Select):
            return False
        current = current.parent
    return False
