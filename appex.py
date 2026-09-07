import streamlit as st
import pandas as pd
import sqlite3
from pathlib import Path


# =========================================================
# PAGE CONFIGURATION
# =========================================================

st.set_page_config(
    page_title="Apex Data System",
    layout="wide"
)


# =========================================================
# FILE PATHS
# =========================================================

# GitHub / Streamlit repository structure:
#
# apexgaming/
# ├── app.py
# └── data/
#     ├── apexsample.csv
#     └── apexsample.db

DATA_FOLDER = Path("data")

DATABASE_PATH = DATA_FOLDER / "apexsample.db"


# Make sure the folder exists.
# This also prevents errors if the repository has
# no data folder yet.
DATA_FOLDER.mkdir(
    parents=True,
    exist_ok=True
)


# =========================================================
# DATABASE CONNECTION
# =========================================================

conn = sqlite3.connect(
    DATABASE_PATH,
    check_same_thread=False
)


# =========================================================
# SETTINGS
# =========================================================

RECORD_YEAR = 2026

MONTHS = [
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec"
]


# =========================================================
# HELPER FUNCTIONS
# =========================================================

def get_dataset_name(file_path):
    """
    The CSV filename becomes the SQLite table name.

    Example:
        apexsample.csv
        -> apexsample
    """

    if hasattr(file_path, "name"):
        return Path(file_path.name).stem

    return Path(file_path).stem


def table_exists(table_name):
    """
    Check whether a SQLite table exists.
    """

    result = conn.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table'
        AND name = ?
        """,
        (table_name,)
    ).fetchone()

    return result is not None


def get_table_columns(table_name):
    """
    Return the columns from an existing SQLite table.
    """

    cursor = conn.execute(
        f'PRAGMA table_info("{table_name}")'
    )

    return [
        row[1]
        for row in cursor.fetchall()
    ]


def get_sqlite_tables():
    """
    Return production SQLite tables only.

    Pending tables are excluded.
    """

    tables = pd.read_sql_query(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table'
        AND name NOT LIKE '%_pending'
        ORDER BY name
        """,
        conn
    )

    return tables["name"].tolist()


def delete_sqlite_tables(table_names):
    """
    Permanently delete multiple production SQLite tables.

    Pending tables are not directly selected because
    get_sqlite_tables() excludes them.
    """

    for table_name in table_names:

        conn.execute(
            f'DROP TABLE IF EXISTS "{table_name}"'
        )

        # Also remove its pending table if it exists.
        pending_table = f"{table_name}_pending"

        conn.execute(
            f'DROP TABLE IF EXISTS "{pending_table}"'
        )

    conn.commit()


def normalize_database_dates(df):
    """
    Normalize date columns read from SQLite so they can
    be compared with prepared source data.
    """

    df = df.copy()

    for column in [
        "HATCH DATE",
        "DEATH DATE"
    ]:

        if column in df.columns:

            df[column] = pd.to_datetime(
                df[column],
                errors="coerce"
            )

    return df


# =========================================================
# DATA PREPARATION
# =========================================================

