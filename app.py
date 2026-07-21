from __future__ import annotations

import io
import re
from pathlib import Path

import pandas as pd
import streamlit as st

from sources.discogs import DiscogsConnector, DiscogsError


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


def to_excel_bytes(df: pd.DataFrame) -> bytes:
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Catalogue Results")
    return output.getvalue()


st.set_page_config(page_title=APP_NAME, page_icon="💿", layout="wide")
st.title(APP_NAME)
st.caption(
    "Upload UPCs or EANs and export every Discogs release returned for each barcode, "
    "including direct JPG/image links."
)

with st.sidebar:
    st.header("Discogs")
    token_from_secrets = st.secrets.get("DISCOGS_TOKEN", "")
    token = st.text_input(
        "Personal access token",
        value=token_from_secrets,
        type="password",
        help="Store this in Streamlit Secrets on the hosted app.",
    )
    per_page = st.number_input(
        "Results per Discogs page",
        min_value=10,
        max_value=100,
        value=100,
        step=10,
    )
    max_pages = st.number_input(
        "Maximum pages per barcode",
        min_value=1,
        max_value=20,
        value=10,
        help="At 100 results per page, the default allows up to 1,000 releases per barcode.",
    )

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
        st.stop()

    barcode_column = st.selectbox(
        "Which column contains the UPC/EAN?",
        options=list(source_df.columns),
        index=0,
    )

    preview = source_df.copy()
    preview["_Cleaned UPC/EAN"] = preview[barcode_column].map(normalise_barcode)
    st.dataframe(preview.head(50), use_container_width=True, hide_index=True)

    if st.button("Fetch all Discogs releases", type="primary", disabled=not bool(token)):
        connector = DiscogsConnector(token=token)
        output_rows: list[dict] = []

        progress = st.progress(0)
        status = st.empty()
        total = len(source_df)

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

            try:
                releases = connector.lookup_all_releases(
                    barcode=barcode,
                    per_page=int(per_page),
                    max_pages=int(max_pages),
                )

                if not releases:
                    output_rows.append({
                        **input_data,
                        "Lookup Status": "No results",
                        "Result Number": "",
                        "Results For Barcode": 0,
                    })
                else:
                    total_results = len(releases)
                    for result_number, release in enumerate(releases, start=1):
                        output_rows.append({
                            **input_data,
                            "Lookup Status": "Found",
                            "Result Number": result_number,
                            "Results For Barcode": total_results,
                            **release,
                        })

            except DiscogsError as exc:
                output_rows.append({
                    **input_data,
                    "Lookup Status": "Error",
                    "Result Number": "",
                    "Results For Barcode": 0,
                    "Error": str(exc),
                })

            progress.progress(idx / total)

        status.empty()
        st.session_state["results_df"] = pd.DataFrame(output_rows)

if "results_df" in st.session_state:
    results_df = st.session_state["results_df"]

    st.subheader("Results")
    st.dataframe(results_df, use_container_width=True, hide_index=True)

    found_rows = int((results_df["Lookup Status"] == "Found").sum())
    unique_barcodes = int(
        results_df.loc[
            results_df["Lookup Status"] == "Found", "Lookup UPC/EAN"
        ].nunique()
    )
    no_result_barcodes = int((results_df["Lookup Status"] == "No results").sum())

    c1, c2, c3 = st.columns(3)
    c1.metric("Release rows returned", found_rows)
    c2.metric("Barcodes with results", unique_barcodes)
    c3.metric("Barcodes with no results", no_result_barcodes)

    st.download_button(
        "Download Catalogue Scraper Excel",
        data=to_excel_bytes(results_df),
        file_name="catalogue_scraper_results.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
