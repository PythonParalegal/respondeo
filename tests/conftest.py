"""
conftest.py — shared pytest fixtures for the Respondeo eDiscovery Platform test suite.

All tests are designed to run headlessly without Streamlit, Tika, or
OpenSearch. External-service tests are gated behind pytest marks.
"""
import os
import sys
import zipfile
import pytest

# ---------------------------------------------------------------------------
# Make the project root importable from within tests/
# ---------------------------------------------------------------------------
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


# ---------------------------------------------------------------------------
# Core fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def case_folder(tmp_path):
    """
    Temp case folder with a fully initialised case.db.
    Cleaned up automatically by pytest after each test.
    """
    import db_manager
    folder = str(tmp_path / "test_case")
    os.makedirs(folder)
    db_manager.init_db(folder)
    return folder


@pytest.fixture()
def seeded_case(case_folder):
    """
    case_folder with 3 documents pre-inserted in 'Processed' status.
    Returns (case_folder, [control_numbers]).
    """
    import db_manager
    conn = db_manager.get_connection(case_folder)
    docs = [
        ("DOC-00001", "invoice.pdf",  ".pdf",  "Processed", 2, "custodian_a"),
        ("DOC-00002", "memo.docx",    ".docx", "Processed", 1, "custodian_b"),
        ("DOC-00003", "sheet.xlsx",   ".xlsx", "Processed", 5, "custodian_a"),
    ]
    conn.executemany(
        """INSERT OR IGNORE INTO documents
           (control_number, file_name, file_extension, processing_status, page_count, custodian)
           VALUES (?, ?, ?, ?, ?, ?)""",
        docs,
    )
    conn.commit()
    conn.close()
    return case_folder, [d[0] for d in docs]


@pytest.fixture()
def auth_config_file(tmp_path):
    """
    Temp auth_config.yaml path, patched into auth_manager.AUTH_CONFIG_PATH.
    Also sets st.session_state['user_role'] = 'admin' so CRUD guards pass
    in headless pytest (no Streamlit runtime).
    Yields the path; the file starts empty (no users).
    """
    import auth_manager
    import streamlit as st
    config_path = str(tmp_path / "auth_config.yaml")
    original = auth_manager.AUTH_CONFIG_PATH
    auth_manager.AUTH_CONFIG_PATH = config_path
    prev_role = st.session_state.get('user_role')
    st.session_state['user_role'] = 'admin'
    yield config_path
    auth_manager.AUTH_CONFIG_PATH = original
    if prev_role is None:
        st.session_state.pop('user_role', None)
    else:
        st.session_state['user_role'] = prev_role


@pytest.fixture()
def sample_zip(tmp_path):
    """
    A minimal ZIP archive containing two text files.
    Returns the path to the .zip file.
    """
    zip_path = str(tmp_path / "sample.zip")
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("doc_a.txt", "Content of document A.")
        zf.writestr("subdir/doc_b.txt", "Content of document B in subdir.")
    return zip_path


@pytest.fixture()
def sample_eml():
    """Path to the static sample EML in tests/fixtures/."""
    return os.path.join(FIXTURES_DIR, "sample.eml")
