from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

class LookupStatus:
    FOUND = "Found"
    NO_RESULTS = "No results"
    UNSUPPORTED = "Unsupported lookup type"
    INVALID = "Invalid input"
    NOT_CONFIGURED = "Source not configured"
    ERROR = "Source error"

class EntityType:
    RELEASE = "Release"
    RECORDING = "Recording"
    TRACK = "Track"
    ARTIST = "Artist"
    LABEL = "Label"

@dataclass(frozen=True)
class LookupType:
    key: str
    label: str

LOOKUP_TYPES = {
    "barcode": LookupType("barcode", "UPC / EAN"),
    "catalogue_number": LookupType("catalogue_number", "Catalogue Number"),
    "isrc": LookupType("isrc", "ISRC"),
    "label": LookupType("label", "Label Name"),
    "artist": LookupType("artist", "Artist"),
    "title": LookupType("title", "Album / Release Title"),
}


def normalise_lookup_value(lookup_type: str, value: object) -> tuple[str, str]:
    if value is None:
        raw = ""
    else:
        raw = str(value).strip()
        raw = re.sub(r"\.0$", "", raw)
    if lookup_type == "barcode":
        normalised = re.sub(r"\D", "", raw)
        return normalised, "" if normalised else "Blank or invalid UPC/EAN"
    if lookup_type == "isrc":
        normalised = re.sub(r"[\s-]+", "", raw).upper()
        valid = bool(re.fullmatch(r"[A-Z0-9]{12}", normalised))
        return normalised, "" if valid else "ISRC must be 12 alphanumeric characters"
    if lookup_type == "catalogue_number":
        return raw, "" if raw else "Blank catalogue number"
    normalised = re.sub(r"\s+", " ", raw)
    return normalised, "" if normalised else "Blank search value"


def lookup_type_label(lookup_type: str) -> str:
    return LOOKUP_TYPES[lookup_type].label
