# ─── MODULE METADATA ────────────────────────────────────────────────────────
# module:        container_exploder.py
# version:       1.13.0
# project:       Respondeo eDiscovery Platform
# project_ver:   2.15.0
# last_modified: 2026-05-21 15:33
# modified_by:   claude-code
# last_commit:   pending
# ─────────────────────────────────────────────────────────────────────────────
import os
import sys
import re
import logging
import shutil
import tempfile
import zipfile
import email
from email import policy
import uuid
import mimetypes
import struct
import binascii
from typing import NamedTuple

logger = logging.getLogger("ProcessorLogger")


class HtmlInlineRefs(NamedTuple):
    """References to inline content extracted from an email's HTML body.

    Populated by _collect_html_inline_refs; consumed by is_part_inline_image
    (extraction-side and rendering-side both) to classify whether a MIME part
    is a true inline image or a real attachment.
    """
    filenames: set  # lowercase filenames referenced via <img src="...">
    cids: set       # CIDs (no angle brackets) referenced via <img src="cid:...">


def is_part_inline_image(part, html_cids, html_filenames):
    """Return True iff a MIME part is truly inline.

    A part is "truly inline" iff it is an image AND the HTML body
    actually references it — either by Content-ID (via <img src="cid:...">
    matching the part's CID) or by filename (via <img src="..."> matching
    the part's filename).

    Non-image parts are never inline, regardless of Content-ID. This
    corrects the pre-Commit-5 defect where libpff-stamped CIDs on
    .docx/.xlsx/.pdf attachments caused them to be silently dropped
    during extraction.

    Pinned-value source of truth for both _explode_eml (extraction)
    and universal_imager.convert_eml_to_pdf (rendering). See
    docs/lessons/extraction-rendering-symmetry.md.
    """
    if part.get_content_maintype() != 'image':
        return False
    cid = part.get('Content-ID')
    if cid and cid.strip('<>') in html_cids:
        return True
    fname = part.get_filename() or ''
    if fname and fname.lower() in html_filenames:
        return True
    return False


def _strip_long_path_prefix(p):
    """Strip Windows \\\\?\\ extended-length prefix — COM APIs don't accept it."""
    if p and p.startswith('\\\\?\\'):
        return p[4:]
    return p

def _get_record_entry(obj, property_tag):
    """
    Read a MAPI property from a pypff object's record sets.
    Returns the record_entry object, or None if not found.

    See docs/references/LIBPFF_API_REFERENCE.md for property tag values.
    """
    for rs_idx in range(obj.number_of_record_sets):
        rs = obj.get_record_set(rs_idx)
        for e_idx in range(rs.number_of_entries):
            entry = rs.get_entry(e_idx)
            if entry.entry_type == property_tag:
                return entry
    return None

def _get_record_string(obj, property_tag):
    """Read a string MAPI property (value_type 31 = PT_UNICODE)."""
    entry = _get_record_entry(obj, property_tag)
    if entry is None:
        return None
    try:
        val = entry.data_as_string
        if val and str(val).strip():
            return str(val).strip()
    except Exception:
        # Fallback: manual UTF-16-LE decode
        if entry.data:
            try:
                val = entry.data.decode('utf-16-le').rstrip('\x00').strip()
                if val:
                    return val
            except UnicodeDecodeError as e:
                logger.debug("OLE string decode fallback failed for property tag: %s", e)
    return None

def _get_record_integer(obj, property_tag):
    """Read an integer MAPI property (value_type 3 = PT_LONG)."""
    entry = _get_record_entry(obj, property_tag)
    if entry is None:
        return None
    try:
        return entry.data_as_integer
    except Exception:
        return None


def get_file_type(filepath):
    _, ext = os.path.splitext(filepath)
    return ext.lower()


def find_scanpst():
    """
    Locate Microsoft's ScanPST.exe (Inbox Repair Tool) on this machine.
    Returns the full path if found, None otherwise.

    ScanPST is a standalone GUI tool that repairs corrupted PST files.
    It ships with every Microsoft Office installation.
    """
    import glob

    if not sys.platform.startswith('win'):
        return None

    # Common installation paths by Office version
    search_patterns = [
        # Office 365 / 2019 / 2021 (Click-to-Run)
        r"C:\Program Files\Microsoft Office\root\Office16\SCANPST.EXE",
        r"C:\Program Files (x86)\Microsoft Office\root\Office16\SCANPST.EXE",
        # Office 2016 (MSI)
        r"C:\Program Files\Microsoft Office\Office16\SCANPST.EXE",
        r"C:\Program Files (x86)\Microsoft Office\Office16\SCANPST.EXE",
        # Office 2013
        r"C:\Program Files\Microsoft Office\Office15\SCANPST.EXE",
        r"C:\Program Files (x86)\Microsoft Office\Office15\SCANPST.EXE",
        # Broader glob fallback
        r"C:\Program Files*\Microsoft Office*\**\SCANPST.EXE",
    ]

    for pattern in search_patterns:
        if '*' in pattern:
            matches = glob.glob(pattern, recursive=True)
            if matches:
                return matches[0]
        elif os.path.isfile(pattern):
            return pattern

    return None


def explode_container(filepath, output_dir, log_path=None):
    """
    Checks if file is a container. If so, extracts children to output_dir.

    .pst → explode_pst_isolated() [COM in-process primary, libpff subprocess fallback]
    .zip → _explode_zip()
    .eml → _explode_eml()

    NOTE: .msg files must be processed in batches via process_msg_batch().

    For PSTs, returns a dict with 'children', 'expected_count',
    'extracted_count', and 'failed_folders'. For other types, returns
    a list of (filename, physical_path, logical_path) tuples.
    Returns [] if not a container.
    """
    filepath = _strip_long_path_prefix(filepath)
    ftype = get_file_type(filepath)

    if ftype == '.zip':
        return _explode_zip(filepath, output_dir)
    elif ftype == '.eml':
        return _explode_eml(filepath, output_dir)
    elif ftype == '.pst':
        return explode_pst_isolated(filepath, output_dir, log_path=log_path)

    return [] # Not a container

try:
    import win32com.client
    import pythoncom
    _WIN32COM_AVAILABLE = True
except ImportError:
    _WIN32COM_AVAILABLE = False

# ── MAPI / Outlook Constants ──────────────────────────────────────────
MAPI_ATTACH_BY_VALUE = 1            # PR_ATTACH_METHOD: attachment data in PR_ATTACH_DATA_BIN
MAPI_ATTACH_EMBEDDED_MSG = 5        # PR_ATTACH_METHOD: attached message object
MAPI_ATTACH_OLE = 6                 # PR_ATTACH_METHOD: embedded OLE object
PR_ATTACH_FLAGS_INLINE = 0x04       # Bit flag: attachment is inline (rendered in body)
OL_MSG_FORMAT = 3                   # Outlook SaveAs format constant for .msg
OL_DISCARD = 1                      # Outlook OlInspectorClose: discard changes on close

# --- Cross-process COM serialization ---
# Two simultaneous Streamlit sessions must not access Outlook COM concurrently.
# A Windows named mutex ensures only one processing pipeline uses COM at a time.
# The mutex is system-wide (Global\ prefix) so it works across all processes.
_COM_MUTEX_NAME = "Global\\DIYeDiscovery_OutlookCOM"
_COM_MUTEX_TIMEOUT_MS = getattr(__import__('config'), 'COM_MUTEX_TIMEOUT_MS', 300000)  # configurable; default 5 minutes

