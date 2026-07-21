from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from sources.base import CatalogueSource, SourceError
from sources.http import HttpClient
from sources.schema import with_base


def _join(values: list[Any]) -> str:
    return "; ".join(str(v).strip() for v in values if str(v).strip())


@dataclass(frozen=True)
class MusicBrainzConfig:
    app_name: str = "CatalogueScraper"
    app_version: str = "2.0"
    contact: str = ""

    @classmethod
    def from_settings(cls, settings: dict[str, Any]) -> "MusicBrainzConfig":
        return cls(
            app_name=str(settings.get("app_name") or os.getenv("MUSICBRAINZ_APP_NAME") or "CatalogueScraper"),
            app_version=str(settings.get("app_version") or os.getenv("MUSICBRAINZ_APP_VERSION") or "2.0"),
            contact=str(settings.get("contact") or os.getenv("MUSICBRAINZ_CONTACT") or ""),
        )


class CoverArtArchiveClient:
    BASE_URL = "https://coverartarchive.org/release"

    def __init__(self, user_agent: str, client: HttpClient | None = None):
        self.client = client or HttpClient("Cover Art Archive", user_agent, min_interval=0.1)

    def lookup(self, release_id: str) -> dict[str, Any]:
        endpoint = f"{self.BASE_URL}/{release_id}"
        try:
            data = self.client.get_json(endpoint)
        except SourceError as exc:
            if "(404)" in str(exc):
                return {"Cover Art Archive release endpoint": endpoint, "Image count": 0}
            raise
        images = data.get("images") or []
        originals = [img.get("image") for img in images if img.get("image")]
        front = next((img for img in images if img.get("front")), None)
        back = next((img for img in images if img.get("back")), None)
        first = images[0] if images else {}
        thumbs = first.get("thumbnails") or {}
        types = sorted({t for img in images for t in (img.get("types") or [])})
        return {
            "Main Image URL": originals[0] if originals else "",
            "Front Image URL": front.get("image", "") if front else "",
            "Back Image URL": back.get("image", "") if back else "",
            "Additional Image URLs": _join(originals[1:]),
            "Thumbnail URL 250": thumbs.get("250", ""),
            "Thumbnail URL 500": thumbs.get("500", ""),
            "Thumbnail URL 1200": thumbs.get("1200", ""),
            "Image count": len(images),
            "Image types": _join(types),
            "Whether the image is front": any(bool(img.get("front")) for img in images),
            "Whether the image is back": any(bool(img.get("back")) for img in images),
            "Cover Art Archive release endpoint": endpoint,
        }


class MusicBrainzConnector(CatalogueSource):
    source_name = "MusicBrainz"
    BASE_URL = "https://musicbrainz.org/ws/2"

    def __init__(self, config: MusicBrainzConfig | None = None, client: HttpClient | None = None, cover_art: CoverArtArchiveClient | None = None):
        self.config = config or MusicBrainzConfig.from_settings({})
        contact = f" ({self.config.contact})" if self.config.contact else ""
        self.user_agent = f"{self.config.app_name}/{self.config.app_version}{contact}"
        self.client = client or HttpClient("MusicBrainz", self.user_agent, min_interval=1.0)
        self.cover_art = cover_art or CoverArtArchiveClient(self.user_agent)

    def _params(self, barcode: str) -> dict[str, str]:
        return {"query": f'barcode:"{barcode}"', "fmt": "json", "limit": "100"}

    def lookup(self, barcode: str) -> list[dict[str, Any]]:
        data = self.client.get_json(f"{self.BASE_URL}/release", params=self._params(barcode))
        rows = []
        for release in data.get("releases") or []:
            rows.append(self._release_to_row(release, barcode))
        return rows

    def search(self, text: str) -> list[dict[str, Any]]:
        return self.client.get_json(f"{self.BASE_URL}/release", params={"query": text, "fmt": "json", "limit": "100"}).get("releases", [])

    def get_release(self, release_id: str | int) -> dict[str, Any]:
        return self.client.get_json(f"{self.BASE_URL}/release/{release_id}", params={"fmt": "json"})

    def _release_to_row(self, release: dict[str, Any], lookup_barcode: str) -> dict[str, Any]:
        rg = release.get("release-group") or {}
        labels = release.get("label-info") or []
        media = release.get("media") or []
        release_id = release.get("id", "")
        caa = self.cover_art.lookup(release_id) if release_id else {}
        has_cover_art = int(caa.get("Image count") or 0) > 0
        source_name = "MusicBrainz + Cover Art Archive" if has_cover_art else self.source_name
        track_listing = []
        for medium in media:
            for track in medium.get("tracks") or []:
                track_listing.append(f"{track.get('number','')} {track.get('title','')}".strip())
        row = with_base({
            "MusicBrainz Release ID": release_id,
            "MusicBrainz Release Group ID": rg.get("id", ""),
            "MusicBrainz release URL": f"https://musicbrainz.org/release/{release_id}" if release_id else "",
            "Release disambiguation": release.get("disambiguation", ""),
            "Release status": release.get("status", ""),
            "Release group primary type": rg.get("primary-type", ""),
            "Release group secondary types": _join(rg.get("secondary-types") or []),
            "Packaging": release.get("packaging", ""),
            "Text representation language": (release.get("text-representation") or {}).get("language", ""),
            "Text representation script": (release.get("text-representation") or {}).get("script", ""),
            "Media formats": _join([m.get("format") for m in media]),
            "Number of media": len(media),
            "Number of tracks": sum(int(m.get("track-count") or len(m.get("tracks") or [])) for m in media),
            "Track listing": " | ".join(track_listing),
            "Disc IDs where available": _join([d.get("id") for m in media for d in (m.get("discs") or [])]),
            "ASIN where available": release.get("asin", ""),
            "Data quality": release.get("quality", ""),
            "Tags or genres where available": _join([t.get("name") for t in (release.get("tags") or []) + (release.get("genres") or [])]),
            **caa,
        }, Source=source_name, **{"Lookup UPC/EAN": lookup_barcode, "Source Record ID": release_id, "Source Record URL": f"https://musicbrainz.org/release/{release_id}" if release_id else "", "Artist": release.get("artist-credit-phrase") or _join([a.get("name") for a in release.get("artist-credit") or [] if isinstance(a, dict)]), "Title": release.get("title", ""), "Label": _join([(li.get("label") or {}).get("name") for li in labels]), "Catalogue Number": _join([li.get("catalog-number") for li in labels]), "Format": _join([m.get("format") for m in media]), "Country": release.get("country", ""), "Release Date": release.get("date", ""), "Barcode": release.get("barcode", "")})
        return row
