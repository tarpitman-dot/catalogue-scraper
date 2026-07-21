from __future__ import annotations

import io
import os
import re
from pathlib import Path

import pandas as pd
import streamlit as st

from sources.base import SourceError
from sources.registry import SOURCE_REGISTRY


APP_NAME = "Catalogue Scraper"


def normalise_barcode(value: object) -> str:
    if pd.isna(value):
        return ""
    text = str(value).strip()
    text = re.sub(r"\.0$", "", text)
    return re.sub(r"\D", "", text)


def read_input(uploaded_file) -> pd.DataFrame:
    suffix = Path(uploaded_file.name).suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(uploaded_file, dtype=str)
    if suffix in {".xlsx", ".xls"}:
        return pd.read_excel(uploaded_file, dtype=str)
    raise ValueError("Please upload an Excel or CSV file.")


def excel_bytes(df: pd.DataFrame) -> bytes:
    validate_found_row_sources(df)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Catalogue Results")

        if "Lookup Status" in df.columns:
            errors = df[df["Lookup Status"].isin(["Error", "Invalid barcode"])]
            no_results = df[df["Lookup Status"] == "No results"]

            if not errors.empty:
                errors.to_excel(writer, index=False, sheet_name="Errors")
            if not no_results.empty:
                no_results.to_excel(writer, index=False, sheet_name="No Results")

    return output.getvalue()



def is_blank_value(value: object) -> bool:
    if value is None:
        return True
    try:
        if pd.isna(value):
            return True
    except (TypeError, ValueError):
        pass
    return not str(value).strip()


def source_name_for_record(record: dict, fallback_source_name: str) -> str:
    source = record.get("Source")
    if is_blank_value(source):
        return fallback_source_name
    return str(source).strip()


PROTECTED_LOOKUP_METADATA = {
    "Lookup Status",
    "Result Number",
    "Results For Barcode",
    "Lookup UPC/EAN",
}


def found_result_row(
    base_values: dict,
    record: dict,
    fallback_source_name: str,
) -> dict:
    row = dict(record)
    for key, value in base_values.items():
        if key in PROTECTED_LOOKUP_METADATA or key not in row:
            row[key] = value
    row["Source"] = source_name_for_record(record, fallback_source_name)
    return row


def validate_found_row_sources(df: pd.DataFrame) -> None:
    if df.empty or "Lookup Status" not in df.columns:
        return
    found = df[df["Lookup Status"] == "Found"]
    if found.empty:
        return
    if "Source" not in found.columns:
        raise ValueError("Export validation failed: found rows are missing the Source column.")
    invalid = found[found["Source"].map(is_blank_value)]
    if not invalid.empty:
        raise ValueError("Export validation failed: found rows must have a non-blank Source.")

def get_secret(name: str, default: str = "") -> str:
    try:
        value = st.secrets.get(name, "")
    except Exception:
        value = ""
    return str(value or os.getenv(name, default) or "")


def source_settings_ui(source_key: str) -> dict:
    if source_key == "discogs":
        token = get_secret("DISCOGS_TOKEN")

        if token:
            st.success("Discogs connected")
        else:
            st.warning("Discogs token not configured")
            token = st.text_input(
                "Discogs personal access token",
                type="password",
                help="Use Streamlit Secrets for normal use.",
                key="discogs_token_input",
            )

        with st.expander("Discogs options", expanded=False):
            per_page = st.number_input(
                "Results per page",
                min_value=10,
                max_value=100,
                value=100,
                step=10,
                key="discogs_per_page",
            )
            max_pages = st.number_input(
                "Maximum pages per barcode",
                min_value=1,
                max_value=50,
                value=10,
                key="discogs_max_pages",
            )
            include_tracklist = st.checkbox(
                "Include track listing",
                value=True,
                key="discogs_tracklist",
            )
            include_notes = st.checkbox(
                "Include release notes",
                value=False,
                key="discogs_notes",
            )
            include_companies = st.checkbox(
                "Include companies",
                value=False,
                key="discogs_companies",
            )
            include_identifiers = st.checkbox(
                "Include identifiers",
                value=True,
                key="discogs_identifiers",
            )
            include_videos = st.checkbox(
                "Include video URLs",
                value=False,
                key="discogs_videos",
            )

        return {
            "token": token,
            "per_page": int(per_page),
            "max_pages": int(max_pages),
            "include_tracklist": include_tracklist,
            "include_notes": include_notes,
            "include_companies": include_companies,
            "include_identifiers": include_identifiers,
            "include_videos": include_videos,
        }

    return {}