def _acquire_com_mutex():
    """
    Acquire system-wide named mutex for exclusive Outlook COM access.
    Blocks until the mutex is available or timeout is reached.
    Returns the mutex handle (must be passed to _release_com_mutex).
    Raises TimeoutError if another session holds the lock too long.
    """
    if not _WIN32COM_AVAILABLE:
        return None
    try:
        import win32event
        import win32api
        mutex = win32event.CreateMutex(None, False, _COM_MUTEX_NAME)
        result = win32event.WaitForSingleObject(mutex, _COM_MUTEX_TIMEOUT_MS)
        if result in (win32event.WAIT_OBJECT_0, win32event.WAIT_ABANDONED):
            return mutex
        else:
            # Timeout — another session has held COM for too long
            try:
                win32api.CloseHandle(mutex)
            except Exception as e:
                logger.debug("CloseHandle on COM mutex failed: %s", e)
            raise TimeoutError(
                f"Timed out waiting for exclusive COM access after "
                f"{_COM_MUTEX_TIMEOUT_MS // 1000}s — another processing "
                f"session may be active"
            )
    except ImportError:
        logger.warning("win32event not available — COM mutex disabled")
        return None


def _release_com_mutex(mutex):
    """Release the system-wide COM mutex."""
    if mutex is None:
        return
    try:
        import win32event
        import win32api
        win32event.ReleaseMutex(mutex)
        win32api.CloseHandle(mutex)
    except Exception as e:
        logger.warning(f"Error releasing COM mutex: {e}")


def _explode_pst_com(filepath, output_dir):
    """
    Extract all messages from a PST file using Outlook COM.
    Each message is saved as a .msg file via SaveAs(..., olMSG=3).
    The .msg files flow into the existing MSG pipeline for attachment extraction.

    Called from explode_pst_isolated() in the main process. PST extraction
    is already serialized by the Processor loop — no mutex needed here.
    (The mutex protects process_msg_batch() for concurrent session safety.)

    Returns a dict matching the standard PST extraction format: {
        'children': [(filename, physical_path, logical_path), ...],
        'expected_count': int,
        'extracted_count': int,
        'failed_folders': [(folder_name, expected, actual), ...]
    }
    """
    import pythoncom
    import win32com.client

    pst_basename = os.path.basename(filepath)
    abs_path = os.path.abspath(_strip_long_path_prefix(filepath))
    extracted = []
    stats = {'expected': 0, 'extracted': 0, 'failed_folders': []}
    root_folder = None

    pythoncom.CoInitialize()
    try:
        outlook = win32com.client.Dispatch("Outlook.Application").GetNamespace("MAPI")

        # P1 Fix 4: Polling loop instead of fixed sleep after AddStore
        import time
        outlook.AddStore(abs_path)
        root_folder = None
        for _poll in range(10):
            try:
                _candidate = outlook.Folders.Item(outlook.Folders.Count)
                # Verify the folder is accessible (not just a COM stub)
                _ = _candidate.Folders.Count
                root_folder = _candidate
                break
            except Exception:
                time.sleep(1)
        if root_folder is None:
            raise RuntimeError(f"AddStore succeeded but folder not accessible after 10s for {pst_basename}")
        _walk_pst_folder_com(root_folder, output_dir, pst_basename, extracted, stats)
    except Exception as e:
        logger.error(f"PST COM extraction error for {pst_basename}: {e}")
        raise
    finally:
        # Aggressively release COM objects and unmount the PST store.
        # RemoveStore MUST run even if root_folder is None — AddStore may
        # have mounted the PST before the polling loop could grab a reference.
        # Without this, failed extractions leave zombie stores in Outlook.
        try:
            if root_folder is not None:
                outlook.RemoveStore(root_folder)
            else:
                # root_folder was never captured — try to find and remove the
                # store by scanning Outlook folders for our PST's filename.
                try:
                    for _fi in range(outlook.Folders.Count, 0, -1):
                        _f = outlook.Folders.Item(_fi)
                        try:
                            _store_path = getattr(_f.Store, 'FilePath', '') or ''
                        except Exception:
                            _store_path = ''
                        if _store_path and os.path.normcase(os.path.abspath(_store_path)) == os.path.normcase(abs_path):
                            outlook.RemoveStore(_f)
                            logger.info(f"Cleaned up orphaned PST store mount for {pst_basename}")
                            break
                except Exception:
                    pass  # Best-effort — Outlook may not be reachable at all
        except Exception as e:
            logger.error(f"RemoveStore cleanup error for {pst_basename}: {e}")
        root_folder = None
        try:
            # Release the MAPI namespace reference
            outlook = None
        except Exception as e:
            logger.debug("PST cleanup — outlook release failed: %s", e)
        try:
            pythoncom.CoUninitialize()
        except Exception as e:
            logger.warning("PST cleanup — CoUninitialize failed: %s", e)

    stats['extracted'] = len(extracted)

    if stats['failed_folders']:
        folder_detail = "; ".join(
            f"{name} ({actual}/{exp})" for name, exp, actual in stats['failed_folders']
        )
        logger.warning(
            f"PST COM partial extraction for {pst_basename}: "
            f"{stats['extracted']}/{stats['expected']} items. "
            f"Failed folders: {folder_detail}"
        )

    return {
        'children': extracted,
        'expected_count': stats['expected'],
        'extracted_count': stats['extracted'],
        'failed_folders': stats['failed_folders'],
        'child_warnings': {},
        'container_notes': None,
    }


