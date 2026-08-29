"""What a migration declares, and what is wrong with it."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class Operation(BaseModel):
    """One `op.*` call in a migration."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: str = Field(min_length=1, description="add_column, create_index, ...")
    table: str = ""
    columns: tuple[str, ...] = ()
    path: str = Field(min_length=1)
    line: int = Field(ge=1)
    keywords: dict[str, str] = Field(
        default_factory=dict,
        description="Keyword arguments as written. `nullable=False` and "
        "`server_default=''` are the difference between a migration that "
        "runs and one that fails on a populated table.",
    )


class SchemaFinding(BaseModel):
    """Something the migrations do that a table with rows will not survive."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    rule: str = Field(min_length=1)
    path: str = Field(min_length=1)
    line: int = Field(ge=1)
    detail: str = Field(min_length=1)
    remediation: str = Field(min_length=1)