def source_runtime_status(source_key: str) -> str:
    if source_key == "amazon":
        return "Planned"
    if source_key == "discogs":
        return "Connected" if get_secret("DISCOGS_TOKEN") else "Not configured"
    if source_key == "musicbrainz":
        return "Available without credentials"
    if source_key == "spotify":
        return "Connected" if get_secret("SPOTIFY_CLIENT_ID") and get_secret("SPOTIFY_CLIENT_SECRET") else "Not configured"
    if source_key == "apple":
        return "Connected" if get_secret("APPLE_MUSIC_DEVELOPER_TOKEN") else "Available without credentials"
    return SOURCE_REGISTRY[source_key].status

def create_source_connector(source_key: str, settings: dict):
    definition = SOURCE_REGISTRY[source_key]
    return definition.create_connector(settings)


def lookup_barcode(source_key: str, barcode: str, settings: dict) -> list[dict]:
    cache_key = (source_key, barcode, tuple(sorted((settings or {}).items())))
    cache = st.session_state.setdefault("lookup_cache", {})
    if cache_key not in cache:
        connector = create_source_connector(source_key, settings)
        cache[cache_key] = connector.lookup(barcode=barcode)
    return cache[cache_key]


def run_bulk_lookup(
    source_keys: list[str],
    source_df: pd.DataFrame,
    barcode_column: str,
    settings_by_source: dict[str, dict],
) -> pd.DataFrame:

    output_rows: list[dict] = []
    total = len(source_df)
    progress = st.progress(0)
    status = st.empty()

    for idx, (_, original_row) in enumerate(source_df.iterrows(), start=1):
        barcode = normalise_barcode(original_row.get(barcode_column, ""))
        status.write(f"Processing {idx} of {total}: {barcode or 'blank barcode'}")

        input_data = original_row.to_dict()
        input_data["Lookup UPC/EAN"] = barcode
        if not barcode:
            output_rows.append({
                **input_data,
                "Lookup Status": "Invalid barcode",
                "Result Number": "",
                "Results For Barcode": 0,
                "Error": "Blank or invalid UPC/EAN",
            })
            progress.progress(idx / total)
            continue

        for source_key in source_keys:
            source_definition = SOURCE_REGISTRY[source_key]
            try:
                records = lookup_barcode(source_key, barcode, settings_by_source.get(source_key, {}))
                if not records:
                    output_rows.append({**input_data, "Source": source_definition.display_name, "Lookup Status": "No results", "Result Number": "", "Results For Barcode": 0})
                else:
                    total_results = len(records)
                    for result_number, record in enumerate(records, start=1):
                        output_rows.append(found_result_row(
                            {**input_data, "Lookup Status": "Found", "Result Number": result_number, "Results For Barcode": total_results},
                            record,
                            source_definition.display_name,
                        ))
            except SourceError as exc:
                output_rows.append({**input_data, "Source": source_definition.display_name, "Lookup Status": "Error", "Result Number": "", "Results For Barcode": 0, "Error": str(exc)})

        progress.progress(idx / total)

    status.empty()
    results = pd.DataFrame(output_rows)
    validate_found_row_sources(results)
    return results


def render_single_result_cards(df: pd.DataFrame) -> None:
    if df.empty:
        st.info("No results found.")
        return

    for _, row in df.iterrows():
        with st.container(border=True):
            title = str(row.get("Title", "") or "Untitled")
            artist = str(row.get("Artist", "") or "")
            heading = f"{artist} — {title}" if artist else title
            st.subheader(heading)

            c1, c2 = st.columns([1, 2])

            with c1:
                image_url = str(row.get("Main Image URL", "") or "")
                if image_url:
                    st.image(image_url, use_container_width=True)
                else:
                    st.caption("No image available")

            with c2:
                summary_fields = [
                    ("Label", row.get("Label")),
                    ("Catalogue Number", row.get("Catalogue Number")),
                    ("Format", row.get("Format")),
                    ("Country", row.get("Country")),
                    ("Release Date", row.get("Release Date")),
                    ("Discogs Release ID", row.get("Discogs Release ID")),
                ]

                for label, value in summary_fields:
                    if value not in (None, "", float("nan")):
                        st.write(f"**{label}:** {value}")

                discogs_url = str(row.get("Discogs URL", "") or "")
                if discogs_url:
                    st.link_button("Open Discogs release", discogs_url)

                if image_url:
                    st.markdown(f"[Open main image directly]({image_url})")


st.set_page_config(page_title=APP_NAME, page_icon="💿", layout="wide")
st.title(APP_NAME)
st.caption("Multi-source catalogue research and bulk metadata export.")

search_tab, sources_tab, settings_tab = st.tabs(["Search", "Sources", "Settings"])