def _walk_pst_folder_com(folder, output_dir, logical_prefix, extracted, stats):
    """
    Recursively walks an Outlook MAPI folder, saving each mail item as a .msg.
    Tracks expected vs actual extraction counts in the stats dict.
    Skips non-mail items silently (calendar, contacts, tasks, etc.).
    Skips non-essential system folders (Deleted Items, Calendar, etc.).
    """
    # Skip non-essential Outlook folders that contain no discoverable email.
    # These folders can have thousands of stubs (deleted items, sync metadata)
    # that bloat extraction time with zero useful output.
    _SKIP_FOLDERS = {
        'deleted items', 'trash',
        'sync issues', 'conflicts', 'local failures', 'server failures',
        'junk email', 'junk e-mail',
        'calendar', 'contacts', 'tasks', 'notes', 'journal',
        'conversation action settings',
        'quick step settings',
        'rss feeds', 'rss subscriptions',
    }
    if folder.Name.lower().strip() in _SKIP_FOLDERS:
        logger.debug(f"Skipping non-essential PST folder: {folder.Name}")
        return

    folder_name = re.sub(r'[\\/*?:"<>|]', "_", folder.Name)
    logical_folder = os.path.join(logical_prefix, folder_name)

    # Save messages in this folder
    folder_expected = 0
    folder_extracted = 0
    try:
        items = folder.Items
        folder_expected = items.Count
        stats['expected'] += folder_expected

        for i in range(1, items.Count + 1):
            item = None
            try:
                item = items.Item(i)
                # Skip non-mail items (calendar, contacts, tasks)
                if not hasattr(item, 'SaveAs'):
                    # Don't count non-mail items against expected
                    stats['expected'] -= 1
                    folder_expected -= 1
                    continue
                subject = getattr(item, 'Subject', None) or "No Subject"
                safe_subject = re.sub(r'[\\/*?:"<>|]', "_", subject)[:60]
                filename = f"{uuid.uuid4().hex[:6]}_{safe_subject}.msg"
                target_path = os.path.join(output_dir, filename)
                logical_path = os.path.join(logical_folder, f"{safe_subject}.msg")
                item.SaveAs(target_path, OL_MSG_FORMAT)
                # P0 Fix 3: Verify file was actually written
                if not os.path.exists(target_path):
                    logger.error(f"SaveAs claimed success but file not found: {target_path}")
                    continue
                extracted.append((f"{safe_subject}.msg", target_path, logical_path))
                folder_extracted += 1
            except Exception as e:
                logger.error(f"PST COM item error in {folder.Name} (item {i}): {e}")
            finally:
                if item is not None:
                    try:
                        del item
                    except Exception as e:
                        logger.debug("PST COM item cleanup failed: %s", e)
    except Exception as e:
        logger.error(f"PST COM folder items error in {folder.Name}: {e}")

    # Track folder-level partial extraction
    if folder_extracted < folder_expected and folder_expected > 0:
        stats['failed_folders'].append((folder_name, folder_expected, folder_extracted))

    # Recurse into subfolders
    try:
        for i in range(1, folder.Folders.Count + 1):
            try:
                subfolder = folder.Folders.Item(i)
                _walk_pst_folder_com(subfolder, output_dir, logical_folder, extracted, stats)
            except Exception as e:
                logger.error(f"PST COM subfolder error under {folder.Name}: {e}")
    except Exception as e:
        logger.error(f"PST COM subfolder enumeration error in {folder.Name}: {e}")


def process_msg_batch(filepaths, output_dir):
    results = {path: [] for path in filepaths}

    # Acquire system-wide lock before touching Outlook COM
    com_mutex = _acquire_com_mutex()

    # Initialize COM for the current thread
    pythoncom.CoInitialize()

    try:
        outlook = win32com.client.Dispatch("Outlook.Application").GetNamespace("MAPI")
        
        for path in filepaths:
            clean_path = _strip_long_path_prefix(path)
            container_basename = os.path.basename(clean_path)
            extracted_attachments = []
            msg = None
            temp_msg_path = None

            try:
                abs_path = os.path.abspath(clean_path)
                
                # Short-Path Proxy: evade Windows 260-char MAX_PATH limit for COM
                if len(abs_path) > 240:
                    temp_msg_path = os.path.join(tempfile.gettempdir(), f"{uuid.uuid4().hex[:8]}.msg")
                    # shutil.copy2 uses Win32 file APIs that respect MAX_PATH — use \\?\ prefix here
                    copy_src = '\\\\?\\' + abs_path if not abs_path.startswith('\\\\?\\') else abs_path
                    shutil.copy2(copy_src, temp_msg_path)
                    target_open_path = temp_msg_path
                else:
                    target_open_path = abs_path
                
                msg = outlook.OpenSharedItem(target_open_path)
                
                # 1-indexed attachments loop
                for i in range(1, msg.Attachments.Count + 1):
                    attachment = msg.Attachments.Item(i)
                    try:
                        orig_filename = attachment.FileName
                        if not orig_filename:
                            orig_filename = f"attachment_{i}.bin"

                        # Skip CID-referenced inline images — Outlook exposes these through
                        # msg.Attachments even though they are HTML-body embeds (signature
                        # icons, decorative images) and are NOT shown in the email's
                        # "Attachments:" header.  Equivalent to the EML Content-ID check.
                        # PR_ATTACH_FLAGS 0x37140003: bit 4 = ATT_MHTML_REF (inline CID embed).
                        try:
                            _pa = attachment.PropertyAccessor
                            _att_flags = _pa.GetProperty("http://schemas.microsoft.com/mapi/proptag/0x37140003")
                            if _att_flags & PR_ATTACH_FLAGS_INLINE:
                                logger.debug(f"Skipping inline CID image: {orig_filename} in {container_basename}")
                                continue
                        except Exception as e:
                            logger.debug("PropertyAccessor check failed for %s: %s", container_basename, e)

                        # Check for nested MSG (Type 5 = olEmbeddeditem)
                        if attachment.Type == 5 and not orig_filename.lower().endswith('.msg'):
                            orig_filename += ".msg"

                        # Sanitize
                        orig_filename = re.sub(r'[\\/*?:"<>|]', "", orig_filename)

                        # Prepend UUID to avoid sibling collisions
                        safe_filename = f"{uuid.uuid4().hex[:6]}_{orig_filename}"
                        target_path = os.path.join(output_dir, safe_filename)
                        logical_path = os.path.join(container_basename, orig_filename)

                        # Save the physical payload
                        attachment.SaveAsFile(target_path)
                        extracted_attachments.append((orig_filename, target_path, logical_path))
                    except Exception as att_err:
                        logger.error(f"Error extracting attachment {i} from {container_basename}: {att_err}")
                    finally:
                        del attachment
                        
                results[path] = extracted_attachments
                
            except Exception as e:
                logger.error(f"COM Error processing {container_basename}: {e}")
                results[path] = "ERROR"
            finally:
                if msg:
                    try:
                        msg.Close(OL_DISCARD)
                    except Exception as e:
                        logger.debug("MSG Close failed for %s: %s", container_basename, e)
                    del msg
                if temp_msg_path and os.path.exists(temp_msg_path):
                    try:
                        os.remove(temp_msg_path)
                    except Exception as e:
                        logger.debug("Could not remove temp MSG %s: %s", temp_msg_path, e)
                    
    except Exception as dispatch_err:
        logger.error(f"Failed to dispatch Outlook COM: {dispatch_err}")
        for path in filepaths:
            if not results[path]:
                results[path] = "ERROR"
    finally:
        pythoncom.CoUninitialize()
        _release_com_mutex(com_mutex)

    return results


def _pst_subprocess_worker(filepath, output_dir, result_queue, log_path=None):
    """
    Subprocess target: runs libpff PST extraction in an isolated Python process.

    This is the FALLBACK path — only used when Outlook COM is not available.
    Subprocess isolation prevents libpff's C-level state corruption from
    leaking between PST files.
    """
    import logging
    sub_logger = logging.getLogger("ProcessorLogger")
    sub_logger.setLevel(logging.INFO)
    if not sub_logger.handlers:
        if log_path:
            handler = logging.FileHandler(log_path)
        else:
            handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s'
        ))
        sub_logger.addHandler(handler)

    try:
        result = explode_pst_libpff(filepath, output_dir)
        result_queue.put(('OK', result))
    except Exception as e:
        result_queue.put(('ERROR', str(e)))


