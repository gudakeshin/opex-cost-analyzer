"""Base interface for all source system connectors."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List

from app.models import NormalizedSpendLine


@dataclass
class ConnectorConfig:
    """Common configuration shared across connectors."""
    source_system_id: str               # "SAP_001", "COUPA", "GSTR_2A" etc.
    source_system_name: str = ""
    credentials: Dict[str, str] = field(default_factory=dict)
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class FetchResult:
    """Outcome of a connector fetch operation."""
    lines: List[NormalizedSpendLine] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    row_count: int = 0
    source_system_id: str = ""

    @property
    def success(self) -> bool:
        return len(self.lines) > 0 and not self.errors


class ConnectorInterface(ABC):
    """Abstract base for all source system connectors.

    Implementations must be stateless — all state lives in ConnectorConfig.
    """

    def __init__(self, config: ConnectorConfig) -> None:
        self._config = config

    @property
    def source_system_id(self) -> str:
        return self._config.source_system_id

    @abstractmethod
    def authenticate(self) -> bool:
        """Verify credentials / connectivity. Return True on success."""

    @abstractmethod
    def fetch(self, **kwargs: Any) -> FetchResult:
        """Pull data from source and return normalized spend lines."""

    def normalize(self, raw: Any) -> List[NormalizedSpendLine]:
        """Optional: transform raw source records to NormalizedSpendLine."""
        return []
