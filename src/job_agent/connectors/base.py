"""SourceConnector protocol + a small registry/factory (see ARCHITECTURE.md 4.1, 8).

`requires_supervision=True` connectors are excluded from the unattended cron and only
run via the supervised lane (LinkedIn).
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol, runtime_checkable

from job_agent.schemas.core import RawJobRecord, SourceHealth


@runtime_checkable
class SourceConnector(Protocol):
    source_id: str
    requires_supervision: bool

    def fetch(self, since: datetime | None = None) -> list[RawJobRecord]: ...

    def health(self) -> SourceHealth: ...


class BaseConnector:
    """Convenience base with shared attrs; concrete connectors subclass and implement fetch()."""

    requires_supervision: bool = False

    def __init__(self, source_id: str, params: dict[str, Any] | None = None) -> None:
        self.source_id = source_id
        self.params = params or {}

    def fetch(self, since: datetime | None = None) -> list[RawJobRecord]:  # pragma: no cover
        raise NotImplementedError

    def health(self) -> SourceHealth:
        return SourceHealth(source_id=self.source_id, ok=True, detail="base")


# Registry of connector type -> class. Concrete classes register here.
CONNECTOR_TYPES: dict[str, type[BaseConnector]] = {}


def register(type_name: str):
    def _wrap(cls: type[BaseConnector]) -> type[BaseConnector]:
        CONNECTOR_TYPES[type_name] = cls
        return cls

    return _wrap


def build_connector(type_name: str, source_id: str, params: dict[str, Any]) -> BaseConnector:
    if type_name not in CONNECTOR_TYPES:
        raise ValueError(f"Unknown connector type: {type_name!r}. Registered: {list(CONNECTOR_TYPES)}")
    return CONNECTOR_TYPES[type_name](source_id=source_id, params=params)
