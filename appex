import streamlit as st
import pandas as pd
import sqlite3
from pathlib import Path

st.title("My Data Dashboard")

# =========================
# FILE PATH
# =========================

DATA_FOLDER = Path(r"C:\Users\acelo\OneDrive\Desktop\python")

# =========================
# SQLITE DATABASE
# =========================

DATABASE_PATH = Path(
    r"C:\Users\acelo\OneDrive\Desktop\python\apexsample.db"
)

conn = sqlite3.connect(DATABASE_PATH)

# =========================
# FIND CSV FILES
# =========================

files = list(DATA_FOLDER.glob("*.csv"))

if not files:

    st.warning("No CSV files found in the data folder.")

else:

    selected_file = st.selectbox(
        "Select data file",
        files
    )

    # =========================
    # READ SELECTED FILE
    # =========================

    df = pd.read_csv(selected_file)

    # =========================
    # CONVERT DATES
    # =========================

    df["HATCH DATE"] = pd.to_datetime(
        df["HATCH DATE"],
        errors="coerce"
    )

    df["DEATH DATE"] = pd.to_datetime(
        df["DEATH DATE"],
        errors="coerce"
    )

    df["RECORD MONTH"] = pd.to_datetime(
        df["RECORD MONTH"],
        format="%b-%Y",
        errors="coerce"
    )

    # =========================
    # COMPUTE AGE IN MONTHS
    # =========================

    df["AGE IN MONTHS"] = (
        (df["RECORD MONTH"].dt.year - df["HATCH DATE"].dt.year) * 12
        +
        (df["RECORD MONTH"].dt.month - df["HATCH DATE"].dt.month)
    )

    # Prevent negative ages
    df["AGE IN MONTHS"] = df["AGE IN MONTHS"].clip(lower=0)

    # =========================
    # COMPUTE AGE CLASS
    # =========================

    def get_age_class(age):
        if pd.isna(age):
            return "Unknown"

        if age < 4:
            return "Chick"

        elif age < 12:
            return "Pullet"

        else:
            return "Adult"

    df["AGE CLASS"] = df["AGE IN MONTHS"].apply(
        get_age_class
    )

    # =========================
    # DISPLAY SOURCE DATA
    # =========================

    st.subheader("Source Data")

    st.dataframe(
        df,
        use_container_width=True
    )

    # =========================
    # IMPORT INTO SQLITE
    # =========================

    if st.button("Import to Database"):

        df.to_sql(
            "records",
            conn,
            if_exists="replace",
            index=False
        )

        st.success("Data imported successfully!")

# =========================
# DISPLAY DATABASE
# =========================

try:

    database_df = pd.read_sql_query(
        "SELECT * FROM records",
        conn
    )

    st.subheader("SQLite Database")

    st.dataframe(
        database_df,
        use_container_width=True
    )

except Exception:

    st.info("No data has been imported yet.")

conn.close()