def _repair_pst_header_crc(filepath):
    """
    Validate and repair PST header CRC checksums.

    Some PST files are created or modified by non-Outlook tools (import
    utilities, recovery software, webmail exporters) that write valid data
    but leave the header CRC fields incorrect.  Outlook's COM API validates
    these CRCs on AddStore() and refuses to mount the file if they don't
    match.  This function recalculates them — the same first step that
    Microsoft's SCANPST.EXE performs.

    Per MS-PST spec (§2.2.2.6 HEADER):
    - dwCRCPartial (offset 4, 4 bytes): CRC32 of bytes 8–11
    - dwCRCFull    (offset 524, 4 bytes): CRC32 of bytes 8–523

    If either CRC is invalid, copies the PST to a temp directory, patches
    the two CRC fields, and returns the repaired path.  The original file
    is never modified.  If both CRCs are valid, returns the original path.

    Returns:
        tuple: (path_to_use, was_repaired: bool, repair_note: str or None)
    """
    PST_HEADER_SIZE = 564

    try:
        with open(filepath, 'rb') as f:
            header = f.read(PST_HEADER_SIZE)

        if len(header) < PST_HEADER_SIZE:
            return filepath, False, None

        # Verify this is actually a PST (magic = !BDN)
        if header[:4] != b'!BDN':
            return filepath, False, None

        # Compute expected CRCs
        stored_partial = struct.unpack_from('<I', header, 4)[0]
        stored_full = struct.unpack_from('<I', header, 524)[0]
        computed_partial = binascii.crc32(header[8:12]) & 0xFFFFFFFF
        computed_full = binascii.crc32(header[8:524]) & 0xFFFFFFFF

        partial_ok = (stored_partial == computed_partial)
        full_ok = (stored_full == computed_full)

        if partial_ok and full_ok:
            return filepath, False, None

        # CRC mismatch — repair a copy
        basename = os.path.basename(filepath)
        repair_dir = tempfile.mkdtemp(prefix="pst_crc_repair_")
        repaired_path = os.path.join(repair_dir, basename)
        shutil.copy2(filepath, repaired_path)

        with open(repaired_path, 'r+b') as f:
            # Patch dwCRCPartial at offset 4
            f.seek(4)
            f.write(struct.pack('<I', computed_partial))
            # Patch dwCRCFull at offset 524
            f.seek(524)
            f.write(struct.pack('<I', computed_full))

        mismatch_parts = []
        if not partial_ok:
            mismatch_parts.append(
                f"partial CRC 0x{stored_partial:08X}->0x{computed_partial:08X}"
            )
        if not full_ok:
            mismatch_parts.append(
                f"full CRC 0x{stored_full:08X}->0x{computed_full:08X}"
            )
        repair_note = (
            f"PST header CRC repair applied ({', '.join(mismatch_parts)}). "
            f"Original file unchanged; extraction used repaired copy."
        )
        logger.warning(f"PST CRC repair for {basename}: {', '.join(mismatch_parts)}")

        return repaired_path, True, repair_note

    except Exception as e:
        logger.error(f"PST CRC check failed for {os.path.basename(filepath)}: {e}")
        return filepath, False, None


def explode_pst_isolated(filepath, output_dir, timeout=300, log_path=None):
    """
    Extract a PST file using the best available backend.

    Strategy (libpff-primary):
    - libpff: Runs in an ISOLATED SUBPROCESS (primary). Headless C library —
      no UI, no RPC, no desktop session. Subprocess isolation prevents
      C-level state corruption between PST files. Corrupted attachment
      B-trees are handled gracefully with per-message extraction_notes.
    - COM (Outlook): Runs in the MAIN PROCESS (fallback). Only used when
      libpff fails (timeout, crash, or extraction error). Requires Outlook
      running in the desktop session — can show blocking modal dialogs.

    Args:
        filepath: Path to the PST file
        output_dir: Directory to write extracted files (.eml for libpff, .msg for COM)
        timeout: Maximum seconds for libpff subprocess (default 300s)
        log_path: Optional log path for libpff subprocess logging

    Returns:
        dict: {
            'children': [(filename, physical_path, logical_path), ...],
            'expected_count': int,
            'extracted_count': int,
            'failed_folders': [(folder_name, expected, actual), ...],
            'child_warnings': {logical_path: str, ...},  -- per-child extraction warnings
            'container_notes': str or None  -- container-level extraction summary
        }
    Raises RuntimeError on failure.
    """
    pst_basename = os.path.basename(filepath)

    # --- Primary: libpff in isolated subprocess (with retry) ---
    # libpff is a headless C library — no UI, no RPC, no desktop session required.
    # Subprocess isolation prevents C-level state corruption between PST files.
    # Corrupted attachment B-trees are handled gracefully with per-message warnings.
    #
    # Uses subprocess.Popen with a dedicated worker script (_pst_worker.py) instead
    # of multiprocessing.Process. On Windows, multiprocessing.spawn re-imports the
    # main module (home.py), which partially initializes Streamlit in the subprocess
    # and causes libpff's C library to hang.
    import subprocess as _sp
    import json as _json

    _worker_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), '_pst_worker.py')
    _libpff_failed = False

    for _libpff_attempt, _libpff_timeout in [(1, timeout), (2, timeout * 2)]:
        logger.info(
            f"PST extraction via libpff (subprocess) for {pst_basename}"
            + (f" (retry, timeout={_libpff_timeout}s)" if _libpff_attempt > 1 else "")
        )

        _result_json = tempfile.mktemp(suffix='.json', prefix='pst_result_')
        _cmd = [sys.executable, _worker_script, filepath, output_dir, _result_json]
        if log_path:
            _cmd.append(log_path)

        try:
            p = _sp.Popen(_cmd)
            p.wait(timeout=_libpff_timeout)
        except _sp.TimeoutExpired:
            logger.error(
                f"PST extraction timeout for {pst_basename} after {_libpff_timeout}s. "
                f"Terminating subprocess."
            )
            p.kill()
            p.wait(5)
            if _libpff_attempt < 2:
                logger.info(f"Retrying libpff with extended timeout ({timeout * 2}s)...")
                continue
            _libpff_failed = True
            logger.warning(
                f"libpff timed out for {pst_basename} after {_libpff_timeout}s "
                f"— falling back to COM"
            )
            break

        if p.returncode != 0 or not os.path.exists(_result_json):
            if _libpff_attempt < 2:
                logger.warning(
                    f"libpff subprocess failed (exit code {p.returncode}), retrying..."
                )
                continue
            _libpff_failed = True
            logger.warning(
                f"libpff subprocess failed for {pst_basename} "
                f"(exit code {p.returncode}) — falling back to COM"
            )
            break

        # Read result from JSON file
        try:
            with open(_result_json, 'r', encoding='utf-8') as _rf:
                _result_data = _json.load(_rf)
        except Exception as e:
            if _libpff_attempt < 2:
                logger.warning(f"Could not read libpff result JSON: {e}, retrying...")
                continue
            _libpff_failed = True
            logger.warning(
                f"Could not read libpff result for {pst_basename}: {e} "
                f"— falling back to COM"
            )
            break
        finally:
            try:
                os.unlink(_result_json)
            except OSError:
                pass

        if _result_data.get('status') == 'OK':
            payload = _result_data['payload']
            logger.info(
                f"PST libpff extraction complete for {pst_basename}: "
                f"{payload['extracted_count']}/{payload['expected_count']} items"
            )
            payload.setdefault('child_warnings', {})
            payload.setdefault('container_notes', None)
            return payload
        else:
            if _libpff_attempt < 2:
                logger.warning(
                    f"libpff returned error for {pst_basename}: "
                    f"{_result_data.get('payload')}, retrying..."
                )
                continue
            _libpff_failed = True
            logger.warning(
                f"libpff extraction returned error for {pst_basename}: "
                f"{_result_data.get('payload')} — falling back to COM"
            )
            break

    # --- Fallback: COM in the main process (with retry) ---
    # COM requires Outlook running in the desktop session. It can show modal
    # dialogs that block programmatic access. Only used when libpff fails.
    if _WIN32COM_AVAILABLE:
        import time as _time
        for _attempt in range(1, 3):  # Up to 2 attempts
            try:
                logger.info(
                    f"PST extraction via COM (fallback) for {pst_basename}"
                    + (f" (retry {_attempt})" if _attempt > 1 else "")
                )
                result = _explode_pst_com(filepath, output_dir)
                # Check for empty extraction
                if (isinstance(result, dict)
                        and result.get('expected_count', 0) > 0
                        and result.get('extracted_count', 0) == 0):
                    logger.warning(
                        f"COM returned 0 items for {pst_basename} "
                        f"(expected {result['expected_count']})"
                    )
                    break
                _time.sleep(3)
                result.setdefault('child_warnings', {})
                result.setdefault('container_notes', None)
                return result
            except Exception as e:
                logger.warning(
                    f"COM attempt {_attempt} failed for {pst_basename}: {e}"
                )
                if _attempt < 2:
                    logger.info("Waiting 5s for Outlook to recover before retry...")
                    _time.sleep(5)
                else:
                    logger.warning(
                        f"COM extraction also failed for {pst_basename} after "
                        f"{_attempt} attempts"
                    )

    # Both backends failed
    raise RuntimeError(
        f"PST extraction failed for '{pst_basename}': "
        f"libpff and COM both unsuccessful"
    )