def prepare_data(df):
    """
    Clean data and calculate derived fields.
    """

    df = df.copy()


    # -----------------------------------------------------
    # HATCH DATE
    # -----------------------------------------------------

    if "HATCH DATE" in df.columns:

        df["HATCH DATE"] = pd.to_datetime(
            df["HATCH DATE"],
            errors="coerce"
        )


    # -----------------------------------------------------
    # DEATH DATE
    # -----------------------------------------------------

    if "DEATH DATE" in df.columns:

        df["DEATH DATE"] = pd.to_datetime(
            df["DEATH DATE"],
            errors="coerce"
        )


    # -----------------------------------------------------
    # RECORD MONTH
    # -----------------------------------------------------

    if "RECORD MONTH" in df.columns:

        df["RECORD MONTH"] = (
            df["RECORD MONTH"]
            .astype(str)
            .str.strip()
        )


    # -----------------------------------------------------
    # AGE IN MONTHS
    # -----------------------------------------------------

    if (
        "RECORD MONTH" in df.columns
        and "HATCH DATE" in df.columns
    ):

        month_number = pd.to_datetime(
            df["RECORD MONTH"],
            format="%b",
            errors="coerce"
        ).dt.month

        df["AGE IN MONTHS"] = (

            (
                RECORD_YEAR
                - df["HATCH DATE"].dt.year
            ) * 12

            +

            (
                month_number
                - df["HATCH DATE"].dt.month
            )
        )

        df["AGE IN MONTHS"] = (
            df["AGE IN MONTHS"]
            .clip(lower=0)
        )


    # -----------------------------------------------------
    # AGE CLASS
    # -----------------------------------------------------

    if "AGE IN MONTHS" in df.columns:

        def get_age_class(age):

            if pd.isna(age):
                return "Unknown"

            if age < 4:
                return "Chick"

            elif age < 12:
                return "Pullet"

            else:
                return "Adult"

        df["AGE CLASS"] = (
            df["AGE IN MONTHS"]
            .apply(get_age_class)
        )


    return df


# =========================================================
# SCHEMA VALIDATION
# =========================================================

def schema_matches(df, table_name):
    """
    Check whether incoming data has exactly
    the same columns as the production table.
    """

    source_columns = list(df.columns)

    database_columns = get_table_columns(
        table_name
    )

    return source_columns == database_columns


# =========================================================
# FIND NEW RECORDS
# =========================================================

def find_new_records(df, existing_df):

    # -----------------------------------------------------
    # NORMALIZE DATE TYPES
    # -----------------------------------------------------

    incoming_unique = (
        df
        .drop_duplicates()
        .reset_index(drop=True)
    )

    incoming_unique = normalize_database_dates(
        incoming_unique
    )

    existing_unique = existing_df.copy()

    existing_unique = normalize_database_dates(
        existing_unique
    )


    # -----------------------------------------------------
    # NO EXISTING RECORDS
    # -----------------------------------------------------

    if existing_unique.empty:

        duplicate_count = (
            len(df)
            - len(incoming_unique)
        )

        return (
            incoming_unique,
            duplicate_count
        )


    # -----------------------------------------------------
    # MAKE SURE WE COMPARE THE SAME COLUMNS
    # -----------------------------------------------------

    existing_unique = (
        existing_unique[
            incoming_unique.columns
        ]
        .drop_duplicates()
        .reset_index(drop=True)
    )


    # -----------------------------------------------------
    # COMPARE INCOMING RECORDS AGAINST SQLITE
    # -----------------------------------------------------

    comparison = incoming_unique.merge(
        existing_unique,
        how="left",
        on=list(incoming_unique.columns),
        indicator=True
    )


    # -----------------------------------------------------
    # KEEP ONLY NEW RECORDS
    # -----------------------------------------------------

    new_df = (
        comparison[
            comparison["_merge"] == "left_only"
        ]
        .drop(columns="_merge")
        .reset_index(drop=True)
    )


    # -----------------------------------------------------
    # DUPLICATE COUNT
    # -----------------------------------------------------

    duplicate_count = (
        len(df)
        - len(new_df)
    )


    return (
        new_df,
        duplicate_count
    )


# =========================================================
# SOURCE DATA IMPORT
# =========================================================

