# ─── MODULE METADATA ────────────────────────────────────────────────────────
# module:        _processing_worker.py
# version:       1.0.0
# project:       Respondeo eDiscovery Platform
# project_ver:   2.9.0
# last_modified: 2026-04-08 12:30
# modified_by:   claude-code
# last_commit:   pending
# ─────────────────────────────────────────────────────────────────────────────
"""
Standalone processing worker — invoked via subprocess.Popen from 2_Processor.py.

Runs all three processing phases in a clean Python process (no Streamlit).
Progress is reported via the `jobs` table in the case database.
The worker process survives Streamlit session disconnects.

Usage:
    python _processing_worker.py <case_folder> <job_id> [--threads N]
"""
import sys
import os
import argparse
import json
import logging
import time

# Ensure project root is on the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import db_manager
import processing_engine


def main():
    parser = argparse.ArgumentParser(description="Background processing worker")
    parser.add_argument("case_folder", help="Path to the case folder")
    parser.add_argument("job_id", type=int, help="Job ID from the jobs table")
    parser.add_argument("--threads", type=int, default=4, help="Max worker threads for Phase 2")
    args = parser.parse_args()

    case_folder = args.case_folder
    job_id = args.job_id
    max_threads = args.threads

    # Validate case folder
    db_path = os.path.join(case_folder, "case.db")
    if not os.path.exists(db_path):
        print(f"ERROR: case.db not found at {db_path}", file=sys.stderr)
        sys.exit(2)

    # Set up logger
    audit_path = os.path.join(case_folder, "Audit")
    logger = processing_engine.setup_logger(audit_path)

    # Read job info
    job = db_manager.get_job(case_folder, job_id)
    if not job:
        logger.error(f"Job {job_id} not found in database")
        sys.exit(2)

    username = job.get('username', 'system') or 'system'

    # Check for conflicting active jobs
    active = db_manager.get_active_job(case_folder, 'processing')
    if active and active['id'] != job_id and active['status'] == 'running':
        logger.error(f"Another processing job (ID {active['id']}) is already running for this case")
        db_manager.fail_job(case_folder, job_id, "Another processing job is already running")
        sys.exit(1)

    # Register as running
    db_manager.start_job(case_folder, job_id, os.getpid())
    logger.info(f"Background worker started: job_id={job_id}, case={case_folder}, threads={max_threads}, pid={os.getpid()}")

    # Paths
    temp_path = os.path.join(case_folder, "Temp_Explode")
    processed_path = os.path.join(case_folder, "Processed")
    if not os.path.exists(processed_path):
        os.makedirs(processed_path)

    # Details blob — accumulates stats across phases
    details = {
        "max_threads": max_threads,
        "recent_warnings": [],  # Last 10 warnings for live UI display
    }

    def _add_warning(msg):
        """Add a warning to the details blob (capped at 10 most recent)."""
        details["recent_warnings"].append(msg)
        if len(details["recent_warnings"]) > 10:
            details["recent_warnings"] = details["recent_warnings"][-10:]

    def on_progress(phase, completed, total, message):
        """Write progress to the jobs table. Batched — called every ~50 docs."""
        db_manager.update_job_progress(
            case_folder, job_id,
            phase=phase, progress=completed, total=total,
            phase_label=message,
            details_json=details
        )

    def check_cancel():
        """Check the cancel flag in the jobs table."""
        return db_manager.is_cancel_requested(case_folder, job_id)

    try:
        # --- PHASE 1: CONTAINER EXTRACTION ---
        on_progress(1, 0, 0, "Phase 1: Starting container extraction...")
        db_manager.log_audit(case_folder, "PROCESSING_STARTED", username=username,
            module="Processor", details=json.dumps({"phase": 1, "background": True}))

        extraction_summary = processing_engine.run_phase_1(
            case_folder, temp_path, username=username,
            on_progress=on_progress, check_cancel=check_cancel
        )

        details["phase1_summary"] = extraction_summary
        if extraction_summary:
            partial = [s for s in extraction_summary if s['failed_folders'] or (s['expected'] > 0 and s['extracted'] < s['expected'])]
            if partial:
                _add_warning(f"Phase 1: {len(partial)} container(s) had partial extraction")

        if check_cancel():
            db_manager.update_job_progress(case_folder, job_id, 1, 0, 0,
                "Cancelled during Phase 1", details)
            conn_cancel = db_manager.get_connection(case_folder)
            conn_cancel.execute("UPDATE jobs SET status='cancelled', finished_at=? WHERE id=?",
                (time.strftime('%Y-%m-%dT%H:%M:%S'), job_id))
            conn_cancel.commit()
            conn_cancel.close()
            logger.info(f"Job {job_id} cancelled during Phase 1")
            return

        # --- PHASE 2: PARALLEL TEXT EXTRACTION ---
        on_progress(2, 0, 0, "Phase 2: Starting parallel text extraction...")

        completed, total_docs, thread_errors, was_cancelled = processing_engine.run_phase_2(
            case_folder, processed_path, max_threads, username=username,
            on_progress=on_progress, check_cancel=check_cancel
        )

        details["phase2_completed"] = completed
        details["phase2_total"] = total_docs
        details["phase2_errors"] = len(thread_errors)
        if thread_errors:
            for err in thread_errors[:5]:
                _add_warning(f"Phase 2 error: {err[:200]}")

        if was_cancelled:
            db_manager.update_job_progress(case_folder, job_id, 2, completed, total_docs,
                f"Cancelled during Phase 2 ({completed}/{total_docs})", details)
            conn_cancel = db_manager.get_connection(case_folder)
            conn_cancel.execute("UPDATE jobs SET status='cancelled', finished_at=? WHERE id=?",
                (time.strftime('%Y-%m-%dT%H:%M:%S'), job_id))
            conn_cancel.commit()
            conn_cancel.close()
            logger.info(f"Job {job_id} cancelled during Phase 2 ({completed}/{total_docs})")
            return

        # --- PHASE 3: EMAIL IMAGING ---
        on_progress(3, 0, 0, "Phase 3: Starting email imaging...")

        img_success, img_fail, img_total = processing_engine.run_phase_3(
            case_folder, processed_path, username=username,
            on_progress=on_progress, check_cancel=check_cancel
        )

        details["phase3_imaged"] = img_success
        details["phase3_failed"] = img_fail
        details["phase3_total"] = img_total
        if img_fail > 0:
            _add_warning(f"Phase 3: {img_fail} email(s) failed imaging")

        # --- BATCH REPORT ---
        report_path, suspicious_count = processing_engine.generate_batch_report(
            case_folder, audit_path
        )
        details["report_path"] = report_path
        details["suspicious_count"] = suspicious_count

        # --- COMPLETION ---
        db_manager.log_audit(case_folder, "PROCESSING_COMPLETED", username=username,
            module="Processor", details=json.dumps({
                "processed": total_docs, "background": True,
                "images_ok": img_success, "images_fail": img_fail,
                "suspicious": suspicious_count
            }))

        db_manager.complete_job(case_folder, job_id, details_json=details)
        logger.info(
            f"Job {job_id} completed: {total_docs} docs processed, "
            f"{img_success}/{img_total} emails imaged, {suspicious_count} suspicious"
        )

    except Exception as e:
        logger.error(f"Job {job_id} failed with unhandled exception: {e}", exc_info=True)
        _add_warning(f"Fatal error: {str(e)[:200]}")
        db_manager.fail_job(case_folder, job_id, str(e)[:2000], details_json=details)
        sys.exit(1)


if __name__ == '__main__':
    main()
