# Catalogue Scraper

Standalone Streamlit app for uploading UPC/EAN barcodes and exporting all Discogs releases returned for each barcode.

## Features

- Upload Excel or CSV
- Select the barcode column
- Fetch every Discogs release returned for each barcode
- Produce one Excel row per Discogs release
- Preserve the original uploaded columns
- Export metadata and direct main/additional image URLs
- No image downloads
- No matching or confidence logic

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
mkdir -p .streamlit
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
streamlit run app.py
```

Add your Discogs token to `.streamlit/secrets.toml`.

## Streamlit Community Cloud

Add this secret in the app settings:

```toml
DISCOGS_TOKEN = "your-token"
```
