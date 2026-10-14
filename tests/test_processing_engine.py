"""
test_processing_engine.py — regression tests for the family-model fix in
processing_engine.add_children_to_db (beta-2.15 Commit 4).

Pinned-value tests for the three cases that define the family-model rule:

  1. Archive container at top-of-family (.pst/.zip) — direct children
     each START a new family rooted at themselves. group_id != parent's.
  2. Email container (.eml/.msg) — direct children INHERIT the email's
     group_id (email-rooted family).
  3. Archive nested inside an email family — propagates the email's
     group_id DOWN through the archive to the archive's contents,
     preserving the email-rooted boundary.

See docs/lessons/container-family-model.md for the full pattern and
docs/archive/audits/beta-2.15/commit_4_pst_family_model_fix_preflight.md §3.1 for the
case-walk that justifies these invariants.
"""
import sqlite3

import pytest

import processing_engine


# ---------------------------------------------------------------------------
# Test fixtures: minimal documents-table schema + Row-factory connection
# ---------------------------------------------------------------------------

def _create_documents_table(conn):
    """Minimal schema covering the columns add_children_to_db touches."""
    conn.execute("""
        CREATE TABLE documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            control_number TEXT,
            file_name TEXT,
            full_path TEXT,
            original_path TEXT,
            file_extension TEXT,
            file_size_kb REAL,
            md5_hash TEXT UNIQUE,
            processing_status TEXT,
            parent_id TEXT,
            group_id TEXT,
            custodian TEXT,
            volume TEXT,
            record_type TEXT,
            extraction_notes TEXT
        )
    """)
    conn.commit()


def _insert_self_rooted_parent(conn, *, file_extension, custodian='Custodian-X',
                                volume='VOL001'):
    """Insert a parent row in the post-processing self-rooted state
    (group_id == own DOC-id form). Returns the parent's Row object."""
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO documents (file_name, full_path, original_path, file_extension,
                               file_size_kb, md5_hash, processing_status,
                               custodian, volume, record_type)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        f"parent{file_extension}", f"/tmp/parent{file_extension}",
        f"/tmp/parent{file_extension}", file_extension, 1.0,
        f"md5-parent-{file_extension}", 'Container_Scanned',
        custodian, volume, 'Container',
    ))
    parent_id = cur.lastrowid
    parent_id_str = f"DOC-{parent_id:06d}"
    cur.execute(
        "UPDATE documents SET control_number = ?, group_id = ? WHERE id = ?",
        (parent_id_str, parent_id_str, parent_id),
    )
    conn.commit()
    return conn.execute("SELECT * FROM documents WHERE id=?", (parent_id,)).fetchone()


@pytest.fixture
def conn(tmp_path):
    """Per-test SQLite connection with documents table + Row factory."""
    db_path = str(tmp_path / "test.db")
    c = sqlite3.connect(db_path)
    c.row_factory = sqlite3.Row
    _create_documents_table(c)
    yield c
    c.close()


@pytest.fixture
def two_email_children(tmp_path):
    """Two real on-disk files representing extracted email children.
    add_children_to_db reads file size + md5 from these."""
    f1 = tmp_path / "child_email_1.eml"
    f1.write_bytes(b"email 1 body")
    f2 = tmp_path / "child_email_2.eml"
    f2.write_bytes(b"email 2 body - distinct content for unique md5")
    return [
        ('child_email_1.eml', str(f1), 'email1.eml'),
        ('child_email_2.eml', str(f2), 'email2.eml'),
    ]


@pytest.fixture
def two_attachment_children(tmp_path):
    f1 = tmp_path / "attach1.pdf"
    f1.write_bytes(b"attachment 1 bytes")
    f2 = tmp_path / "attach2.pdf"
    f2.write_bytes(b"attachment 2 bytes - distinct")
    return [
        ('attach1.pdf', str(f1), 'attach1.pdf'),
        ('attach2.pdf', str(f2), 'attach2.pdf'),
    ]


# ---------------------------------------------------------------------------
# Pinned-value tests for the family-model rule
# ---------------------------------------------------------------------------

