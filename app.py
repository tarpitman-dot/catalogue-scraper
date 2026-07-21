from __future__ import annotations

import io
import os
import re
from pathlib import Path

import pandas as pd
import streamlit as st

from sources.base import SourceError
from sources.registry import SOURCE_REGISTRY
from sources.lookup import LOOKUP_TYPES, LookupStatus, lookup_type_label, normalise_lookup_value


APP_NAME = "Catalogue Scraper"


def normalise_barcode(value: object) -> str:
    return normalise_lookup_value("barcode", value)[0]


def read_input(uploaded_file) -> pd.DataFrame:
    suffix = Path(uploaded_file.name).suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(uploaded_file, dtype=str)
    if suffix in {".xlsx", ".xls"}:
        return pd.read_excel(uploaded_file, dtype=str)
    raise ValueError("Please upload an Excel or CSV file.")


def safe_source_filename(source_name: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9]+", "_", str(source_name).strip().lower()).strip("_")
    return safe or "source"


def result_sources_with_rows(df: pd.DataFrame) -> list[str]:
    if df.empty or "Source" not in df.columns:
        return []
    return [str(source) for source in df["Source"].dropna().astype(str).unique() if source.strip()]


def source_specific_results(df: pd.DataFrame, source_name: str) -> pd.DataFrame:
    if df.empty or "Source" not in df.columns:
        return df.iloc[0:0].copy()
    return df[df["Source"].astype(str) == source_name].copy()


