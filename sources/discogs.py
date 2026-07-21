from __future__ import annotations

from typing import Any

import requests


class DiscogsError(RuntimeError):
    pass


class DiscogsConnector:
    BASE_URL = "https://api.discogs.com"

    def __init__(self, token: str, user_agent: str = "CatalogueScraper/0.3"):
        if not token:
            raise DiscogsError("A Discogs token is required.")

        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Discogs token={token}",
            "User-Agent": user_agent,
            "Accept": "application/vnd.discogs.v2.discogs+json",
        })

    def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        response = self.session.get(
            f"{self.BASE_URL}{path}",
            params=params,
            timeout=30,
        )

        if response.status_code == 429:
            raise DiscogsError("Discogs rate limit reached.")
        if response.status_code == 401:
            raise DiscogsError("Discogs rejected the token.")
        if not response.ok:
            raise DiscogsError(
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
    def _barcodes(release: dict[str, Any]) -> str:
        values: list[str] = []
        for identifier in release.get("identifiers") or []:
            if str(identifier.get("type", "")).lower() == "barcode":
                value = str(identifier.get("value", "")).strip()
                if value:
                    values.append(value)
        return "; ".join(dict.fromkeys(values))

    def _release_to_row(self, release: dict[str, Any]) -> dict[str, Any]:
        labels = release.get("labels") or []
        images = release.get("images") or []
        image_urls = [
            image.get("uri") or image.get("resource_url")
            for image in images
            if image.get("uri") or image.get("resource_url")
        ]

        return {
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
            "Track Listing": self._tracklist_text(release.get("tracklist")),
            "Discogs Barcodes": self._barcodes(release),
            "Main Image URL": image_urls[0] if image_urls else "",
            "Additional Image URLs": "; ".join(image_urls[1:]),
            "Image Count": len(image_urls),
        }

    def lookup_all_releases(
        self,
        barcode: str,
        per_page: int = 100,
        max_pages: int = 10,
    ) -> list[dict[str, Any]]:
        release_ids: list[int] = []

        for page in range(1, max_pages + 1):
            search = self._get(
                "/database/search",
                params={
                    "barcode": barcode,
                    "type": "release",
                    "per_page": per_page,
                    "page": page,
                },
            )

            results = search.get("results") or []
            for result in results:
                release_id = result.get("id")
                if release_id and release_id not in release_ids:
                    release_ids.append(release_id)

            pagination = search.get("pagination") or {}
            total_pages = int(pagination.get("pages") or 1)
            if page >= total_pages or not results:
                break

        rows: list[dict[str, Any]] = []
        for release_id in release_ids:
            release = self._get(f"/releases/{release_id}")
            rows.append(self._release_to_row(release))

        return rows
