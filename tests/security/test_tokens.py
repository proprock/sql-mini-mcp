import base64
import json
from datetime import UTC, date, datetime, time
from decimal import Decimal
from uuid import UUID

import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from sql_safe_mcp.config import AppConfig
from sql_safe_mcp.errors import DomainError, ErrorCode
from sql_safe_mcp.security.tokens import MAX_TOKEN_CHARS, TokenCodec, TokenKeyRegistry

KEY = bytes(range(32))
OTHER_KEY = bytes(range(1, 33))

VALUES = [
    "plain",
    "",
    "x'; DROP TABLE Canary;--",
    "üñí \U0001f600 ‮",
    0,
    -7,
    2**70,
    True,
    False,
    1.5,
    Decimal("12345.67890"),
    date(2024, 2, 29),
    datetime(2024, 2, 29, 13, 14, 15, 123456),
    datetime(2024, 2, 29, 13, 14, 15, tzinfo=UTC),
    time(1, 2, 3, 4),
    UUID("12345678-1234-5678-1234-567812345678"),
    b"\x00\xff\x10",
]


def invalid(token: str, codec: TokenCodec) -> DomainError:
    with pytest.raises(DomainError) as info:
        codec.decrypt(token)
    assert info.value.code is ErrorCode.INVALID_PII_TOKEN
    return info.value


@pytest.mark.parametrize("value", VALUES, ids=[repr(v)[:30] for v in VALUES])
def test_round_trip_preserves_type_and_value(value: object) -> None:
    codec = TokenCodec("srv", KEY)
    token = codec.encrypt(value)
    assert token.startswith("pii:v1:")
    decoded = codec.decrypt(token)
    assert decoded == value
    assert type(decoded) is type(value)


def test_null_is_not_tokenized() -> None:
    assert TokenCodec("srv", KEY).encrypt(None) is None


def test_nonce_is_random() -> None:
    codec = TokenCodec("srv", KEY)
    assert codec.encrypt("same") != codec.encrypt("same")


def test_token_layout_is_nonce_ciphertext_tag() -> None:
    token = TokenCodec("srv", KEY).encrypt("a")
    raw = base64.urlsafe_b64decode(token.removeprefix("pii:v1:") + "==")
    assert len(raw) == 12 + len(b'{"v":1,"t":"str","d":"a"}') + 16


def test_token_is_bound_to_its_alias_even_with_the_same_key() -> None:
    token = TokenCodec("alpha", KEY).encrypt("secret")
    invalid(token, TokenCodec("beta", KEY))
    assert TokenCodec("alpha", KEY).decrypt(token) == "secret"


def test_wrong_key_is_rejected_and_rotation_invalidates_tokens() -> None:
    token = TokenCodec("srv", KEY).encrypt("secret")
    invalid(token, TokenCodec("srv", OTHER_KEY))


def _corruptions(token: str) -> list[str]:
    body = token.removeprefix("pii:v1:")
    flipped = [
        "pii:v1:" + body[:i] + ("A" if body[i] != "A" else "B") + body[i + 1 :]
        for i in range(0, len(body), 3)
    ]
    return [
        *flipped,
        "",
        "pii:v1:",
        "pii:v2:" + body,
        "PII:v1:" + body,
        "pii:v1:" + body[:-4],
        "pii:v1:" + body + "AAAA",
        "pii:v1:" + body + "=",
        "pii:v1:" + body.replace("-", "+").replace("_", "/") + "\n",
        "pii:v1: " + body,
        "pii:v1:" + body + "é",
        "pii:v1:" + "!" * len(body),
        body,
        "pii:v1:" + "A" * (MAX_TOKEN_CHARS + 1),
        "\x00",
        "\ud800",
    ]


def test_every_malformed_or_tampered_token_gives_the_same_error() -> None:
    codec = TokenCodec("srv", KEY)
    errors = {repr(invalid(item, codec)) for item in _corruptions(codec.encrypt("secret" * 4))}
    assert len(errors) == 1
    assert "secret" not in next(iter(errors))


