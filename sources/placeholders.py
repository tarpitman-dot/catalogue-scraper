from __future__ import annotations

from typing import Any

from sources.base import CatalogueSource, SourceError


class PlaceholderConnector(CatalogueSource):
    """Disabled connector used to document planned source integrations."""

    def __init__(self, source_name: str):
        self.source_name = source_name

    def lookup(self, barcode: str) -> list[dict[str, Any]]:
        raise SourceError(f"{self.source_name} is not implemented yet.")

    def search(self, text: str) -> list[dict[str, Any]]:
        raise SourceError(f"{self.source_name} is not implemented yet.")

    def get_release(self, release_id: str | int) -> dict[str, Any]:
        raise SourceError(f"{self.source_name} is not implemented yet.")
