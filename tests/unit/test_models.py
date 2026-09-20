from __future__ import annotations

from sql_mini_mcp.models import (
    ColumnDefinition,
    ForeignKeyDefinition,
    IndexDefinition,
    PrimaryKeyDefinition,
    TableDefinition,
    UniqueConstraintDefinition,
)


def test_table_definition_serializes_to_public_primitive_contract() -> None:
    definition = TableDefinition(
        schema_="dbo",
        name="Orders",
        columns=[
            ColumnDefinition(
                name="Id",
                native_type="int",
                nullable=False,
                autoincrement=True,
                identity={"start": 1, "increment": 1},
                computed=None,
                default="((0))",
            )
        ],
        primary_key=PrimaryKeyDefinition(name="PK_Orders", columns=["Id"]),
        foreign_keys=[
            ForeignKeyDefinition(
                name="FK_Orders_Users",
                columns=["UserId"],
                referred_schema="dbo",
                referred_table="Users",
                referred_columns=["Id"],
                options={"ondelete": "CASCADE"},
            )
        ],
        unique_constraints=[UniqueConstraintDefinition(name="UQ_Orders_Code", columns=["Code"])],
        indexes=[IndexDefinition(name="IX_Orders_Code", columns=["Code"], unique=False)],
    )

    payload = definition.model_dump(mode="json", by_alias=True)

    assert payload["schema"] == "dbo"
    assert "schema_" not in payload
    assert payload["columns"][0]["identity"] == {"start": 1, "increment": 1}
    assert payload["foreign_keys"][0]["options"] == {"ondelete": "CASCADE"}
