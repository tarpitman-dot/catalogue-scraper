from __future__ import annotations

from sources.base import CatalogueSource


class AmazonConnector(CatalogueSource):
    source_name = "Amazon"

    def lookup_all(self, barcode: str):
        raise NotImplementedError
