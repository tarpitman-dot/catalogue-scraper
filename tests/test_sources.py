from __future__ import annotations

from sources.base import CatalogueSource
from sources.discogs import DiscogsConnector
from sources.registry import SOURCE_REGISTRY


def test_discogs_registry_uses_single_connector_constructor_path() -> None:
    connector = SOURCE_REGISTRY["discogs"].create_connector({"token": "test-token"})

    assert isinstance(connector, DiscogsConnector)
    assert isinstance(connector, CatalogueSource)
    assert connector.config.token == "test-token"


def test_enabled_sources_implement_common_catalogue_interface() -> None:
    required_methods = {"lookup", "search", "get_release"}

    for definition in SOURCE_REGISTRY.values():
        if not definition.enabled:
            continue

        connector = definition.create_connector({"token": "test-token"})
        for method_name in required_methods:
            method = getattr(connector, method_name, None)
            assert callable(method), f"{definition.key} missing {method_name}"
