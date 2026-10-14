"""
Audit script: Find documents with redaction marks but missing privilege_status.

Usage:
    python audit_redaction_disposition.py "D:\eDiscovery\YourCaseName"

Optional --fix flag to repair the mismatches:
    python audit_redaction_disposition.py "D:\eDiscovery\YourCaseName" --fix
"""
import sys
import os
import sqlite3

def audit(case_folder, fix=False):
    db_path = os.path.join(case_folder, "case.db")
    if not os.path.exists(db_path):
        print(f"ERROR: No case.db found at {db_path}")
        sys.exit(1)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # Find documents with ACTUAL redaction marks but NULL or empty privilege_status
    # marks_json must exist, not be empty, and not be an empty JSON array '[]'
    mismatches = conn.execute("""
        SELECT DISTINCT d.control_number, d.file_name, d.privilege_status,
               d.redaction_status, d.tags, d.production_category,
               COUNT(r.id) as mark_count
        FROM redaction_marks r
        JOIN documents d ON d.control_number = r.control_number
        WHERE (d.privilege_status IS NULL OR d.privilege_status = '')
          AND r.marks_json IS NOT NULL
          AND r.marks_json != ''
          AND r.marks_json != '[]'
          AND LENGTH(r.marks_json) > 2
        GROUP BY d.control_number
        ORDER BY d.control_number
    """).fetchall()

    # Also check the reverse: privilege_status = 'Redact' but NO actual redaction marks
    orphan_status = conn.execute("""
        SELECT d.control_number, d.file_name, d.privilege_status, d.tags
        FROM documents d
        WHERE d.privilege_status = 'Redact'
          AND d.control_number NOT IN (
              SELECT DISTINCT control_number FROM redaction_marks
              WHERE marks_json IS NOT NULL
                AND marks_json != ''
                AND marks_json != '[]'
                AND LENGTH(marks_json) > 2
          )
        ORDER BY d.control_number
    """).fetchall()

    # Summary stats — only count rows with actual mark data
    total_with_marks = conn.execute("""
        SELECT COUNT(DISTINCT control_number) FROM redaction_marks
        WHERE marks_json IS NOT NULL
          AND marks_json != ''
          AND marks_json != '[]'
          AND LENGTH(marks_json) > 2
    """).fetchone()[0]

    total_with_status = conn.execute(
        "SELECT COUNT(*) FROM documents WHERE privilege_status IS NOT NULL AND privilege_status != ''"
    ).fetchone()[0]

    print("=" * 70)
    print("REDACTION / PRIVILEGE DISPOSITION AUDIT")
    print(f"Case: {case_folder}")
    print("=" * 70)
    print(f"Documents with redaction marks:       {total_with_marks}")
    print(f"Documents with privilege_status set:   {total_with_status}")
    print()

    if mismatches:
        print(f"PROBLEM: {len(mismatches)} document(s) have redaction marks but NO privilege_status:")
        print("-" * 70)
        for row in mismatches:
            print(f"  {row['control_number']:15s}  {row['file_name'][:45]:45s}  "
                  f"marks: {row['mark_count']}  status: {row['privilege_status'] or 'NULL'}")
        print()

        if fix:
            print("FIXING: Setting privilege_status = 'Redact' for these documents...")
            for row in mismatches:
                conn.execute(
                    "UPDATE documents SET privilege_status = 'Redact' WHERE control_number = ?",
                    (row['control_number'],)
                )
            conn.commit()
            print(f"  Updated {len(mismatches)} documents.")
        else:
            print("Run with --fix flag to repair these documents.")
    else:
        print("ALL CLEAR: Every document with redaction marks has privilege_status set.")

    print()

    if orphan_status:
        print(f"NOTE: {len(orphan_status)} document(s) have privilege_status='Redact' but NO redaction marks:")
        print("  (These may have been set via privilege tags rather than redaction marks — likely OK)")
        print("-" * 70)
        for row in orphan_status:
            tags = row['tags'] or ''
            print(f"  {row['control_number']:15s}  {row['file_name'][:45]:45s}  tags: {tags[:40]}")
    else:
        print("No orphaned privilege_status entries found.")

    print()
    conn.close()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python audit_redaction_disposition.py <case_folder> [--fix]")
        sys.exit(1)

    case_path = sys.argv[1]
    do_fix = "--fix" in sys.argv
    audit(case_path, fix=do_fix)
