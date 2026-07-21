from __future__ import annotations
from typing import Any

BASE_COLUMNS = [
    "Source", "Lookup UPC/EAN", "Source Record ID", "Source Record URL", "Artist", "Title",
    "Label", "Catalogue Number", "Format", "Country", "Release Date", "Barcode",
    "Main Image URL", "Additional Image URLs", "Result Number", "Results For Barcode",
    "Lookup Status", "Error",
]

ORCHESTRATION_COLUMNS = {
    "Source",
    "Lookup UPC/EAN",
    "Result Number",
    "Results For Barcode",
    "Lookup Status",
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
