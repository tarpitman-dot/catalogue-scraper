from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class SourceError(RuntimeError):
    pass


class CatalogueSource(ABC):
    source_name: str

    @abstractmethod
    def lookup_all(self, barcode: str) -> list[dict[str, Any]]:
        raise NotImplementedError
