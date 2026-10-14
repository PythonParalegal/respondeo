# Centralized Configuration for Respondeo eDiscovery Platform
# OpenSearch runs locally without authentication (plugins.security.disabled: true).
#
# ┌─────────────────────────────────────────────────────────────────────┐
# │  Copy this file to 'config.py' and update the paths for your      │
# │  machine.  config.py is gitignored — your local paths stay local. │
# └─────────────────────────────────────────────────────────────────────┘

__version__ = "2.16.0"
__branch__ = "beta-2.12"

TIKA_ENDPOINT = "http://localhost:9998/tika"
TIKA_TIMEOUT = 1800

# OpenSearch connection
OS_HOST = "http://localhost:9200"

# --- Machine-Specific Service Paths ---
# Update these to match where Tika and OpenSearch are installed on YOUR machine.
TIKA_JAR = r"C:\Tools\tika\tika-server-standard-3.2.3.jar"
OPENSEARCH_HOME = r"C:\Tools\opensearch-2.19.1"

# Root directory where all case folders live.
# The Home page scans this for sub-folders containing case.db files.
CASES_ROOT = r"C:\eDiscovery"

# --- Third-Party Tool Paths ---
# Update these to match where the tools are installed on YOUR machine.
WKHTMLTOPDF_PATH = r"C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe"
TESSERACT_PATH = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
LIBREOFFICE_PATH = r"C:\Program Files\LibreOffice\program\soffice.exe"

# --- Performance Tuning ---
# Maximum parallel imaging workers for Production Pass 1.
# 0 = auto-detect: min(4, cpu_count - 1). Set explicitly for fixed deployments.
IMAGING_WORKERS = 0

# Session inactivity timeout (minutes). Users are logged out after this many minutes
# of no page interaction. Default: 120 (2 hours). Set to 0 to disable.
# Increase for long-running processing or production jobs.
session_timeout_minutes = 120

# COM mutex timeout (milliseconds) for Outlook COM serialization during PST/MSG processing.
# Increase if large batches cause TimeoutError on slower machines. Default: 300000 (5 minutes).
COM_MUTEX_TIMEOUT_MS = 300000

# --- Filevine Integration ---
# The subdomain of the Filevine account (e.g. "my-firm" for my-firm.filevine.com).
FILEVINE_SUBDOMAIN = "your-firm-subdomain"