def import_source_data(df, table_name):
    """
    Create a production table if it does not exist.

    If the table already exists:
        - validate schema
        - detect new records
        - append only new records
    """

    # -----------------------------------------------------
    # CREATE NEW TABLE
    # -----------------------------------------------------

    if not table_exists(table_name):

        df.to_sql(
            table_name,
            conn,
            if_exists="fail",
            index=False
        )

        conn.commit()

        return {
            "created": True,
            "added": len(df),
            "duplicates": 0
        }


    # -----------------------------------------------------
    # CHECK SCHEMA
    # -----------------------------------------------------

    if not schema_matches(
        df,
        table_name
    ):

        raise ValueError(
            "The source file does not match "
            "the existing dataset structure."
        )


    # -----------------------------------------------------
    # READ EXISTING DATA
    # -----------------------------------------------------

    existing_df = pd.read_sql_query(
        f'SELECT * FROM "{table_name}"',
        conn
    )

    existing_df = normalize_database_dates(
        existing_df
    )


    # -----------------------------------------------------
    # FIND NEW RECORDS
    # -----------------------------------------------------

    new_df, duplicate_count = (
        find_new_records(
            df,
            existing_df
        )
    )


    # -----------------------------------------------------
    # APPEND NEW RECORDS
    # -----------------------------------------------------

    if not new_df.empty:

        new_df.to_sql(
            table_name,
            conn,
            if_exists="append",
            index=False
        )

        conn.commit()


    return {
        "created": False,
        "added": len(new_df),
        "duplicates": duplicate_count
    }


# =========================================================
# PENDING DATA FUNCTIONS
# =========================================================

def create_pending_table(
    table_name,
    columns
):
    """
    Create:

        <table_name>_pending

    using the same columns as the production table.
    """

    pending_table = (
        f"{table_name}_pending"
    )

    if not table_exists(
        pending_table
    ):

        empty_df = pd.DataFrame(
            columns=columns
        )

        empty_df.to_sql(
            pending_table,
            conn,
            if_exists="fail",
            index=False
        )

        conn.commit()

    return pending_table


def add_pending_record(
    record_df,
    table_name
):
    """
    Add a new record to the pending table.

    Reject exact duplicates already found in:
        1. Production
        2. Pending
    """

    pending_table = (
        f"{table_name}_pending"
    )


    # -----------------------------------------------------
    # MAKE SURE PENDING TABLE EXISTS
    # -----------------------------------------------------

    create_pending_table(
        table_name,
        list(record_df.columns)
    )


    # -----------------------------------------------------
    # CHECK PRODUCTION
    # -----------------------------------------------------

    production_df = pd.read_sql_query(
        f'SELECT * FROM "{table_name}"',
        conn
    )

    production_df = normalize_database_dates(
        production_df
    )

    record_df = normalize_database_dates(
        record_df
    )


    if not production_df.empty:

        production_df = (
            production_df[
                record_df.columns
            ]
        )

        combined = pd.concat(
            [
                production_df,
                record_df
            ],
            ignore_index=True
        )

        if (
            len(combined.drop_duplicates())
            == len(production_df)
        ):

            return False, "duplicate"


    # -----------------------------------------------------
    # CHECK PENDING
    # -----------------------------------------------------

    pending_df = pd.read_sql_query(
        f'SELECT * FROM "{pending_table}"',
        conn
    )

    pending_df = normalize_database_dates(
        pending_df
    )


    if not pending_df.empty:

        combined = pd.concat(
            [
                pending_df,
                record_df
            ],
            ignore_index=True
        )

        if (
            len(combined.drop_duplicates())
            == len(pending_df)
        ):

            return False, "pending_duplicate"


    # -----------------------------------------------------
    # ADD RECORD
    # -----------------------------------------------------

    record_df.to_sql(
        pending_table,
        conn,
        if_exists="append",
        index=False
    )

    conn.commit()

    return True, "added"