def test_wrong_key_wrong_alias_and_malformed_are_indistinguishable() -> None:
    token = TokenCodec("srv", KEY).encrypt("v")
    results = {
        repr(invalid(token, TokenCodec("srv", OTHER_KEY))),
        repr(invalid(token, TokenCodec("other", KEY))),
        repr(invalid("pii:v1:AAAA", TokenCodec("srv", KEY))),
    }
    assert len(results) == 1


def _forge(codec_alias: str, payload: bytes) -> str:
    nonce = bytes(12)
    aad = f"pii:v1\x00{codec_alias}".encode()
    sealed = AESGCM(KEY).encrypt(nonce, payload, aad)
    return "pii:v1:" + base64.urlsafe_b64encode(nonce + sealed).decode().rstrip("=")


@pytest.mark.parametrize(
    "payload",
    [
        b"not json",
        b"[]",
        b'{"v":1,"t":"str"}',
        b'{"v":1,"t":"str","d":1}',
        b'{"v":2,"t":"str","d":"x"}',
        b'{"v":1,"t":"unknown","d":"x"}',
        b'{"v":1,"t":"str","d":"x","extra":1}',
        b'{"v":1,"t":"int","d":"1"}',
        b'{"v":1,"t":"int","d":true}',
        b'{"v":1,"t":"bool","d":1}',
        b'{"v":1,"t":"date","d":"nope"}',
        b'{"v":1,"t":"bytes","d":"!!"}',
        b'{"v":1,"t":"float","d":NaN}',
        b"\xff\xfe",
    ],
)
def test_authentic_but_invalid_payload_is_rejected(payload: bytes) -> None:
    invalid(_forge("srv", payload), TokenCodec("srv", KEY))


def test_forged_well_formed_payload_is_accepted_only_with_the_key() -> None:
    payload = json.dumps({"v": 1, "t": "str", "d": "ok"}, separators=(",", ":")).encode()
    assert TokenCodec("srv", KEY).decrypt(_forge("srv", payload)) == "ok"


@pytest.mark.parametrize("value", [float("nan"), float("inf"), object(), [1], {"a": 1}, 1j])
def test_unsupported_values_fail_closed_without_leaking(value: object) -> None:
    with pytest.raises(DomainError) as info:
        TokenCodec("srv", KEY).encrypt(value)
    assert info.value.code is ErrorCode.QUERY_REJECTED


def test_oversized_plaintext_is_rejected() -> None:
    with pytest.raises(DomainError) as info:
        TokenCodec("srv", KEY).encrypt("x" * MAX_TOKEN_CHARS)
    assert info.value.code is ErrorCode.QUERY_REJECTED


def test_codec_rejects_bad_key_length_and_hides_key_in_repr() -> None:
    with pytest.raises(ValueError, match="32 bytes"):
        TokenCodec("srv", b"short")
    codec = TokenCodec("srv", KEY)
    assert KEY.hex() not in repr(codec) + str(codec)
    assert repr(KEY) not in repr(codec)


def _config(keys: dict[str, bytes | None]) -> AppConfig:
    servers = {}
    for alias, key in keys.items():
        server: dict[str, object] = {
            "engine": "sqlserver",
            "connection_url": "mssql+pyodbc://u:p@h/d?driver=x",
        }
        if key is not None:
            server.update(
                access_level="pii_safe",
                pii_key_env="K",
                pii={"rules": [{"database": "*", "table": "T", "columns": ["c"]}]},
                pii_key=base64.b64encode(key).decode(),
            )
        servers[alias] = server
    return AppConfig.model_validate({"version": 1, "servers": servers})


def test_registry_builds_codecs_only_for_pii_safe_aliases() -> None:
    registry = TokenKeyRegistry.from_config(_config({"a": KEY, "b": OTHER_KEY, "m": None}))
    token = registry.codec_for("a").encrypt("x")
    invalid(token, registry.codec_for("b"))
    for alias in ("m", "missing"):
        with pytest.raises(DomainError) as info:
            registry.codec_for(alias)
        assert info.value.code is ErrorCode.ACCESS_LEVEL_DENIED


def test_registry_repr_hides_keys() -> None:
    registry = TokenKeyRegistry.from_config(_config({"a": KEY}))
    assert KEY.hex() not in repr(registry)
    assert base64.b64encode(KEY).decode() not in repr(registry)