with search_tab:
    mode = st.radio(
        "Search mode",
        options=["Single Lookup", "Bulk Lookup"],
        horizontal=True,
    )

    available_sources = [
        key for key, definition in SOURCE_REGISTRY.items() if definition.enabled
    ]

    selected_sources = st.multiselect(
        "Sources",
        options=available_sources,
        default=[available_sources[0]] if available_sources else [],
        format_func=lambda key: SOURCE_REGISTRY[key].display_name,
    )

    settings_by_source = {key: source_settings_ui(key) for key in selected_sources}

    if mode == "Single Lookup":
        st.subheader("Single Lookup")

        barcode_input = st.text_input(
            "UPC / EAN",
            placeholder="Paste one barcode",
        )

        if st.button(
            "Search catalogue",
            type="primary",
            disabled=not bool(normalise_barcode(barcode_input)),
        ):
            barcode = normalise_barcode(barcode_input)

            try:
                all_rows = []
                for source_key in selected_sources:
                    try:
                        records = lookup_barcode(source_key, barcode, settings_by_source.get(source_key, {}))
                        for n, record in enumerate(records, start=1):
                            all_rows.append(found_result_row(
                                {"Lookup UPC/EAN": barcode, "Lookup Status": "Found", "Result Number": n, "Results For Barcode": len(records)},
                                record,
                                SOURCE_REGISTRY[source_key].display_name,
                            ))
                    except SourceError as exc:
                        all_rows.append({"Lookup UPC/EAN": barcode, "Source": SOURCE_REGISTRY[source_key].display_name, "Lookup Status": "Error", "Error": str(exc)})
                single_results = pd.DataFrame(all_rows)
                validate_found_row_sources(single_results)
                st.session_state["single_results"] = single_results
            except SourceError as exc:
                st.error(str(exc))

        if "single_results" in st.session_state:
            single_df = st.session_state["single_results"]

            st.write(f"**Results:** {len(single_df)}")
            render_single_result_cards(single_df)

            if not single_df.empty:
                with st.expander("View as table"):
                    st.dataframe(single_df, use_container_width=True, hide_index=True)

                st.download_button(
                    "Download single lookup Excel",
                    data=excel_bytes(single_df),
                    file_name="catalogue_scraper_single_lookup.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )

    else:
        st.subheader("Bulk Lookup")

        uploaded = st.file_uploader(
            "Upload an Excel or CSV file containing UPCs/EANs",
            type=["xlsx", "xls", "csv"],
        )

        if uploaded is not None:
            try:
                source_df = read_input(uploaded)
            except Exception as exc:
                st.error(str(exc))
                st.stop()

            if source_df.empty:
                st.warning("The uploaded file contains no rows.")
            else:
                barcode_column = st.selectbox(
                    "Which column contains the UPC/EAN?",
                    options=list(source_df.columns),
                    index=0,
                )

                preview = source_df.copy()
                preview["_Cleaned UPC/EAN"] = preview[barcode_column].map(normalise_barcode)
                st.dataframe(preview.head(50), use_container_width=True, hide_index=True)

                if st.button("Run bulk lookup", type="primary"):
                    results_df = run_bulk_lookup(
                        selected_sources,
                        source_df,
                        barcode_column,
                        settings_by_source,
                    )
                    st.session_state["bulk_results"] = results_df

        if "bulk_results" in st.session_state:
            results_df = st.session_state["bulk_results"]

            st.subheader("Bulk results")
            st.dataframe(results_df, use_container_width=True, hide_index=True)

            found_rows = int((results_df["Lookup Status"] == "Found").sum())
            unique_barcodes = int(
                results_df.loc[
                    results_df["Lookup Status"] == "Found", "Lookup UPC/EAN"
                ].nunique()
            )
            no_results = int((results_df["Lookup Status"] == "No results").sum())

            c1, c2, c3 = st.columns(3)
            c1.metric("Rows returned", found_rows)
            c2.metric("Barcodes with results", unique_barcodes)
            c3.metric("Barcodes with no results", no_results)

            st.download_button(
                "Download bulk Excel",
                data=excel_bytes(results_df),
                file_name="catalogue_scraper_bulk_results.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )

with sources_tab:
    st.subheader("Sources")
    source_rows = []
    for definition in SOURCE_REGISTRY.values():
        source_rows.append({
            "Source": definition.display_name,
            "Status": source_runtime_status(definition.key),
            "Enabled": definition.enabled,
            "Configuration": ", ".join(definition.required_secret_names) or "No credentials required",
            "Purpose": definition.description,
        })
    st.dataframe(pd.DataFrame(source_rows), use_container_width=True, hide_index=True)

with settings_tab:
    st.subheader("Settings")
    st.write("Catalogue Scraper reads credentials from Streamlit Secrets or environment variables. Spotify requires SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET. Apple Music uses APPLE_MUSIC_DEVELOPER_TOKEN; without it, the public iTunes Lookup fallback is used. Amazon is planned while access is being arranged.")
    settings_rows = []
    for definition in SOURCE_REGISTRY.values():
        for secret_name in definition.required_secret_names:
            settings_rows.append({
                "Source": definition.display_name,
                "Secret": secret_name,
                "Configured": bool(get_secret(secret_name)),
            })
    st.dataframe(pd.DataFrame(settings_rows), use_container_width=True, hide_index=True)