def explode_pst_libpff(filepath, output_dir):
    """
    Fallback PST extraction using libpff-python (pypff).
    Used when Outlook COM is not available on the machine.
    Each message is written as a .eml file and flows into the existing
    EML attachment-extraction pipeline.

    Returns a dict: {
        'children': [(filename, physical_path, logical_path), ...],
        'expected_count': int,
        'extracted_count': int,
        'failed_folders': [(folder_name, expected, actual), ...]
    }
    Raises RuntimeError if pypff is not installed or extraction fails entirely.
    """
    try:
        import pypff
    except ImportError:
        raise RuntimeError(
            f"PST extraction requires libpff-python. Run: pip install libpff-python"
        )

    pst_basename = os.path.basename(filepath)
    clean_path = _strip_long_path_prefix(filepath)
    extracted = []
    stats = {'expected': 0, 'extracted': 0, 'failed_folders': []}

    pst_file = pypff.file()
    try:
        pst_file.open(clean_path)
        root = pst_file.get_root_folder()
        _walk_pst_folder_libpff(root, output_dir, pst_basename, extracted, stats)
    except Exception as e:
        raise RuntimeError(f"PST extraction failed for '{pst_basename}': {e}") from e
    finally:
        try:
            pst_file.close()
        except Exception as e:
            logger.warning(f"Error closing PST file '{pst_basename}': {e}")

    stats['extracted'] = len(extracted)

    if stats['failed_folders']:
        folder_detail = "; ".join(
            f"{name} ({actual}/{exp})" for name, exp, actual in stats['failed_folders']
        )
        logger.warning(
            f"PST partial extraction for {pst_basename}: "
            f"{stats['extracted']}/{stats['expected']} items extracted. "
            f"Failed folders: {folder_detail}"
        )

    child_warnings = stats.get('child_warnings', {})
    n_warned = len(child_warnings)
    container_notes = None
    if n_warned:
        container_notes = (
            f"{n_warned} of {stats['extracted']} messages had corrupted attachment "
            f"B-trees in the source PST — attachments omitted for those messages "
            f"(see child document extraction_notes)."
        )

    return {
        'children': extracted,
        'expected_count': stats['expected'],
        'extracted_count': stats['extracted'],
        'failed_folders': stats['failed_folders'],
        'child_warnings': child_warnings,
        'container_notes': container_notes,
    }


def _walk_pst_folder_libpff(folder, output_dir, logical_prefix, extracted, stats):
    """
    Recursively walks a pypff folder, writing each message as a .eml file.
    Tracks expected vs actual extraction counts in the stats dict.
    Per-message warnings (e.g. corrupted attachments) are collected in
    stats['child_warnings'] keyed by logical_path.
    """
    folder_name = re.sub(r'[\\/*?:"<>|]', "_", folder.name or "folder")
    logical_folder = os.path.join(logical_prefix, folder_name)

    # Save messages in this folder
    num_messages = getattr(folder, 'number_of_sub_messages', None)
    if num_messages is None:
        num_messages = getattr(folder, 'number_of_messages', 0)
    get_message = getattr(folder, 'get_sub_message', None) or getattr(folder, 'get_message', None)

    stats['expected'] += num_messages
    stats.setdefault('child_warnings', {})
    folder_extracted = 0

    if get_message:
        for i in range(num_messages):
            try:
                msg = get_message(i)
                eml_bytes, msg_warning = _libpff_message_to_eml(msg)
                subject = (getattr(msg, 'subject', None) or 'No Subject').strip()
                safe_subject = re.sub(r'[\\/*?:"<>|]', '_', subject)[:60]
                filename = f"{uuid.uuid4().hex[:6]}_{safe_subject}.eml"
                target_path = os.path.join(output_dir, filename)
                logical_path = os.path.join(logical_folder, f"{safe_subject}.eml")
                with open(target_path, 'wb') as f:
                    f.write(eml_bytes)
                # P0 Fix 3: Verify file was actually written
                if not os.path.exists(target_path) or os.path.getsize(target_path) == 0:
                    logger.error(f"EML write produced empty/missing file: {target_path}")
                    continue
                extracted.append((f"{safe_subject}.eml", target_path, logical_path))
                folder_extracted += 1
                # Collect per-message warning for DB persistence
                if msg_warning:
                    stats['child_warnings'][logical_path] = msg_warning
            except Exception as e:
                logger.error(f"libpff message error in folder '{folder.name}' (index {i}): {e}")

    # Track folder-level partial extraction
    if folder_extracted < num_messages and num_messages > 0:
        stats['failed_folders'].append((folder_name, num_messages, folder_extracted))

    # Recurse into sub-folders
    num_folders = getattr(folder, 'number_of_sub_folders', 0)
    for i in range(num_folders):
        try:
            subfolder = folder.get_sub_folder(i)
            _walk_pst_folder_libpff(subfolder, output_dir, logical_folder, extracted, stats)
        except Exception as e:
            logger.error(f"libpff subfolder error under '{folder.name}' (index {i}): {e}")


