from __future__ import annotations
from typing import Any

BASE_COLUMNS = [
    "Search Type", "Search Value", "Source", "Result Entity Type", "Lookup Status",
    "Result Number", "Results For Search", "Source Record ID", "Source Record URL",
    "Artist", "Title", "Label", "Catalogue Number", "Barcode", "ISRC", "Format",
    "Country", "Release Date", "Main Image URL", "Additional Image URLs", "Error",
    "Lookup UPC/EAN", "Results For Barcode",
]

ORCHESTRATION_COLUMNS = {
    "Search Type", "Search Value", "Source", "Result Entity Type", "Lookup Status",
    "Result Number", "Results For Search", "Lookup UPC/EAN", "Results For Barcode",
}

def with_base(row: dict[str, Any], **values: Any) -> dict[str, Any]:
    base = {
        column: ""
        for column in BASE_COLUMNS
        if column not in ORCHESTRATION_COLUMNS
    }
    base.update(row)
    base.update(values)
    return base