def approve_pending_record(
    table_name,
    row_index
):
    """
    Move one pending record into production.
    """

    pending_table = (
        f"{table_name}_pending"
    )

    pending_df = pd.read_sql_query(
        f'SELECT * FROM "{pending_table}"',
        conn
    )

    if pending_df.empty:
        return False

    if (
        row_index < 0
        or row_index >= len(pending_df)
    ):
        return False


    # -----------------------------------------------------
    # SELECT RECORD
    # -----------------------------------------------------

    record = pending_df.iloc[
        [row_index]
    ].copy()

    record = normalize_database_dates(
        record
    )


    # -----------------------------------------------------
    # FINAL DUPLICATE CHECK
    # -----------------------------------------------------

    production_df = pd.read_sql_query(
        f'SELECT * FROM "{table_name}"',
        conn
    )

    production_df = normalize_database_dates(
        production_df
    )

    new_df, duplicate_count = (
        find_new_records(
            record,
            production_df
        )
    )


    if duplicate_count > 0:
        return False


    # -----------------------------------------------------
    # APPEND TO PRODUCTION
    # -----------------------------------------------------

    new_df.to_sql(
        table_name,
        conn,
        if_exists="append",
        index=False
    )


    # -----------------------------------------------------
    # REMOVE FROM PENDING
    # -----------------------------------------------------

    pending_df = pending_df.drop(
        pending_df.index[row_index]
    )

    pending_df.to_sql(
        pending_table,
        conn,
        if_exists="replace",
        index=False
    )

    conn.commit()

    return True


def reject_pending_record(
    table_name,
    row_index
):
    """
    Permanently remove one record from the pending table
    without adding it to production.
    """

    pending_table = (
        f"{table_name}_pending"
    )

    pending_df = pd.read_sql_query(
        f'SELECT * FROM "{pending_table}"',
        conn
    )

    if pending_df.empty:
        return False

    if (
        row_index < 0
        or row_index >= len(pending_df)
    ):
        return False


    # -----------------------------------------------------
    # REMOVE SELECTED RECORD
    # -----------------------------------------------------

    pending_df = pending_df.drop(
        pending_df.index[row_index]
    )


    # -----------------------------------------------------
    # REWRITE PENDING TABLE
    # -----------------------------------------------------

    pending_df.to_sql(
        pending_table,
        conn,
        if_exists="replace",
        index=False
    )

    conn.commit()

    return True


# =========================================================
# SIDEBAR NAVIGATION
# =========================================================

st.sidebar.title(
    "Navigation"
)

page = st.sidebar.radio(
    "Go to",
    [
        "Admin",
        "Update Records",
        "Reports"
    ]
)


# =========================================================
# PAGE 1 — ADMIN
# =========================================================