def _build_eml_headers(msg, num_att):
    """
    Parse transport headers and MAPI properties from a pypff message to build
    the root MIMEMultipart envelope with From/To/Cc/Date/Subject headers.

    Returns (root: MIMEMultipart, msg_id: str) where msg_id is the pypff
    message identifier (used for synthetic CID generation).
    """
    from email.mime.multipart import MIMEMultipart

    subject = (getattr(msg, 'subject', None) or '').strip()
    msg_id = str(getattr(msg, 'identifier', 'unknown'))

    # --- Parse transport headers for reliable email metadata ---
    # transport_headers contains the raw RFC 2822 headers and is the most
    # reliable source for addresses and threading info.
    from_header = msg.sender_name or 'Unknown Sender'
    to_addrs = ''
    cc_addrs = ''
    date_header = None

    _transport = getattr(msg, 'transport_headers', None)
    if _transport:
        try:
            _parsed_hdrs = email.message_from_string(_transport, policy=policy.default)
            _from_hdr = _parsed_hdrs.get('From')
            if _from_hdr:
                from_header = str(_from_hdr)
            to_addrs = str(_parsed_hdrs.get('To') or '')
            cc_addrs = str(_parsed_hdrs.get('Cc') or '')
            date_header = str(_parsed_hdrs.get('Date') or '')
        except Exception as e:
            logger.debug("Transport header parsing failed, using fallbacks: %s", e)

    # Fallback: if transport_headers didn't provide a From with an email address,
    # try the MAPI record set for the sender email
    if '@' not in from_header:
        sender_email = _get_record_string(msg, 0x0C1F)  # PR_SENDER_EMAIL_ADDRESS
        if sender_email and '@' in sender_email:
            from_header = f'"{msg.sender_name}" <{sender_email}>' if msg.sender_name else sender_email

    # Fallback: construct Date header from pypff datetime attributes
    if not date_header:
        _send_dt = getattr(msg, 'client_submit_time', None) or getattr(msg, 'delivery_time', None)
        if _send_dt:
            from email.utils import format_datetime
            try:
                date_header = format_datetime(_send_dt)
            except Exception:
                date_header = _send_dt.strftime('%a, %d %b %Y %H:%M:%S +0000')

    # Choose multipart type based on content
    html_body_bytes = getattr(msg, 'html_body', None)
    if num_att > 0:
        root = MIMEMultipart('mixed')
    elif html_body_bytes:
        root = MIMEMultipart('alternative')
    else:
        root = MIMEMultipart('mixed')

    root['Subject'] = subject
    root['From'] = from_header
    if to_addrs:
        root['To'] = to_addrs
    if cc_addrs:
        root['Cc'] = cc_addrs
    if date_header:
        root['Date'] = date_header

    return root, msg_id


def _attach_eml_bodies(root, msg):
    """
    Attach plain-text and HTML body parts to the root MIMEMultipart envelope.
    Mutates root in place.
    """
    from email.mime.text import MIMEText

    plain_body_bytes = getattr(msg, 'plain_text_body', None)
    html_body_bytes = getattr(msg, 'html_body', None)

    if plain_body_bytes:
        try:
            root.attach(MIMEText(plain_body_bytes.decode('utf-8', errors='replace'), 'plain', 'utf-8'))
        except Exception as e:
            logger.warning("Failed to attach plain-text body to synthesized EML: %s", e)
    if html_body_bytes:
        try:
            root.attach(MIMEText(html_body_bytes.decode('utf-8', errors='replace'), 'html', 'utf-8'))
        except Exception as e:
            logger.warning("Failed to attach HTML body to synthesized EML: %s", e)


def _attach_eml_attachment(root, att, index, msg_id):
    """
    Process a single pypff attachment and attach it to the root MIMEMultipart.
    Handles filename resolution, Content-Type detection, CID/inline detection,
    embedded message recursion, and regular binary attachments.
    Mutates root in place.
    """
    from email.mime.base import MIMEBase
    from email import encoders as _enc

    # MAPI property tags for attachments (see docs/references/LIBPFF_API_REFERENCE.md)
    _TAG_LONG_FILENAME  = 0x3707  # PR_ATTACH_LONG_FILENAME
    _TAG_SHORT_FILENAME = 0x3704  # PR_ATTACH_FILENAME
    _TAG_MIME_TAG       = 0x370E  # PR_ATTACH_MIME_TAG
    _TAG_CONTENT_ID     = 0x3712  # PR_ATTACH_CONTENT_ID
    _TAG_ATTACH_FLAGS   = 0x3714  # PR_ATTACH_FLAGS
    _TAG_ATTACH_METHOD  = 0x3705  # PR_ATTACH_METHOD (1=by_value, 5=embedded_msg, 6=OLE)

    # --- Filename resolution via MAPI record sets ---
    att_name = (
        # P2 Fix 7: Correct fallback order (removed PR_DISPLAY_NAME — not an attachment property)
        _get_record_string(att, _TAG_LONG_FILENAME)
        or _get_record_string(att, _TAG_SHORT_FILENAME)
        or f'attachment_{index}.bin'
    )
    att_name = re.sub(r'[\\/*?:"<>|]', '_', att_name)

    # --- Content-Type resolution ---
    att_content_type = _get_record_string(att, _TAG_MIME_TAG)
    if not att_content_type or att_content_type == 'application/octet-stream':
        guessed, _ = mimetypes.guess_type(att_name, strict=False)
        if guessed:
            att_content_type = guessed
    if att_content_type and '/' in att_content_type:
        _main, _sub = att_content_type.split('/', 1)
    else:
        _main, _sub = 'application', 'octet-stream'

    # --- CID / inline detection ---
    att_cid = _get_record_string(att, _TAG_CONTENT_ID)
    att_flags = _get_record_integer(att, _TAG_ATTACH_FLAGS) or 0

    # Generate synthetic CID for inline-flagged attachments that lack one.
    # PR_ATTACH_FLAGS bit 2 (ATT_MHTML_REF) indicates an inline embed.
    # Without a Content-ID header, the exploder won't skip these images.
    if not att_cid and (att_flags & 4):
        att_cid = f'inline-{index}-{msg_id}'
        logger.debug(f"Generated synthetic CID for inline attachment {index}: {att_cid}")

    # --- Check attachment method ---
    att_method = _get_record_integer(att, _TAG_ATTACH_METHOD)

    if att_method == MAPI_ATTACH_EMBEDDED_MSG:
        # ── Embedded MAPI message (forwarded email) ──
        # The attachment is a structured sub-message, not a binary blob.
        # read_buffer() does not work for these — use get_sub_item().
        num_sub = getattr(att, 'number_of_sub_items', 0)
        if num_sub > 0:
            try:
                embedded_msg = att.get_sub_item(0)
                embedded_eml_bytes, _embedded_warn = _libpff_message_to_eml(embedded_msg)

                # Wrap in a message/rfc822 MIME part
                from email.mime.message import MIMEMessage
                nested_parsed = email.message_from_bytes(
                    embedded_eml_bytes, policy=policy.default
                )
                part = MIMEMessage(nested_parsed)
                part.add_header(
                    'Content-Disposition', 'attachment', filename=att_name
                )
            except Exception as e:
                logger.error(
                    f"libpff embedded message error (index {index}): {e}"
                )
                return
        else:
            logger.warning(
                f"libpff attachment {index} is embedded msg but has no sub_items"
            )
            return
    else:
        # ── Regular binary attachment (file) ──
        att_size = getattr(att, 'size', 0)
        att_data = b''
        if att_size > 0:
            try:
                att_data = att.read_buffer(att_size)
            except Exception as e:
                logger.debug("read_buffer failed for attachment %s (%s), trying file_object: %s", index, att_name, e)
                try:
                    _fo = att.get_data_as_file_object()
                    try:
                        att_data = _fo.read()
                    finally:
                        _fo.close()
                except Exception as e2:
                    logger.warning("All attachment data methods failed for attachment %s (%s): %s", index, att_name, e2)

        if not att_data and not att_cid:
            # Empty payload and not an inline image — skip silently
            logger.debug(
                f"Skipping empty attachment {index} ({att_name})"
            )
            return

        part = MIMEBase(_main, _sub)
        part.set_payload(att_data)
        _enc.encode_base64(part)
        part.add_header(
            'Content-Disposition', 'attachment', filename=att_name
        )

        # Preserve CID reference so downstream consumers can detect inline images
        if att_cid:
            part['Content-ID'] = f'<{att_cid}>'

    root.attach(part)


