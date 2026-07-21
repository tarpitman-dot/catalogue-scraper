from __future__ import annotations

from sources.placeholders import PlaceholderConnector


class AmazonConnector(PlaceholderConnector):
    def __init__(self) -> None:
        super().__init__("Amazon")
