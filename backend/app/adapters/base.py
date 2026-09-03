from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.models.transaction import SourceData


@dataclass(frozen=True)
class FetchParams:
    start_date: str | None = None
    end_date: str | None = None
    limit: int = 100


class RealDataAdapter(ABC):
    @abstractmethod
    def validate_credentials(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def fetch(self, params: FetchParams | None = None) -> SourceData:
        raise NotImplementedError
