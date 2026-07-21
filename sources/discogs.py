from __future__ import annotations

from dataclasses import dataclass
from email.utils import parsedate_to_datetime
import logging
import time
from typing import Any

import requests

from sources.base import CatalogueSource, SourceCapabilities, SourceError
from sources.schema import with_base


@dataclass(frozen=True)
class DiscogsConfig:
    token: str
    per_page: int = 100
    max_pages: int = 10
    include_tracklist: bool = False
    include_notes: bool = False
    include_companies: bool = False
    include_identifiers: bool = False
    include_videos: bool = False
    max_retries: int = 3
    min_retry_delay: float = 1.0
    max_retry_delay: float = 60.0

    @classmethod
    def from_settings(cls, settings: dict[str, Any]) -> "DiscogsConfig":
        return cls(
            token=str(settings.get("token", "") or ""),
            per_page=int(settings.get("per_page", 100) or 100),
            max_pages=int(settings.get("max_pages", 10) or 10),
            include_tracklist=bool(settings.get("include_tracklist", False)),
            include_notes=bool(settings.get("include_notes", False)),
            include_companies=bool(settings.get("include_companies", False)),
            include_identifiers=bool(settings.get("include_identifiers", False)),
            include_videos=bool(settings.get("include_videos", False)),
            max_retries=int(settings.get("max_retries", 3) or 3),
            min_retry_delay=float(settings.get("min_retry_delay", 1.0) or 1.0),
            max_retry_delay=float(settings.get("max_retry_delay", 60.0) or 60.0),
        )


