"""Runs every case in tests/security/corpus through DatabaseService.execute_sql.

Each case must fail with its expected error code and must never call the database sink.
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Any

import pytest
import yaml
from support import FOREIGN, OTHER_KEY, OWN, SpyConnection, spy_service

from sql_mini_mcp.errors import DomainError, ErrorCode
from sql_mini_mcp.security.tokens import PREFIX, TokenCodec
from sql_mini_mcp.service import DatabaseService

CORPUS = Path(__file__).parent / "corpus"
TEMPLATE = re.compile(r"\{\{(\w+)(?::(.*?))?\}\}")


def _own_token() -> str:
    return OWN.encrypt("value")


def _std_alphabet_token() -> str:
    for _ in range(500):
        token = _own_token()
        body = token.removeprefix(PREFIX)
        if "-" in body or "_" in body:
            return PREFIX + body.replace("-", "+").replace("_", "/")
    raise AssertionError("could not build a token with a url-safe character")


def _flipped(token: str) -> str:
    middle = len(PREFIX) + (len(token) - len(PREFIX)) // 2
    replacement = "A" if token[middle] != "A" else "B"
    return token[:middle] + replacement + token[middle + 1 :]


def _expand(name: str, arg: str | None) -> str:
    own = _own_token()
    if name == "TOKEN_OWN":
        return own
    if name == "TOKEN_OTHER":
        return FOREIGN.encrypt("value")
    if name == "TOKEN_OTHER_KEY_SAME_ALIAS":
        return TokenCodec("srv", OTHER_KEY).encrypt("value")
    if name == "TOKEN_BODY":
        return own.removeprefix(PREFIX)
    if name == "TOKEN_TRUNCATED":
        return own[:-8]
    if name == "TOKEN_FLIPPED":
        return _flipped(own)
    if name == "TOKEN_STD_ALPHABET":
        return _std_alphabet_token()
    assert arg is not None, name
    if name == "PAD":
        return " " * int(arg)
    text, _, count = arg.rpartition(":")
    if name in {"PAD_CHAR", "REPEAT"}:
        return text * int(count)
    if name == "IN_LIST":
        return ", ".join(str(i) for i in range(int(arg)))
    if name == "NEST":
        depth = int(arg)
        return "(" * depth + "1" + ")" * depth
    if name == "JOINS":
        return "".join(f" JOIN Orders o{i} ON o{i}.Id = u.Id" for i in range(int(arg)))
    raise AssertionError(f"unknown corpus template {name}")


def expand(sql: str) -> str:
    return TEMPLATE.sub(lambda match: _expand(match.group(1), match.group(2)), sql)


def load_cases() -> list[tuple[str, dict[str, Any]]]:
    cases: list[tuple[str, dict[str, Any]]] = []
    for path in sorted(CORPUS.glob("*.yaml")):
        for case in yaml.safe_load(path.read_text(encoding="utf-8")):
            cases.append((f"{path.stem}::{case['name']}", case))
    return cases


CASES = load_cases()


@pytest.fixture(scope="module")
def harness() -> tuple[DatabaseService, SpyConnection]:
    connection = SpyConnection()
    return spy_service(connection), connection


def test_corpus_is_well_formed_and_large_enough() -> None:
    ids = [case_id for case_id, _ in CASES]
    assert len(ids) == len(set(ids)), "duplicate corpus case names"
    assert len(CASES) >= 250
    codes = {member.value for member in ErrorCode}
    for case_id, case in CASES:
        assert case.get("reason"), case_id
        assert isinstance(case["sql"], str), case_id
        assert case.get("code", "QUERY_REJECTED") in codes, case_id
        assert set(case) <= {"name", "sql", "code", "reason"}, case_id


@pytest.mark.parametrize(("case_id", "case"), CASES, ids=[case_id for case_id, _ in CASES])
def test_corpus_case_is_rejected_without_reaching_the_database(
    harness: tuple[DatabaseService, SpyConnection], case_id: str, case: dict[str, Any]
) -> None:
    service, connection = harness
    sql = expand(case["sql"])
    expected = ErrorCode(case.get("code", "QUERY_REJECTED"))
    before = len(connection.calls)
    with pytest.raises(DomainError) as info:
        asyncio.run(service.execute_sql("srv", "app", sql))
    assert info.value.code is expected, f"{case_id}: {info.value}"
    assert len(connection.calls) == before, f"{case_id}: reached the database sink"
    message = str(info.value)
    assert PREFIX not in message
    assert len(message) < 400
