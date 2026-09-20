"""Hypothesis properties, security-fast profile (deterministic, ~200 examples each)."""

from __future__ import annotations

import property_checks as checks
import pytest
from hypothesis import given
from hypothesis import strategies as st
from sqlglot import exp
from support import Spec, specs

from sql_mini_mcp.errors import DomainError, ErrorCode
from sql_mini_mcp.security.parser import _ALLOWED_ARGS, validate_allowlist

SEEDS = st.integers(0, 2**32 - 1)
ALIAS_NAMES = st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789._-", min_size=1, max_size=12)
SQL_FRAGMENTS = st.lists(
    st.sampled_from(
        [
            "SELECT",
            "FROM",
            "Users",
            "u",
            "WHERE",
            "Email",
            "=",
            "IN",
            "(",
            ")",
            "'",
            "--",
            ";",
            "/*",
            "*/",
            "UNION",
            "JOIN",
            "ON",
            "1",
            "NULL",
            "*",
            ",",
            "TOP",
            "ORDER BY",
            "[",
            "]",
            "pii:v1:",
            "dbo",
            ".",
            "@x",
            "#t",
            "EXEC",
            "DROP TABLE",
            "WITH",
            "AS",
            "NOT",
            "\x00",
        ]
    ),
    max_size=30,
).map(" ".join)


@given(specs(), SEEDS)
def test_valid_specs_are_accepted(spec: Spec, seed: int) -> None:
    checks.check_valid_specs_are_accepted(spec, seed)


@given(specs(), SEEDS, SEEDS)
def test_formatting_does_not_change_the_decision(spec: Spec, a: int, b: int) -> None:
    checks.check_formatting_does_not_change_the_decision(spec, a, b)


@given(specs(), SEEDS)
def test_alias_rename_keeps_lineage(spec: Spec, seed: int) -> None:
    checks.check_alias_rename_keeps_lineage(spec, seed)


@given(specs(), SEEDS)
def test_generated_sql_reparses_and_validates(spec: Spec, seed: int) -> None:
    checks.check_generated_sql_reparses_and_validates(spec, seed)


@given(specs(), SEEDS, st.integers(0, 10_000))
def test_forbidden_constructs_are_rejected_and_never_executed(
    spec: Spec, seed: int, mutation: int
) -> None:
    checks.check_forbidden_constructs_are_rejected_and_never_executed(spec, seed, mutation)


@given(st.one_of(st.text(max_size=200), SQL_FRAGMENTS))
def test_arbitrary_text_never_crashes_and_is_never_executed(text: str) -> None:
    checks.check_arbitrary_text_never_crashes_and_is_never_executed(text)


@given(st.lists(st.text(alphabet="ÀÉÎÕÜßøæ ", min_size=4, max_size=30), min_size=1, max_size=5))
def test_plaintext_is_never_serialized(values: list[str]) -> None:
    checks.check_plaintext_is_never_serialized(values)


@given(st.text(max_size=40), ALIAS_NAMES, ALIAS_NAMES)
def test_token_belongs_to_its_alias(value: str, a: str, b: str) -> None:
    checks.check_token_belongs_to_its_alias(value, a, b)


@given(st.text(max_size=40), st.integers(0, 10_000), st.characters(codec="ascii"))
def test_tampered_token_is_rejected(value: str, position: int, replacement: str) -> None:
    checks.check_tampered_token_is_rejected(value, position, replacement)


@given(st.one_of(st.text(max_size=300), st.binary(max_size=200).map(lambda b: b.hex())))
def test_arbitrary_token_input_only_raises_the_public_error(text: str) -> None:
    checks.check_arbitrary_token_input_only_raises_the_public_error(text)


@given(
    st.one_of(
        st.text(max_size=60),
        st.sampled_from(["x'; DROP TABLE Canary;--", "' OR '1'='1", "'); EXEC xp_cmdshell 'x';--"]),
    )
)
def test_sql_looking_values_stay_binds(value: str) -> None:
    checks.check_sql_looking_values_stay_binds(value)


def _all_expression_classes() -> list[type[exp.Expr]]:
    found: dict[str, type[exp.Expr]] = {}
    pending: list[type[exp.Expr]] = [exp.Expr]
    while pending:
        for cls in pending.pop().__subclasses__():
            if cls.__name__ not in found:
                found[cls.__name__] = cls
                pending.append(cls)
    return [found[name] for name in sorted(found)]


UNKNOWN_NODES = [cls for cls in _all_expression_classes() if cls not in _ALLOWED_ARGS]


@pytest.mark.parametrize("cls", UNKNOWN_NODES, ids=lambda cls: cls.__name__)
def test_every_unlisted_sqlglot_node_is_rejected(cls: type[exp.Expr]) -> None:
    """Unknown defaults reject: no node type outside the allowlist may pass, in any position."""
    if cls is exp.Placeholder:
        pytest.skip("placeholders are admitted only after the token rewrite")
    try:
        node = cls()
        query = exp.select("Id").from_("Users").where(node.copy())
        projected = exp.select(node.copy()).from_("Users")
    except Exception:
        pytest.skip("abstract or argument-requiring node cannot be embedded")
    with pytest.raises(DomainError) as info:
        validate_allowlist(query)
    assert info.value.code is ErrorCode.QUERY_REJECTED
    projected = exp.select(node).from_("Users")
    with pytest.raises(DomainError):
        validate_allowlist(projected)


def test_dangerous_node_types_are_not_allowlisted() -> None:
    assert exp.Anonymous not in _ALLOWED_ARGS
    assert exp.Subquery not in _ALLOWED_ARGS
    assert exp.Union not in _ALLOWED_ARGS