if page == "Admin":

    st.title("Admin")


    # =====================================================
    # 1. DETECT / IMPORT
    # =====================================================

    with st.expander(
        "1. Detect / Import",
        expanded=True
    ):

        st.subheader(
            "Source Data"
        )


        # -------------------------------------------------
        # UPLOAD CSV
        # -------------------------------------------------

        uploaded_files = st.file_uploader(
            "Upload CSV file(s)",
            type=["csv"],
            accept_multiple_files=True,
            key="source_csv_upload"
        )


        # -------------------------------------------------
        # DETECT CSV FILES IN DATA FOLDER
        # -------------------------------------------------

        local_files = sorted(
            DATA_FOLDER.glob("*.csv")
        )


        # -------------------------------------------------
        # SHOW DETECTION STATUS
        # -------------------------------------------------

        if local_files:

            st.success(
                f"{len(local_files)} CSV file(s) "
                f"detected in `data/`."
            )

        else:

            st.info(
                "No CSV files were detected in `data/`. "
                "You can still upload CSV files above."
            )


        # -------------------------------------------------
        # COMBINE AVAILABLE SOURCES
        # -------------------------------------------------

        source_options = []


        # Local GitHub files

        for file in local_files:

            source_options.append(
                (
                    file.name,
                    file
                )
            )


        # Uploaded files

        for file in uploaded_files:

            source_options.append(
                (
                    f"{file.name} (Uploaded)",
                    file
                )
            )


        # -------------------------------------------------
        # NO SOURCES
        # -------------------------------------------------

        if not source_options:

            st.warning(
                "No source data is currently available. "
                "Upload a CSV file to begin."
            )


        # -------------------------------------------------
        # SOURCE AVAILABLE
        # -------------------------------------------------

        else:

            st.write(
                f"**{len(source_options)} source file(s) available.**"
            )


            # -------------------------------------------------
            # SOURCE FILE SELECTION
            # -------------------------------------------------

            selected_source_label = st.selectbox(
                "Select source file",
                [
                    item[0]
                    for item in source_options
                ],
                key="source_file"
            )


            selected_source = next(
                item[1]
                for item in source_options
                if item[0] == selected_source_label
            )


            table_name = get_dataset_name(
                selected_source
            )


            st.write(
                f"**Source file:** "
                f"`{selected_source.name}`"
            )

            st.write(
                f"**Detected dataset:** "
                f"`{table_name}`"
            )

            st.write(
                f"**SQLite table:** "
                f"`{table_name}`"
            )


            # -------------------------------------------------
            # READ SOURCE FILE
            # -------------------------------------------------

            try:

                source_df = pd.read_csv(
                    selected_source
                )


                # ---------------------------------------------
                # PREPARE DATA
                # ---------------------------------------------

                prepared_df = prepare_data(
                    source_df
                )


                # ---------------------------------------------
                # PREVIEW
                # ---------------------------------------------

                st.write(
                    "**Source data preview**"
                )

                st.dataframe(
                    prepared_df.head(100),
                    use_container_width=True
                )


                # ---------------------------------------------
                # VALIDATION
                # ---------------------------------------------

                if table_exists(
                    table_name
                ):

                    if schema_matches(
                        prepared_df,
                        table_name
                    ):

                        st.success(
                            "Source structure matches "
                            "the existing SQLite dataset."
                        )


                        existing_df = (
                            pd.read_sql_query(
                                f'SELECT * FROM "{table_name}"',
                                conn
                            )
                        )

                        existing_df = (
                            normalize_database_dates(
                                existing_df
                            )
                        )


                        new_df, duplicate_count = (
                            find_new_records(
                                prepared_df,
                                existing_df
                            )
                        )


                        # -------------------------------------
                        # SUMMARY METRICS
                        # -------------------------------------

                        col1, col2, col3 = (
                            st.columns(3)
                        )


                        with col1:

                            st.metric(
                                "Existing Records",
                                f"{len(existing_df):,}"
                            )


                        with col2:

                            st.metric(
                                "New Records Detected",
                                f"{len(new_df):,}"
                            )


                        with col3:

                            st.metric(
                                "Duplicate Records",
                                f"{duplicate_count:,}"
                            )


                        # -------------------------------------
                        # IMPORT
                        # -------------------------------------

                        if st.button(
                            "Import / Sync Source Data",
                            type="primary",
                            key="import_source"
                        ):

                            try:

                                result = (
                                    import_source_data(
                                        prepared_df,
                                        table_name
                                    )
                                )


                                if result["created"]:

                                    st.success(
                                        f"SQLite table "
                                        f"`{table_name}` created "
                                        f"with "
                                        f"{result['added']:,} "
                                        f"record(s)."
                                    )

                                else:

                                    st.success(
                                        f"Import complete. "
                                        f"{result['added']:,} "
                                        f"new record(s) added."
                                    )

                                    st.info(
                                        f"{result['duplicates']:,} "
                                        f"duplicate record(s) skipped."
                                    )


                                st.rerun()


                            except Exception as e:

                                st.error(
                                    f"Import failed: {e}"
                                )


                    else:

                        st.error(
                            "Source structure does not match "
                            "the existing SQLite dataset."
                        )


                else:

                    st.info(
                        f"SQLite table `{table_name}` "
                        f"does not exist yet."
                    )


                    if st.button(
                        "Create SQLite Table",
                        type="primary",
                        key="create_source_table"
                    ):

                        try:

                            result = (
                                import_source_data(
                                    prepared_df,
                                    table_name
                                )
                            )


                            st.success(
                                f"SQLite table "
                                f"`{table_name}` created "
                                f"with "
                                f"{result['added']:,} "
                                f"record(s)."
                            )

                            st.rerun()


                        except Exception as e:

                            st.error(
                                f"Import failed: {e}"
                            )


            except Exception as e:

                st.error(
                    f"Could not read the source file: {e}"
                )


    # =====================================================
    # 2. APPROVE / REJECT
    # =====================================================

    with st.expander(
        "2. Approve / Reject",
        expanded=True
    ):

        tables = get_sqlite_tables()


        if not tables:

            st.info(
                "No SQLite production tables exist yet."
            )


        else:

            pending_target = st.selectbox(
                "Select dataset",
                tables,
                key="pending_target"
            )


            pending_table = (
                f"{pending_target}_pending"
            )


            if table_exists(
                pending_table
            ):

                pending_df = pd.read_sql_query(
                    f'SELECT * FROM "{pending_table}"',
                    conn
                )


                if pending_df.empty:

                    st.info(
                        "No pending records."
                    )


                else:

                    st.write(
                        f"Pending records: "
                        f"**{len(pending_df):,}**"
                    )


                    st.dataframe(
                        pending_df,
                        use_container_width=True
                    )


                    selected_index = (
                        st.number_input(
                            "Pending row index",
                            min_value=0,
                            max_value=len(pending_df) - 1,
                            step=1,
                            key="pending_row_index"
                        )
                    )


                    col1, col2 = st.columns(2)


                    # -----------------------------------------
                    # APPROVE
                    # -----------------------------------------

                    with col1:

                        if st.button(
                            "Approve Selected Record",
                            type="primary",
                            key="approve_pending"
                        ):

                            success = (
                                approve_pending_record(
                                    pending_target,
                                    int(selected_index)
                                )
                            )


                            if success:

                                st.success(
                                    "Record approved and "
                                    "added to SQLite."
                                )

                                st.rerun()


                            else:

                                st.warning(
                                    "Record could not be approved. "
                                    "It may already exist."
                                )


                    # -----------------------------------------
                    # REJECT
                    # -----------------------------------------

                    with col2:

                        if st.button(
                            "Reject Selected Record",
                            key="reject_pending"
                        ):

                            success = (
                                reject_pending_record(
                                    pending_target,
                                    int(selected_index)
                                )
                            )


                            if success:

                                st.success(
                                    "Pending record rejected "
                                    "and removed."
                                )

                                st.rerun()


                            else:

                                st.warning(
                                    "Record could not be rejected."
                                )


            else:

                st.info(
                    "No pending records for this dataset."
                )


    # =====================================================
    # 3. DELETE / EXPORT
    # =====================================================

    with st.expander(
        "3. Delete / Export",
        expanded=False
    ):

        tables = get_sqlite_tables()


        if not tables:

            st.info(
                "No SQLite tables are available."
            )


        else:

            # -------------------------------------------------
            # EXPORT
            # -------------------------------------------------

            st.write(
                "### Export"
            )


            export_table = st.selectbox(
                "Select dataset to export",
                tables,
                key="export_table"
            )


            export_df = pd.read_sql_query(
                f'SELECT * FROM "{export_table}"',
                conn
            )


            csv_data = (
                export_df
                .to_csv(index=False)
                .encode("utf-8")
            )


            st.write(
                f"Records: "
                f"**{len(export_df):,}**"
            )


            st.download_button(
                label="Export Table as CSV",
                data=csv_data,
                file_name=f"{export_table}.csv",
                mime="text/csv"
            )


            st.divider()


            # -------------------------------------------------
            # DELETE
            # -------------------------------------------------

            st.write(
                "### Delete SQLite Tables"
            )


            delete_tables = st.multiselect(
                "Select SQLite table(s) to delete",
                tables,
                key="delete_tables"
            )


            if delete_tables:

                st.warning(
                    "The selected table(s) and all of their "
                    "records will be permanently deleted."
                )


                st.write(
                    "**Selected tables:** "
                    + ", ".join(
                        f"`{table}`"
                        for table in delete_tables
                    )
                )


                if st.button(
                    "Delete Selected SQLite Tables",
                    type="secondary",
                    key="delete_selected_tables"
                ):

                    st.session_state[
                        "confirm_delete_tables"
                    ] = True


            # -------------------------------------------------
            # DELETE CONFIRMATION
            # -------------------------------------------------

            if st.session_state.get(
                "confirm_delete_tables",
                False
            ):

                st.error(
                    "Are you sure you want to permanently "
                    "delete the selected SQLite tables?"
                )


                confirm_col, cancel_col = (
                    st.columns(2)
                )


                with confirm_col:

                    if st.button(
                        "Yes, Delete Selected Tables",
                        type="primary",
                        key="confirm_delete_tables_button"
                    ):

                        try:

                            delete_sqlite_tables(
                                delete_tables
                            )


                            st.session_state[
                                "confirm_delete_tables"
                            ] = False


                            st.success(
                                "Selected SQLite table(s) "
                                "deleted successfully."
                            )


                            st.rerun()


                        except Exception as e:

                            st.error(
                                f"Delete failed: {e}"
                            )


                with cancel_col:

                    if st.button(
                        "Cancel",
                        key="cancel_delete_tables"
                    ):

                        st.session_state[
                            "confirm_delete_tables"
                        ] = False

                        st.rerun()