def _libpff_message_to_eml(msg):
    """
    Build a RFC-compliant .eml bytes object from a pypff message.
    Uses HTML body when available, plain text as fallback.
    Attaches any embedded files as MIME parts.

    Returns:
        tuple: (eml_bytes, warning_str_or_None)
            warning is set when extraction was degraded (e.g. attachments
            lost to PST corruption). This becomes the document's
            extraction_notes for defensible audit trail.
    """
    subject = (getattr(msg, 'subject', None) or '').strip()
    warning = None

    # Guard against corrupted local descriptors in PST files.
    # number_of_attachments is a C-backed property that can throw IOError/RuntimeError
    # if the PST's internal B-tree index is damaged. getattr() only catches
    # AttributeError, so we need an explicit try/except.
    # When this fails, we still extract the message (body + headers) — just without
    # attachments. This is far better than losing the entire message.
    try:
        num_att = msg.number_of_attachments
    except Exception as e:
        logger.warning(
            f"Could not read attachment count for message "
            f"'{subject}' (id={getattr(msg, 'identifier', 'unknown')}): {e} "
            f"— extracting message without attachments"
        )
        num_att = 0
        warning = (
            "Attachments unavailable: corrupted local descriptor B-tree in "
            "source PST (libpff extraction). Message body and headers extracted "
            "successfully; original attachment count unknown."
        )

    root, msg_id = _build_eml_headers(msg, num_att)
    _attach_eml_bodies(root, msg)

    for i in range(num_att):
        try:
            att = msg.get_attachment(i)
            _attach_eml_attachment(root, att, i, msg_id)
        except Exception as e:
            logger.warning("Attachment %d failed in libpff EML build: %s", i, e)

    return root.as_bytes(), warning


def _explode_zip(filepath, output_dir):
    """
    Extracts contents of a zip file.
    Returns: A list of (filename, physical_path, logical_path) tuples.
    """
    extracted = []
    container_basename = os.path.basename(filepath)
    try:
        with zipfile.ZipFile(filepath, 'r') as zf:
            for member in zf.namelist():
                if member.endswith('/'): continue
                
                with zf.open(member) as source:
                    clean_name = os.path.basename(member)
                    logical_path = os.path.join(container_basename, member)

                    # Prepend UUID to avoid sibling collisions in parallel processing
                    safe_filename = f"{uuid.uuid4().hex[:6]}_{clean_name}"
                    target_path = os.path.join(output_dir, safe_filename)

                    with open(target_path, "wb") as target:
                        shutil.copyfileobj(source, target)

                extracted.append((clean_name, target_path, logical_path))
    except Exception as e:
        logger.error(f"Zip Error {filepath}: {e}")
    return extracted

def _guess_ext_from_magic(payload):
    """
    Guess file extension from magic bytes when MIME headers provide no useful name.
    Returns an extension string (e.g. '.pdf') or None if unrecognized.
    """
    if not payload or len(payload) < 8:
        return None
    head = payload[:8]
    if head[:4] == b'%PDF':
        return '.pdf'
    if head[:3] == b'\xff\xd8\xff':
        return '.jpg'
    if head[:4] == b'\x89PNG':
        return '.png'
    if head[:4] == b'GIF8':
        return '.gif'
    if head[:4] == b'PK\x03\x04':
        # PK signature: ZIP archive — could be .docx, .xlsx, .pptx, or plain .zip.
        # Peek inside for Office markers.
        if b'word/' in payload[:2000]:
            return '.docx'
        if b'xl/' in payload[:2000]:
            return '.xlsx'
        if b'ppt/' in payload[:2000]:
            return '.pptx'
        return '.zip'
    if head[:4] == b'\xd0\xcf\x11\xe0':
        # OLE2 Compound Document — .doc, .xls, .ppt, or .msg
        # Without deeper parsing, .doc is the safest common guess
        return '.doc'
    if head[:5] == b'{\\rtf':
        return '.rtf'
    if head[:4] == b'RIFF':
        return '.wav'
    if head[:2] == b'BM':
        return '.bmp'
    if head[:4] == b'\x00\x00\x01\x00':
        return '.ico'
    # TIFF (little-endian and big-endian)
    if head[:4] in (b'II\x2a\x00', b'MM\x00\x2a'):
        return '.tiff'
    # HTML documents — commonly email signature blocks or body fragments
    # when wrapped by libpff as application/octet-stream
    if head[:6] == b'<html>' or head[:6] == b'<HTML>' or head[:5] == b'<!DOC' or head[:5] == b'<!doc':
        return '.html'
    return None


def _walk_mime_parts(msg):
    """
    Walk MIME parts like msg.walk(), but stop descent into message/rfc822 parts.

    message/rfc822 parts represent nested emails. They must be extracted as
    whole containers (saved as .eml files) and re-processed by the pipeline,
    NOT unpacked at this level. If walk() descends into them, their internal
    attachments appear as children of the outer email — causing duplicates
    when the .eml later re-enters the pipeline.
    """
    yield msg
    if msg.is_multipart():
        for part in msg.iter_parts():
            if part.get_content_type() == 'message/rfc822':
                yield part  # Yield the message/rfc822 part but do NOT descend
            elif part.is_multipart():
                yield from _walk_mime_parts(part)  # Recurse into multipart
            else:
                yield part


def _collect_html_inline_refs(msg):
    """Scan an email's HTML body for inline references (filenames + CIDs).

    Returns an HtmlInlineRefs NamedTuple with:
      - filenames: set of lowercase filenames referenced via <img src="...">
                   (catches inline signature images embedded by filename
                   reference rather than CID — typical of non-Outlook clients
                   that didn't set PR_ATTACH_CONTENT_ID or PR_ATTACH_FLAGS).
      - cids: set of CIDs (no angle brackets) referenced via <img src="cid:...">
              (defines which Content-ID'd parts are truly inline; used to
              distinguish real inline images from libpff-stamped attachments).

    Both fields are consumed by is_part_inline_image() to classify each
    MIME part as inline-or-attachment. See docs/lessons/extraction-rendering-symmetry.md.
    """
    filenames = set()
    cids = set()
    html_body = None

    # Find the HTML body part (first text/html without attachment disposition)
    for part in msg.walk():
        if part.get_content_type() == 'text/html' and part.get_content_disposition() != 'attachment':
            try:
                html_body = part.get_content()
            except Exception:
                try:
                    payload = part.get_payload(decode=True)
                    if payload:
                        html_body = payload.decode('utf-8', errors='replace')
                except Exception:
                    pass
            break

    if not html_body:
        return HtmlInlineRefs(filenames=filenames, cids=cids)

    # Extract refs from <img src="..."> tags.
    import urllib.parse
    for match in re.finditer(r'<img[^>]+src=["\']([^"\']+)["\']', html_body, re.IGNORECASE):
        src = match.group(1)
        if src.startswith('data:'):
            continue  # Base64 data URIs are already embedded
        if src.lower().startswith('cid:'):
            # CID reference — collect the CID identifier (strip the cid: prefix
            # and any angle brackets to match part.get('Content-ID').strip('<>')).
            cid_val = src[4:].strip('<>')
            if cid_val:
                cids.add(cid_val)
            continue
        # Filename reference — extract just the filename from paths/URLs
        # e.g. "images/logo.png" -> "logo.png", "http://example.com/img.jpg" -> "img.jpg"
        filename = urllib.parse.unquote(src.split('/')[-1].split('?')[0].split('#')[0])
        if filename:
            filenames.add(filename.lower())

    return HtmlInlineRefs(filenames=filenames, cids=cids)