class DiscogsConnector(CatalogueSource):
    source_name = "Discogs"
    supported_lookup_types = {"barcode", "catalogue_number", "label", "artist", "title"}
    capabilities = SourceCapabilities(frozenset(supported_lookup_types), max_page_size=100, supports_pagination=True, credentials_required=True, rate_limit="HTTP 429 retries respect Retry-After and Discogs rate-limit reset headers.")
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
        self.max_retries = max(0, config.max_retries)
        self.min_retry_delay = max(0.0, config.min_retry_delay)
        self.max_retry_delay = max(self.min_retry_delay, config.max_retry_delay)
        self._release_cache: dict[str, dict[str, Any]] = {}
        self._request_count = 0
        self._logger = logging.getLogger(__name__)

        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Discogs token={config.token}",
            "User-Agent": "CatalogueScraper/2.0",
            "Accept": "application/vnd.discogs.v2.discogs+json",
        })

    def _retry_delay(self, response: requests.Response, attempt: int) -> float:
        retry_after = response.headers.get("Retry-After")
        if retry_after:
            try:
                return min(float(retry_after), self.max_retry_delay)
            except ValueError:
                try:
                    seconds = (parsedate_to_datetime(retry_after).timestamp() - time.time())
                    return min(max(0.0, seconds), self.max_retry_delay)
                except (TypeError, ValueError, OverflowError):
                    pass

        remaining = response.headers.get("X-Discogs-Ratelimit-Remaining")
        reset = response.headers.get("X-Discogs-Ratelimit-Reset")
        if remaining == "0" and reset:
            try:
                reset_delay = float(reset)
                # Discogs exposes seconds until reset in this header. If a proxy ever
                # passes an epoch timestamp, convert that to seconds from now.
                if reset_delay > 1_000_000_000:
                    reset_delay -= time.time()
                return min(max(0.0, reset_delay), self.max_retry_delay)
            except ValueError:
                pass

        return min(self.min_retry_delay * (2 ** attempt), self.max_retry_delay)

    def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        for attempt in range(self.max_retries + 1):
            started = time.monotonic()
            response = self.session.get(
                f"{self.BASE_URL}{path}",
                params=params,
                timeout=30,
            )
            self._request_count += 1
            self._logger.debug(
                "Discogs request endpoint=%s count=%s status=%s retry=%s elapsed=%.3fs",
                path, self._request_count, response.status_code, attempt, time.monotonic() - started,
            )

            if response.status_code == 429:
                if attempt >= self.max_retries:
                    raise SourceError("Discogs rate limit reached after retries; please try again later.")
                delay = self._retry_delay(response, attempt)
                time.sleep(delay)
                continue
            if response.status_code == 401:
                raise SourceError("Discogs rejected the token.")
            if not response.ok:
                raise SourceError(
                    f"Discogs request failed ({response.status_code}): "
                    f"{response.text[:200]}"
                )
            return response.json()

        raise SourceError("Discogs request failed unexpectedly after retries.")

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

    def _release_to_row(self, release: dict[str, Any], lookup_barcode: str = "") -> dict[str, Any]:
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

        return with_base(
            row,
            Source=self.source_name,
            **{
                "Result Entity Type": "Release",
                "Lookup UPC/EAN": lookup_barcode,
                "Source Record ID": release.get("id", ""),
                "Source Record URL": release.get("uri", ""),
                "Barcode": lookup_barcode,
            },
        )


    def _detail_required(self, lookup_type: str) -> bool:
        if lookup_type in {"barcode", "catalogue_number"}:
            return True
        return any([
            self.include_tracklist,
            self.include_notes,
            self.include_companies,
            self.include_identifiers,
            self.include_videos,
        ])

    def _search_result_to_row(self, result: dict[str, Any], lookup_value: str = "") -> dict[str, Any]:
        labels = result.get("label") or []
        catnos = result.get("catno") or []
        formats = result.get("format") or []
        title = str(result.get("title", "") or "")
        artist = ""
        release_title = title
        if " - " in title:
            artist, release_title = title.split(" - ", 1)
        image = result.get("cover_image") or result.get("thumb") or ""
        return with_base({
            "Discogs Release ID": result.get("id"),
            "Discogs Master ID": result.get("master_id"),
            "Discogs URL": result.get("uri") or result.get("resource_url", ""),
            "Artist": artist,
            "Title": release_title,
            "Label": "; ".join(str(v).strip() for v in labels if str(v).strip()),
            "Catalogue Number": "; ".join(str(v).strip() for v in catnos if str(v).strip()),
            "Format": "; ".join(str(v).strip() for v in formats if str(v).strip()),
            "Country": result.get("country", ""),
            "Release Year": result.get("year", ""),
            "Genres": "; ".join(result.get("genre") or []),
            "Styles": "; ".join(result.get("style") or []),
            "Main Image URL": image,
        }, Source=self.source_name, **{"Result Entity Type": "Release", "Lookup UPC/EAN": lookup_value, "Source Record ID": result.get("id", ""), "Source Record URL": result.get("uri") or result.get("resource_url", ""), "Barcode": lookup_value})

    def get_release(self, release_id: str | int) -> dict[str, Any]:
        cache_key = str(release_id).strip()
        if cache_key not in self._release_cache:
            self._release_cache[cache_key] = self._get(f"/releases/{cache_key}")
        return self._release_cache[cache_key]

    def search(self, text: str) -> list[dict[str, Any]]:
        search = self._get(
            "/database/search",
            params={"q": text, "type": "release", "per_page": self.per_page},
        )
        return [dict(result) for result in (search.get("results") or [])]

    def _database_search_rows(self, params: dict[str, Any], lookup_value: str = "", lookup_type: str = "") -> list[dict[str, Any]]:
        release_ids: list[int] = []
        unique_results: list[dict[str, Any]] = []

        for page in range(1, self.max_pages + 1):
            search = self._get(
                "/database/search",
                params={
                    **params,
                    "type": "release",
                    "per_page": self.per_page,
                    "page": page,
                },
            )

            results = search.get("results") or []
            for result in results:
                release_id = result.get("id")
                if release_id and release_id not in release_ids:
                    release_ids.append(release_id)
                    unique_results.append(dict(result))

            pagination = search.get("pagination") or {}
            total_pages = int(pagination.get("pages") or 1)

            if page >= total_pages or not results:
                break

        if not self._detail_required(lookup_type):
            return [self._search_result_to_row(result, lookup_value) for result in unique_results]

        rows: list[dict[str, Any]] = []
        for release_id in release_ids:
            release = self.get_release(release_id)
            rows.append(self._release_to_row(release, lookup_value))

        return rows

    def _search_params_for_type(self, lookup_type: str, value: str) -> dict[str, Any]:
        return {
            "barcode": {"barcode": value},
            "catalogue_number": {"catno": value},
            "label": {"label": value},
            "artist": {"artist": value},
            "title": {"release_title": value},
        }[lookup_type]

    def search_by_type(self, lookup_type: str, value: str) -> list[dict[str, Any]]:
        return self._database_search_rows(self._search_params_for_type(lookup_type, value), value, lookup_type)

    def lookup(self, barcode: str) -> list[dict[str, Any]]:
        return self._database_search_rows({"barcode": barcode}, barcode, "barcode")