def render_download_buttons(df: pd.DataFrame, prefix: str = "catalogue_scraper") -> None:
    if df.empty:
        return
    st.download_button("Download All Results", data=excel_bytes(df), file_name=f"{prefix}_all_results.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    for source_name in result_sources_with_rows(df):
        source_df = source_specific_results(df, source_name)
        if source_df.empty:
            continue
        st.download_button(f"Download {source_name} Results", data=excel_bytes(source_df), file_name=f"{prefix}_{safe_source_filename(source_name)}_results.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


def excel_bytes(df: pd.DataFrame) -> bytes:
    validate_found_row_sources(df)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Catalogue Results")

        if "Lookup Status" in df.columns:
            errors = df[df["Lookup Status"].isin([LookupStatus.ERROR, LookupStatus.INVALID, "Error", "Invalid barcode", LookupStatus.NOT_CONFIGURED])]
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
    "Results For Search",
    "Search Type",
    "Search Value",
    "Result Entity Type",
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
                value=False,
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
                value=False,
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



def source_supports_lookup(source_key: str, lookup_type: str) -> bool:
    return lookup_type in getattr(SOURCE_REGISTRY[source_key], "supported_lookup_types", frozenset({"barcode"}))

def show_lookup_support(source_keys: list[str], lookup_type: str) -> None:
    supported = [SOURCE_REGISTRY[k].display_name for k in source_keys if source_supports_lookup(k, lookup_type)]
    unsupported = [SOURCE_REGISTRY[k].display_name for k in source_keys if not source_supports_lookup(k, lookup_type)]
    if supported:
        st.caption("Supports selected lookup: " + ", ".join(supported))
    if unsupported:
        st.caption("Skipped for selected lookup: " + ", ".join(unsupported))

def lookup_by_type(source_key: str, lookup_type: str, value: str, settings: dict) -> list[dict]:
    cache_key = (source_key, lookup_type, value, tuple(sorted((settings or {}).items())))
    cache = st.session_state.setdefault("lookup_cache", {})
    if cache_key not in cache:
        connector = create_source_connector(source_key, settings)
        cache[cache_key] = connector.lookup_by_type(lookup_type, value)
    return cache[cache_key]


def lookup_barcode(source_key: str, barcode: str, settings: dict) -> list[dict]:
    return lookup_by_type(source_key, "barcode", barcode, settings)


def run_bulk_lookup(
    source_keys: list[str],
    source_df: pd.DataFrame,
    value_column: str,
    settings_by_source: dict[str, dict],
    lookup_type: str = "barcode",
) -> pd.DataFrame:

    output_rows: list[dict] = []
    total = len(source_df)
    progress = st.progress(0)
    status = st.empty()

    for idx, (_, original_row) in enumerate(source_df.iterrows(), start=1):
        search_value, validation_error = normalise_lookup_value(lookup_type, original_row.get(value_column, ""))
        status.write(f"Processing {idx} of {total}: {search_value or 'blank search value'}")

        input_data = original_row.to_dict()
        input_data["Search Type"] = lookup_type_label(lookup_type)
        input_data["Search Value"] = search_value
        input_data["Lookup UPC/EAN"] = search_value if lookup_type == "barcode" else ""
        if validation_error:
            output_rows.append({
                **input_data,
                "Lookup Status": LookupStatus.INVALID,
                "Result Number": "",
                "Results For Barcode": 0,
                "Results For Search": 0,
                "Error": validation_error,
            })
            progress.progress(idx / total)
            continue

        for source_key in source_keys:
            source_definition = SOURCE_REGISTRY[source_key]
            if not source_supports_lookup(source_key, lookup_type):
                output_rows.append({**input_data, "Source": source_definition.display_name, "Lookup Status": LookupStatus.UNSUPPORTED, "Result Number": "", "Results For Barcode": 0, "Results For Search": 0})
                continue
            try:
                records = (lookup_barcode(source_key, search_value, settings_by_source.get(source_key, {})) if lookup_type == "barcode" else lookup_by_type(source_key, lookup_type, search_value, settings_by_source.get(source_key, {})))
                if not records:
                    output_rows.append({**input_data, "Source": source_definition.display_name, "Lookup Status": LookupStatus.NO_RESULTS, "Result Number": "", "Results For Barcode": 0, "Results For Search": 0})
                else:
                    total_results = len(records)
                    for result_number, record in enumerate(records, start=1):
                        output_rows.append(found_result_row(
                            {**input_data, "Lookup Status": LookupStatus.FOUND, "Result Number": result_number, "Results For Barcode": total_results, "Results For Search": total_results, "Search Type": lookup_type_label(lookup_type), "Search Value": search_value},
                            record,
                            source_definition.display_name,
                        ))
            except SourceError as exc:
                output_rows.append({**input_data, "Source": source_definition.display_name, "Lookup Status": LookupStatus.ERROR, "Result Number": "", "Results For Barcode": 0, "Results For Search": 0, "Error": str(exc)})

        progress.progress(idx / total)

    status.empty()
    results = pd.DataFrame(output_rows)
    validate_found_row_sources(results)
    return results


def render_single_result_cards(df: pd.DataFrame) -> None:
    if df.empty:
        st.info("No results found.")
        return

    status_rows = df[df.get("Lookup Status", "") != LookupStatus.FOUND] if "Lookup Status" in df.columns else df.iloc[0:0]
    found_rows = df[df.get("Lookup Status", "") == LookupStatus.FOUND] if "Lookup Status" in df.columns else df

    if not status_rows.empty:
        for _, row in status_rows.iterrows():
            status = str(row.get("Lookup Status", "Status") or "Status")
            source = str(row.get("Source", "") or "").strip()
            error = str(row.get("Error", "") or "").strip()
            message = f"{source}: {status}" if source else status
            if error:
                message = f"{message} — {error}"
            if status == LookupStatus.ERROR:
                st.error(message)
            elif status in {LookupStatus.NO_RESULTS, LookupStatus.UNSUPPORTED, LookupStatus.INVALID, LookupStatus.NOT_CONFIGURED}:
                st.info(message)
            else:
                st.warning(message)

    for _, row in found_rows.iterrows():
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

        lookup_type = st.selectbox(
            "Lookup type",
            options=list(LOOKUP_TYPES),
            format_func=lookup_type_label,
            key="single_lookup_type",
        )
        show_lookup_support(selected_sources, lookup_type)

        search_input = st.text_input(
            lookup_type_label(lookup_type),
            placeholder="Paste one lookup value",
        )
        search_value, validation_error = normalise_lookup_value(lookup_type, search_input)

        if st.button(
            "Search catalogue",
            type="primary",
            disabled=bool(validation_error),
        ):
            all_rows = []
            for source_key in selected_sources:
                source_definition = SOURCE_REGISTRY[source_key]
                base = {"Search Type": lookup_type_label(lookup_type), "Search Value": search_value, "Lookup UPC/EAN": search_value if lookup_type == "barcode" else ""}
                if not source_supports_lookup(source_key, lookup_type):
                    all_rows.append({**base, "Source": source_definition.display_name, "Lookup Status": LookupStatus.UNSUPPORTED, "Result Number": "", "Results For Search": 0})
                    continue
                try:
                    records = (lookup_barcode(source_key, search_value, settings_by_source.get(source_key, {})) if lookup_type == "barcode" else lookup_by_type(source_key, lookup_type, search_value, settings_by_source.get(source_key, {})))
                    if not records:
                        all_rows.append({**base, "Source": source_definition.display_name, "Lookup Status": LookupStatus.NO_RESULTS, "Result Number": "", "Results For Search": 0})
                    for n, record in enumerate(records, start=1):
                        all_rows.append(found_result_row(
                            {**base, "Lookup Status": LookupStatus.FOUND, "Result Number": n, "Results For Search": len(records), "Results For Barcode": len(records)},
                            record,
                            source_definition.display_name,
                        ))
                except SourceError as exc:
                    all_rows.append({**base, "Source": source_definition.display_name, "Lookup Status": LookupStatus.ERROR, "Result Number": "", "Results For Search": 0, "Error": str(exc)})
            single_results = pd.DataFrame(all_rows)
            validate_found_row_sources(single_results)
            st.session_state["single_results"] = single_results

        if "single_results" in st.session_state:
            single_df = st.session_state["single_results"]

            st.write(f"**Results:** {len(single_df)}")
            render_single_result_cards(single_df)

            if not single_df.empty:
                with st.expander("View as table"):
                    st.dataframe(single_df, use_container_width=True, hide_index=True)

                render_download_buttons(single_df)

    else:
        st.subheader("Bulk Lookup")

        bulk_lookup_type = st.selectbox(
            "Lookup type",
            options=list(LOOKUP_TYPES),
            format_func=lookup_type_label,
            key="bulk_lookup_type",
        )
        show_lookup_support(selected_sources, bulk_lookup_type)

        uploaded = st.file_uploader(
            "Upload an Excel or CSV file containing lookup values",
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
                    "Which column contains the selected lookup value?",
                    options=list(source_df.columns),
                    index=0,
                )

                preview = source_df.copy()
                preview["_Normalised Search Value"] = preview[barcode_column].map(lambda value: normalise_lookup_value(bulk_lookup_type, value)[0])
                st.dataframe(preview.head(50), use_container_width=True, hide_index=True)

                if st.button("Run bulk lookup", type="primary"):
                    results_df = run_bulk_lookup(
                        selected_sources,
                        source_df,
                        barcode_column,
                        settings_by_source,
                        bulk_lookup_type,
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

            render_download_buttons(results_df)

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
