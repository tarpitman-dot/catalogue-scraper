from __future__ import annotations
from typing import Any

BASE_COLUMNS = [
    "Source", "Lookup UPC/EAN", "Source Record ID", "Source Record URL", "Artist", "Title",
    "Label", "Catalogue Number", "Format", "Country", "Release Date", "Barcode",
    "Main Image URL", "Additional Image URLs", "Result Number", "Results For Barcode",
    "Lookup Status", "Error",
]

def with_base(row: dict[str, Any], **values: Any) -> dict[str, Any]:
    base = {column: "" for column in BASE_COLUMNS}
    base.update(values)
    base.update(row)
    return base