def test_add_children_to_db_pst_assigns_email_family(conn, two_email_children):
    """PST at top-of-family — each extracted email gets its OWN DOC-id
    form as group_id. The PST's group_id MUST NOT propagate. This is
    the headline fix for beta-2.15 Commit 4 (the bug that exported
    ~500-doc PSTs as one mega-PDF)."""
    parent_row = _insert_self_rooted_parent(conn, file_extension='.pst')
    parent_group_id = parent_row['group_id']

    new_rows = processing_engine.add_children_to_db(conn, parent_row, two_email_children)

    assert len(new_rows) == 2, "Both email children should have been inserted"
    for child in new_rows:
        own_doc_id = f"DOC-{child['id']:06d}"
        assert child['group_id'] == own_doc_id, (
            f"Email child {child['file_name']} should have group_id == own "
            f"DOC-id ({own_doc_id}), got {child['group_id']!r}"
        )
        assert child['group_id'] != parent_group_id, (
            f"Email child {child['file_name']} must NOT inherit PST's "
            f"group_id ({parent_group_id})"
        )


def test_add_children_to_db_email_propagates(conn, two_attachment_children):
    """Email at top-of-family — attachments INHERIT the email's
    group_id (email-rooted family is preserved)."""
    parent_row = _insert_self_rooted_parent(conn, file_extension='.eml')
    parent_group_id = parent_row['group_id']

    new_rows = processing_engine.add_children_to_db(conn, parent_row, two_attachment_children)

    assert len(new_rows) == 2
    for child in new_rows:
        assert child['group_id'] == parent_group_id, (
            f"Attachment {child['file_name']} should inherit email's "
            f"group_id ({parent_group_id}), got {child['group_id']!r}"
        )


def test_add_children_to_db_nested_archive_in_email_propagates(conn, tmp_path):
    """Cascading three-layer extraction: PST → email → ZIP → file.
    The innermost file's group_id MUST equal the email's DOC-id form,
    NOT the ZIP's and NOT the PST's. This is the corner case PM's
    §3.1.2 NULL-handling derivation calls out as the reason
    `parent.group_id == parent_id_str` is the correct top-of-family
    test (instead of `parent.parent_id IS NULL`)."""
    # Layer 1: PST at top of family → email child gets its own DOC-id.
    pst_row = _insert_self_rooted_parent(conn, file_extension='.pst')
    email_file = tmp_path / "msg.eml"
    email_file.write_bytes(b"email content for nested test")
    [email_row] = processing_engine.add_children_to_db(
        conn, pst_row, [('msg.eml', str(email_file), 'msg.eml')]
    )
    email_doc_id = f"DOC-{email_row['id']:06d}"
    assert email_row['group_id'] == email_doc_id, (
        "PRECONDITION: email under PST should be its own family root"
    )

    # Layer 2: Email parent (not archive) → ZIP attachment INHERITS email's group_id.
    zip_file = tmp_path / "attached.zip"
    zip_file.write_bytes(b"zip container bytes")
    [zip_row] = processing_engine.add_children_to_db(
        conn, email_row, [('attached.zip', str(zip_file), 'attached.zip')]
    )
    assert zip_row['group_id'] == email_doc_id, (
        f"ZIP attached to email must inherit email's group_id "
        f"({email_doc_id}), got {zip_row['group_id']!r}"
    )

    # Layer 3: ZIP parent (archive but NOT top-of-family — its group_id
    # is the email's DOC-id, not its own) → contents INHERIT email's group_id.
    inner_file = tmp_path / "doc.txt"
    inner_file.write_bytes(b"document content inside zip")
    [inner_row] = processing_engine.add_children_to_db(
        conn, zip_row, [('doc.txt', str(inner_file), 'doc.txt')]
    )
    assert inner_row['group_id'] == email_doc_id, (
        f"File inside nested-ZIP-in-email must inherit email's group_id "
        f"({email_doc_id}), got {inner_row['group_id']!r}. The ZIP's "
        f"presence in the chain MUST NOT break the email-rooted family."
    )
