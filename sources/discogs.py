from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import requests

from sources.base import CatalogueSource, SourceError


@dataclass(frozen=True)
class DiscogsConfig:
    token: str
    per_page: int = 100
    max_pages: int = 10
    include_tracklist: bool = True
    include_notes: bool = False
    include_companies: bool = False
    include_identifiers: bool = True
    include_videos: bool = False

    @classmethod
    def from_settings(cls, settings: dict[str, Any]) -> "DiscogsConfig":
        return cls(
            token=str(settings.get("token", "") or ""),
            per_page=int(settings.get("per_page", 100) or 100),
            max_pages=int(settings.get("max_pages", 10) or 10),
            include_tracklist=bool(settings.get("include_tracklist", True)),
            include_notes=bool(settings.get("include_notes", False)),
            include_companies=bool(settings.get("include_companies", False)),
            include_identifiers=bool(settings.get("include_identifiers", True)),
            include_videos=bool(settings.get("include_videos", False)),
        )


class DiscogsConnector(CatalogueSource):
    source_name = "Discogs"
    BASE_URL = "https://api.discogs.com"

    def __init__(self, config: DiscogsConfig):
        if not config.token:
            raise SourceError("A Discogs token is required.")

        self.config = config
        self.per_page = config.per_page
        self.max_pages = config.max_pages
        self.include_tracklist = config.include_tracklist
        self.include_notes = config.include_notes
        self.include_companies = config.include_companies
        self.include_identifiers = config.include_identifiers
        self.include_videos = config.include_videos

        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Discogs token={config.token}",
            "User-Agent": "CatalogueScraper/2.0",
            "Accept": "application/vnd.discogs.v2.discogs+json",
        })

    def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        response = self.session.get(
            f"{self.BASE_URL}{path}",
            params=params,
            timeout=30,
        )

        if response.status_code == 429:
            raise SourceError("Discogs rate limit reached.")
        if response.status_code == 401:
            raise SourceError("Discogs rejected the token.")
        if not response.ok:
            raise SourceError(
                f"Discogs request failed ({response.status_code}): "
                f"{response.text[:200]}"
            )
        return response.json()

    @staticmethod
    def _join_names(items: list[dict[str, Any]] | None, key: str = "name") -> str:
        return "; ".join(
            str(item.get(key, "")).strip()
            for item in (items or [])
            if str(item.get(key, "")).strip()
        )

    @staticmethod
    def _format_text(formats: list[dict[str, Any]] | None) -> str:
        values: list[str] = []
        for fmt in formats or []:
            name = str(fmt.get("name", "")).strip()
            descriptions = [
                str(value).strip()
                for value in fmt.get("descriptions", [])
                if str(value).strip()
            ]
            quantity = str(fmt.get("qty", "")).strip()
            text = ", ".join([value for value in [name, *descriptions] if value])
            if quantity and quantity != "1":
                text = f"{quantity} × {text}"
            if text:
                values.append(text)
        return "; ".join(values)

    @staticmethod
    def _tracklist_text(tracklist: list[dict[str, Any]] | None) -> str:
        values: list[str] = []
        for track in tracklist or []:
            position = str(track.get("position", "")).strip()
            title = str(track.get("title", "")).strip()
            duration = str(track.get("duration", "")).strip()
            text = f"{position} {title}".strip()
            if duration:
                text = f"{text} ({duration})"
            if text:
                values.append(text)
        return " | ".join(values)

    @staticmethod
    def _identifiers_text(identifiers: list[dict[str, Any]] | None) -> str:
        values = []
        for identifier in identifiers or []:
            identifier_type = str(identifier.get("type", "")).strip()
            value = str(identifier.get("value", "")).strip()
            description = str(identifier.get("description", "")).strip()

            text = f"{identifier_type}: {value}".strip(": ")
            if description:
                text = f"{text} ({description})"
            if text:
                values.append(text)
        return " | ".join(values)

    @staticmethod
    def _companies_text(companies: list[dict[str, Any]] | None) -> str:
        values = []
        for company in companies or []:
            entity_type = str(company.get("entity_type_name", "")).strip()
            name = str(company.get("name", "")).strip()
            if entity_type or name:
                values.append(f"{entity_type}: {name}".strip(": "))
        return " | ".join(values)

    def _release_to_row(self, release: dict[str, Any]) -> dict[str, Any]:
        labels = release.get("labels") or []
        images = release.get("images") or []
        image_urls = [
            image.get("uri") or image.get("resource_url")
            for image in images
            if image.get("uri") or image.get("resource_url")
        ]

        row = {
            "Discogs Release ID": release.get("id"),
            "Discogs Master ID": release.get("master_id"),
            "Discogs URL": release.get("uri"),
            "Artist": release.get("artists_sort") or self._join_names(release.get("artists")),
            "Title": release.get("title"),
            "Label": self._join_names(labels),
            "Catalogue Number": "; ".join(
                str(label.get("catno", "")).strip()
                for label in labels
                if str(label.get("catno", "")).strip()
            ),
            "Format": self._format_text(release.get("formats")),
            "Country": release.get("country"),
            "Release Year": release.get("year"),
            "Release Date": release.get("released"),
            "Genres": "; ".join(release.get("genres") or []),
            "Styles": "; ".join(release.get("styles") or []),
            "Discogs Barcodes": "; ".join(
                str(identifier.get("value", "")).strip()
                for identifier in (release.get("identifiers") or [])
                if str(identifier.get("type", "")).lower() == "barcode"
                and str(identifier.get("value", "")).strip()
            ),
            "Main Image URL": image_urls[0] if image_urls else "",
            "Additional Image URLs": "; ".join(image_urls[1:]),
            "Image Count": len(image_urls),
        }

        if self.include_tracklist:
            row["Track Listing"] = self._tracklist_text(release.get("tracklist"))

        if self.include_notes:
            row["Release Notes"] = release.get("notes", "")

        if self.include_companies:
            row["Companies"] = self._companies_text(release.get("companies"))

        if self.include_identifiers:
            row["Identifiers"] = self._identifiers_text(release.get("identifiers"))

        if self.include_videos:
            row["Video URLs"] = "; ".join(
                str(video.get("uri", "")).strip()
                for video in (release.get("videos") or [])
                if str(video.get("uri", "")).strip()
            )

        return row

    def get_release(self, release_id: str | int) -> dict[str, Any]:
        return self._get(f"/releases/{release_id}")

    def search(self, text: str) -> list[dict[str, Any]]:
        search = self._get(
            "/database/search",
            params={"q": text, "type": "release", "per_page": self.per_page},
        )
        return [dict(result) for result in (search.get("results") or [])]

    def lookup(self, barcode: str) -> list[dict[str, Any]]:
        release_ids: list[int] = []

        for page in range(1, self.max_pages + 1):
            search = self._get(
                "/database/search",
                params={
                    "barcode": barcode,
                    "type": "release",
                    "per_page": self.per_page,
                    "page": page,
                },
            )

            results = search.get("results") or []
            for result in results:
                release_id = result.get("id")
                if release_id:
                    release_ids.append(release_id)

            pagination = search.get("pagination") or {}
            total_pages = int(pagination.get("pages") or 1)

            if page >= total_pages or not results:
                break

        rows: list[dict[str, Any]] = []
        for release_id in release_ids:
            release = self.get_release(release_id)
            rows.append(self._release_to_row(release))

        return rows
