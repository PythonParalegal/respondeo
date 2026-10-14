# ─── MODULE METADATA ────────────────────────────────────────────────────────
# module:        email_imager.py
# version:       1.0.1
# project:       Respondeo eDiscovery Platform
# project_ver:   2.9.0
# last_modified: 2026-03-24 14:00
# modified_by:   claude-code
# last_commit:   pending
# ─────────────────────────────────────────────────────────────────────────────
import logging
import pythoncom
import win32com.client
from pathlib import Path

logger = logging.getLogger(__name__)

def convert_msg_to_pdf(msg_path, output_pdf_path):
    """
    Uses local Outlook installation to open an MSG and print it to PDF.
    Returns True if successful, False otherwise.
    """
    outlook = None
    msg = None
    msg_path = str(Path(msg_path).resolve())
    output_pdf_path = str(Path(output_pdf_path).resolve())

    try:
        pythoncom.CoInitialize()
        outlook = win32com.client.Dispatch("Outlook.Application")
        ns = outlook.GetNamespace("MAPI")
        msg = ns.OpenSharedItem(msg_path)
        
        inspector = msg.GetInspector
        word_doc = inspector.WordEditor
        word_doc.ExportAsFixedFormat(
            OutputFileName=output_pdf_path,
            ExportFormat=17, # PDF
            OpenAfterExport=False,
            OptimizeFor=0,
            Item=0,
            IncludeDocProps=True,
            KeepIRM=True,
            CreateBookmarks=1,
            DocStructureTags=True,
            BitmapMissingFonts=True,
            UseISO19005_1=False
        )
        return True
    except Exception as e:
        logger.warning("Error converting MSG to PDF %s: %s", msg_path, e)
        return False
    finally:
        if msg:
            try: msg.Close(0)
            except Exception as e:
                logger.debug("MSG Close error for %s: %s", msg_path, e)
        try: pythoncom.CoUninitialize()
        except Exception as e:
            logger.debug("CoUninitialize error: %s", e)