# =========================================================
# PAGE 2 — UPDATE RECORDS
# =========================================================

elif page == "Update Records":

    st.title("Update Records")


    sqlite_tables = (
        get_sqlite_tables()
    )


    if not sqlite_tables:

        st.info(
            "No SQLite tables available. "
            "Import source data first."
        )


    else:

        selected_table = st.selectbox(
            "Select dataset",
            sqlite_tables,
            key="new_data_table"
        )


        st.write(
            f"**Enter new record for:** "
            f"`{selected_table}`"
        )


        with st.form(
            "new_data_form"
        ):

            hatch_date = st.date_input(
                "HATCH DATE"
            )


            death_date = st.date_input(
                "DEATH DATE"
            )


            record_month = st.selectbox(
                "RECORD MONTH",
                MONTHS
            )


            gender = st.text_input(
                "GENDER"
            )


            wingband = st.text_input(
                "APEX WINGBAND"
            )


            legband = st.text_input(
                "APEX LEGBAND"
            )


            markings = st.text_input(
                "MARKINGS"
            )


            area = st.text_input(
                "AREA"
            )


            count = st.number_input(
                "COUNT",
                min_value=0,
                step=1
            )


            submitted = (
                st.form_submit_button(
                    "Submit for Review"
                )
            )


        if submitted:

            record_df = pd.DataFrame(
                [
                    {
                        "HATCH DATE": hatch_date,
                        "DEATH DATE": death_date,
                        "RECORD MONTH": record_month,
                        "GENDER": gender,
                        "APEX WINGBAND": wingband,
                        "APEX LEGBAND": legband,
                        "MARKINGS": markings,
                        "AREA": area,
                        "COUNT": count
                    }
                ]
            )


            # ---------------------------------------------
            # CALCULATE DERIVED FIELDS
            # ---------------------------------------------

            record_df = prepare_data(
                record_df
            )


            # ---------------------------------------------
            # MATCH TABLE STRUCTURE
            # ---------------------------------------------

            table_columns = (
                get_table_columns(
                    selected_table
                )
            )


            try:

                record_df = record_df[
                    table_columns
                ]


            except KeyError:

                st.error(
                    "The standard input fields do not "
                    "match the selected dataset."
                )


            else:

                added, status = (
                    add_pending_record(
                        record_df,
                        selected_table
                    )
                )


                if added:

                    st.success(
                        "Record submitted for review."
                    )


                elif status == "duplicate":

                    st.warning(
                        "This record already exists "
                        "in the production database."
                    )


                elif status == "pending_duplicate":

                    st.warning(
                        "This record is already "
                        "pending review."
                    )


