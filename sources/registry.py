from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from sources.base import CatalogueSource
from sources.discogs import DiscogsConfig, DiscogsConnector
from sources.placeholders import PlaceholderConnector

ConnectorFactory = Callable[[dict[str, Any]], CatalogueSource]


@dataclass(frozen=True)
class SourceDefinition:
    key: str
    display_name: str
    description: str
    enabled: bool
    required_secret_names: tuple[str, ...]
    connector_factory: ConnectorFactory

    @property
    def status(self) -> str:
        return "Available" if self.enabled else "Planned"

    def create_connector(self, settings: dict[str, Any]) -> CatalogueSource:
        return self.connector_factory(settings)


def create_discogs_connector(settings: dict[str, Any]) -> DiscogsConnector:
    """Build Discogs through one stable constructor path used by UI and tests."""
    return DiscogsConnector(DiscogsConfig.from_settings(settings))


def placeholder_factory(source_name: str) -> ConnectorFactory:
    return lambda settings: PlaceholderConnector(source_name)


SOURCE_REGISTRY: dict[str, SourceDefinition] = {
    "discogs": SourceDefinition(
        key="discogs",
        display_name="Discogs",
        description="Music release metadata, labels, formats, track listings and image URLs.",
        enabled=True,
        required_secret_names=("DISCOGS_TOKEN",),
        connector_factory=create_discogs_connector,
    ),
    "amazon": SourceDefinition(
        key="amazon",
        display_name="Amazon",
        description="ASIN, retail metadata, package dimensions, weights and images.",
        enabled=False,
        required_secret_names=(
            "AMAZON_CLIENT_ID",
            "AMAZON_CLIENT_SECRET",
            "AMAZON_REFRESH_TOKEN",
            "AMAZON_SELLER_ID",
        ),
        connector_factory=placeholder_factory("Amazon"),
    ),
    "musicbrainz": SourceDefinition(
        key="musicbrainz",
        display_name="MusicBrainz",
        description="Release metadata and Cover Art Archive fallback images.",
        enabled=False,
        required_secret_names=(),
        connector_factory=placeholder_factory("MusicBrainz"),
    ),
    "spotify": SourceDefinition(
        key="spotify",
        display_name="Spotify",
        description="Digital release and track metadata.",
        enabled=False,
        required_secret_names=(),
        connector_factory=placeholder_factory("Spotify"),
    ),
    "apple_music": SourceDefinition(
        key="apple_music",
        display_name="Apple Music",
        description="Digital release metadata and artwork.",
        enabled=False,
        required_secret_names=(),
        connector_factory=placeholder_factory("Apple Music"),
    ),
    "audiosalad": SourceDefinition(
        key="audiosalad",
        display_name="AudioSalad",
        description="Internal catalogue metadata and digital identifiers.",
        enabled=False,
        required_secret_names=(),
        connector_factory=placeholder_factory("AudioSalad"),
    ),
}
