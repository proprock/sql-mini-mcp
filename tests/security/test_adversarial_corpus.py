"""Runs every case in tests/security/corpus through DatabaseService.execute_sql.

Each case must fail with its expected error code and must never call the database sink.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from corpus_support import TokenSources, expand, load_cases
from support import FOREIGN, OTHER_KEY, OWN, SpyConnection, spy_service

from sql_safe_mcp.errors import DomainError, ErrorCode
from sql_safe_mcp.security.tokens import PREFIX, TokenCodec
from sql_safe_mcp.service import DatabaseService

TOKENS = TokenSources(OWN, FOREIGN, TokenCodec("srv", OTHER_KEY))
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
    sql = expand(case["sql"], TOKENS)
    expected = ErrorCode(case.get("code", "QUERY_REJECTED"))
    before = len(connection.calls)
    with pytest.raises(DomainError) as info:
        asyncio.run(service.execute_sql("srv", "app", sql))
    assert info.value.code is expected, f"{case_id}: {info.value}"
    assert len(connection.calls) == before, f"{case_id}: reached the database sink"
    message = str(info.value)
    assert PREFIX not in message
    assert len(message) < 400