def _explode_eml(filepath, output_dir):
    """
    Extracts attachments from an EML file.
    Returns: A list of (filename, physical_path, logical_path) tuples.
    """
    extracted = []
    container_basename = os.path.basename(filepath)
    try:
        with open(filepath, 'rb') as f:
            msg = email.message_from_binary_file(f, policy=policy.default)
            
        # Pre-scan HTML body for inline references (both CIDs and filenames).
        # The shared is_part_inline_image() predicate uses both sets to
        # classify each MIME part as truly-inline vs. real-attachment.
        refs = _collect_html_inline_refs(msg)

        counter = 0
        for part in _walk_mime_parts(msg):
            if part.get_content_maintype() == 'multipart': continue
            if part.get_content_disposition() is None and part.get_content_type() != 'message/rfc822': continue
            # Skip parts that are truly inline (image AND actually referenced
            # from the HTML body via CID or filename). Pre-Commit-5 this branch
            # used `part.get('Content-ID')` alone, which over-skipped every
            # libpff-extracted PST attachment (libpff stamps Content-ID on
            # every attachment regardless of whether it's inline). See
            # docs/lessons/extraction-rendering-symmetry.md.
            if is_part_inline_image(part, refs.cids, refs.filenames): continue
            # Skip text/html attachment parts — these are signature blocks or formatted
            # body fragments (common in Apple Mail) that are baked into the parent email
            # PDF by universal_imager rather than extracted as standalone child documents.
            if part.get_content_type() == 'text/html': continue

            # --- Handle nested email messages (message/rfc822) ---
            # These are forwarded-as-attachment emails. Save the entire nested
            # message as a .eml file so it re-enters the pipeline as a container.
            if part.get_content_type() == 'message/rfc822':
                try:
                    nested_payload = part.get_payload()
                    if isinstance(nested_payload, list) and len(nested_payload) > 0:
                        nested_msg = nested_payload[0]
                    elif hasattr(nested_payload, 'as_bytes'):
                        nested_msg = nested_payload
                    else:
                        logger.warning(
                            f"Unexpected message/rfc822 payload type in {container_basename}: "
                            f"{type(nested_payload)}"
                        )
                        counter += 1
                        continue

                    # Use nested message's subject for the filename
                    nested_subject = nested_msg.get('Subject', 'Forwarded Message') or 'Forwarded Message'
                    safe_nested_subject = re.sub(r'[\\/*?:"<>|]', '_', nested_subject)[:60]
                    nested_filename = f"{safe_nested_subject}.eml"
                    safe_nested_filename = f"{uuid.uuid4().hex[:6]}_{nested_filename}"
                    nested_target = os.path.join(output_dir, safe_nested_filename)
                    nested_logical = os.path.join(container_basename, nested_filename)

                    eml_bytes = nested_msg.as_bytes()
                    with open(nested_target, 'wb') as nf:
                        nf.write(eml_bytes)

                    extracted.append((nested_filename, nested_target, nested_logical))
                    counter += 1
                except Exception as e:
                    logger.error(f"Nested message extraction error in {container_basename}: {e}")
                    counter += 1
                continue

            # --- Filename inference (multi-strategy fallback) ---
            filename = part.get_filename()

            if not filename:
                # Strategy 2: Content-Type 'name' parameter
                #   Some clients put the filename here instead of Content-Disposition
                filename = part.get_param('name')

            if not filename:
                # Strategy 3: Infer extension from MIME type
                #   e.g. application/pdf → .pdf, image/jpeg → .jpg
                content_type = part.get_content_type()
                guessed_ext = mimetypes.guess_extension(content_type, strict=False) if content_type else None
                # mimetypes can return oddities like .ksh for text/plain — guard against that
                if guessed_ext and guessed_ext not in ('.ksh', '.bat', '.com'):
                    filename = f"attachment_{counter}{guessed_ext}"
                else:
                    filename = f"attachment_{counter}.bin"

            # Strategy 4: If extension is still .bin, try to improve it.
            # This catches cases where get_filename() returned a name like
            # "attachment_0.bin" (truthy but unhelpful) or where the MIME
            # Content-Type was application/octet-stream.
            _base, _ext = os.path.splitext(filename)
            if _ext.lower() == '.bin':
                # 4a: Check Content-Type for a more specific MIME type
                content_type = part.get_content_type()
                if content_type and content_type != 'application/octet-stream':
                    ct_ext = mimetypes.guess_extension(content_type, strict=False)
                    if ct_ext and ct_ext not in ('.ksh', '.bat', '.com', '.bin'):
                        filename = f"{_base}{ct_ext}"
                        _ext = ct_ext  # update so 4b doesn't re-check

                # 4b: If still .bin, inspect payload magic bytes
                if _ext.lower() == '.bin':
                    peek_payload = part.get_payload(decode=True)
                    if peek_payload:
                        magic_ext = _guess_ext_from_magic(peek_payload)
                        if magic_ext:
                            filename = f"{_base}{magic_ext}"

            # --- Post-detection HTML skip ---
            # The native-EML path (above) skips text/html parts because they are
            # body fragments / signature blocks baked into the parent PDF by
            # universal_imager.  When EMLs come through the libpff converter,
            # Content-Type is masked as application/octet-stream, so that filter
            # doesn't fire.  Now that magic-byte detection has resolved the true
            # extension, apply the same skip logic for consistency.
            _resolved_ext = os.path.splitext(filename)[1].lower()
            if _resolved_ext in ('.html', '.htm'):
                logger.debug(f"Skipping HTML body fragment (detected via magic bytes): {filename} in {container_basename}")
                counter += 1
                continue

            payload = part.get_payload(decode=True)
            if not payload: continue
            
            logical_path = os.path.join(container_basename, filename)
            
            # Prepend UUID to avoid sibling collisions in parallel processing
            safe_filename = f"{uuid.uuid4().hex[:6]}_{filename}"
            target_path = os.path.join(output_dir, safe_filename)
                
            with open(target_path, 'wb') as f:
                f.write(payload)
                
            extracted.append((filename, target_path, logical_path))
            counter += 1
    except Exception as e:
        logger.error(f"EML Error {filepath}: {e}")
    return extracted
