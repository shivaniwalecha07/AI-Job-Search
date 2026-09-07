"""Portable column types.

VectorType uses pgvector's Vector on PostgreSQL (real ANN-ready embeddings) and falls
back to JSON-encoded text elsewhere (e.g. SQLite for local dev). This lets the same models
run on SQLite for zero-setup development and on Postgres+pgvector in production.
"""
from __future__ import annotations

import json

from sqlalchemy import Text
from sqlalchemy.types import TypeDecorator


class VectorType(TypeDecorator):
    impl = Text
    cache_ok = True

    def __init__(self, dim: int) -> None:
        self.dim = dim
        super().__init__()

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            from pgvector.sqlalchemy import Vector

            return dialect.type_descriptor(Vector(self.dim))
        return dialect.type_descriptor(Text())

    def process_bind_param(self, value, dialect):
        if value is None or dialect.name == "postgresql":
            return value
        return json.dumps(list(value))

    def process_result_value(self, value, dialect):
        if value is None or dialect.name == "postgresql":
            return value
        return json.loads(value)