# =========================================================
# PAGE 3 — REPORTS
# =========================================================

elif page == "Reports":

    st.title("Reports")


    # =====================================================
    # BASIC SUMMARY
    # =====================================================

    with st.expander(
        "Basic Summary",
        expanded=True
    ):

        tables = (
            get_sqlite_tables()
        )


        if not tables:

            st.info(
                "No SQLite tables available "
                "for reporting."
            )


        else:

            selected_report_table = st.selectbox(
                "Select dataset",
                tables,
                key="report_table"
            )


            report_df = pd.read_sql_query(
                f'SELECT * FROM "{selected_report_table}"',
                conn
            )


            st.write(
                f"### Summary — "
                f"`{selected_report_table}`"
            )


            # -------------------------------------------------
            # TOP SUMMARY METRICS
            # -------------------------------------------------

            col1, col2, col3 = (
                st.columns(3)
            )


            with col1:

                st.metric(
                    "Total Records",
                    f"{len(report_df):,}"
                )


            with col2:

                if "COUNT" in report_df.columns:

                    total_count = pd.to_numeric(
                        report_df["COUNT"],
                        errors="coerce"
                    ).sum()

                else:

                    total_count = 0


                st.metric(
                    "Total Count",
                    f"{total_count:,.0f}"
                )


            with col3:

                if "AREA" in report_df.columns:

                    areas = (
                        report_df["AREA"]
                        .dropna()
                        .nunique()
                    )

                else:

                    areas = 0


                st.metric(
                    "Areas",
                    f"{areas:,}"
                )


            # -------------------------------------------------
            # GENDER SUMMARY
            # -------------------------------------------------

            if "GENDER" in report_df.columns:

                st.write(
                    "#### Gender"
                )


                gender_summary = (
                    report_df[
                        "GENDER"
                    ]
                    .fillna("Unknown")
                    .replace("", "Unknown")
                    .value_counts()
                    .rename_axis("GENDER")
                    .reset_index(
                        name="RECORDS"
                    )
                )


                st.dataframe(
                    gender_summary,
                    use_container_width=True,
                    hide_index=True
                )


            # -------------------------------------------------
            # AGE CLASS SUMMARY
            # -------------------------------------------------

            if "AGE CLASS" in report_df.columns:

                st.write(
                    "#### Age Class"
                )


                age_summary = (
                    report_df[
                        "AGE CLASS"
                    ]
                    .fillna("Unknown")
                    .value_counts()
                    .rename_axis("AGE CLASS")
                    .reset_index(
                        name="RECORDS"
                    )
                )


                st.dataframe(
                    age_summary,
                    use_container_width=True,
                    hide_index=True
                )


            # -------------------------------------------------
            # RECORD MONTH SUMMARY
            # -------------------------------------------------

            if "RECORD MONTH" in report_df.columns:

                st.write(
                    "#### Record Month"
                )


                month_summary = (
                    report_df[
                        "RECORD MONTH"
                    ]
                    .value_counts()
                    .reindex(
                        MONTHS,
                        fill_value=0
                    )
                    .rename_axis(
                        "RECORD MONTH"
                    )
                    .reset_index(
                        name="RECORDS"
                    )
                )


                st.dataframe(
                    month_summary,
                    use_container_width=True,
                    hide_index=True
                )


            # -------------------------------------------------
            # AREA SUMMARY
            # -------------------------------------------------

            if "AREA" in report_df.columns:

                st.write(
                    "#### Area"
                )


                area_summary = (
                    report_df[
                        "AREA"
                    ]
                    .fillna("Unknown")
                    .replace("", "Unknown")
                    .value_counts()
                    .rename_axis("AREA")
                    .reset_index(
                        name="RECORDS"
                    )
                )


                st.dataframe(
                    area_summary,
                    use_container_width=True,
                    hide_index=True
                )


# =========================================================
# CLOSE DATABASE
# =========================================================

conn.close()
