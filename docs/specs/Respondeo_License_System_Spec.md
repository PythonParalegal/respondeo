# Respondeo License & Distribution System — Implementation Spec

> **Purpose:** Complete architecture for licensing, update distribution, and subscription enforcement.
> **Audience:** Claude Code implementation prompt / developer reference.
> **Date:** 2026-04-14
> **Revised:** 2026-04-14 — Fixed version string comparison bug (use tuple parsing instead of raw string `<`), added `winreg` import guard with clear error message, added explicit release checklist to Section 7.

---

## 1. System Overview

Three components work together:

```
┌─────────────────────┐        HTTPS         ┌──────────────────────┐
│  Client Install     │ ◄──────────────────►  │  PythonAnywhere      │
│  (law firm machine) │   license check       │  License Server       │
│                     │   + version check     │  (Flask + SQLite)    │
│  license_manager.py │                       │  /validate endpoint  │
│  .license cache     │                       │  /version  endpoint  │
│  hardware fingerprint                       │  admin panel         │
└─────────────────────┘                       └──────────────────────┘
         │
         │ startup gate
         ▼
┌─────────────────────┐
│  home.py            │
│  (existing auth)    │
│  Streamlit app      │
└─────────────────────┘
```

**Flow:** App starts → `license_manager.validate()` runs before auth gate → phones home to server → server checks key + fingerprint → returns status + latest version → client caches result locally (encrypted) → app proceeds or locks.

---

## 2. Server Side — PythonAnywhere Flask App

### 2.1 Tech Stack

- **Platform:** PythonAnywhere free tier (Beginner)
- **Framework:** Flask (included in PythonAnywhere default environment)
- **Database:** SQLite (single file, trivial at this scale)
- **Auth:** Simple API key in request header for admin endpoints; license key in body for validation

### 2.2 Database Schema

```sql
-- File: license_server/schema.sql

CREATE TABLE clients (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    client_name     TEXT NOT NULL,               -- "Smith & Associates LLP"
    contact_email   TEXT,                         -- billing contact
    license_key     TEXT NOT NULL UNIQUE,          -- UUID4: "RSP-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
    hardware_fp     TEXT,                          -- SHA-256 fingerprint, NULL until first activation
    status          TEXT NOT NULL DEFAULT 'active', -- active | suspended | revoked
    tier            TEXT NOT NULL DEFAULT 'standard', -- standard | premium (future use)
    subscription_start DATE NOT NULL,
    subscription_end   DATE,                      -- NULL = indefinite/monthly
    grace_days      INTEGER NOT NULL DEFAULT 14,  -- offline grace period
    max_version     TEXT,                          -- highest version they're entitled to (NULL = latest)
    notes           TEXT,                          -- internal notes
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE activations (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    license_key     TEXT NOT NULL,
    hardware_fp     TEXT NOT NULL,
    ip_address      TEXT,
    activated_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (license_key) REFERENCES clients(license_key)
);

CREATE TABLE check_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    license_key     TEXT NOT NULL,
    hardware_fp     TEXT,
    ip_address      TEXT,
    result          TEXT NOT NULL,                 -- valid | expired | suspended | revoked | fp_mismatch | unknown_key
    client_version  TEXT,                          -- version the client reported
    checked_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

**Notes:**
- `activations` table keeps history of every hardware fingerprint registration (audit trail for disputes).
- `check_log` gives you visibility into who's checking in, from where, running what version.
- `grace_days` is per-client so you can extend it for firms in rural areas with unreliable internet.

### 2.3 Flask Application

```python
# File: license_server/app.py
# Deploy to PythonAnywhere as a Flask WSGI app

from flask import Flask, request, jsonify
import sqlite3
import os
from datetime import datetime, date

app = Flask(__name__)
DB_PATH = os.path.join(os.path.dirname(__file__), 'licenses.db')

LATEST_VERSION = "2.9.0"  # Update this when you cut a release
ADMIN_API_KEY = os.environ.get('ADMIN_API_KEY', 'CHANGE-ME-ON-DEPLOY')

def _parse_version(v: str) -> tuple:
    """Parse version string to tuple for correct numeric comparison.
    '2.10.0' → (2, 10, 0).  Avoids string comparison bug where '2.10.0' < '2.9.0'."""
    try:
        return tuple(int(x) for x in v.split('.'))
    except (ValueError, AttributeError):
        return (0, 0, 0)

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

# ── Public endpoint: license validation ──────────────────────────────────

@app.route('/validate', methods=['POST'])
def validate_license():
    """
    Client sends:
    {
        "license_key": "RSP-...",
        "hardware_fp": "sha256hex...",
        "client_version": "2.9.0"
    }

    Server returns:
    {
        "status": "valid" | "expired" | "suspended" | "revoked" | "fp_mismatch" | "unknown_key",
        "grace_days": 14,
        "latest_version": "2.9.0",
        "update_url": "https://...",        # only if newer version available
        "server_time": "2026-04-14T...",    # client uses this to detect clock tampering
        "message": ""                        # optional message to display
    }
    """
    data = request.get_json(silent=True) or {}
    key = data.get('license_key', '').strip()
    fp = data.get('hardware_fp', '').strip()
    client_ver = data.get('client_version', '')

    if not key or not fp:
        return jsonify({"status": "error", "message": "Missing required fields"}), 400

    db = get_db()
    try:
        row = db.execute("SELECT * FROM clients WHERE license_key = ?", (key,)).fetchone()

        # Unknown key
        if not row:
            _log_check(db, key, fp, 'unknown_key', client_ver)
            return jsonify({"status": "unknown_key", "message": "License key not recognized"})

        # Check subscription status
        if row['status'] == 'revoked':
            _log_check(db, key, fp, 'revoked', client_ver)
            return jsonify({"status": "revoked", "message": "License has been revoked"})

        if row['status'] == 'suspended':
            _log_check(db, key, fp, 'suspended', client_ver)
            return jsonify({"status": "suspended", "message": "Subscription suspended — contact support"})

        # Check expiration
        if row['subscription_end']:
            end_date = date.fromisoformat(row['subscription_end'])
            if date.today() > end_date:
                _log_check(db, key, fp, 'expired', client_ver)
                return jsonify({"status": "expired", "message": "Subscription expired"})

        # Hardware fingerprint: first activation or validation
        if not row['hardware_fp']:
            # First activation — register this fingerprint
            db.execute("UPDATE clients SET hardware_fp = ?, updated_at = ? WHERE license_key = ?",
                       (fp, datetime.utcnow().isoformat(), key))
            db.execute("INSERT INTO activations (license_key, hardware_fp, ip_address) VALUES (?, ?, ?)",
                       (key, fp, request.remote_addr))
            db.commit()
        elif row['hardware_fp'] != fp:
            # Fingerprint mismatch — different machine
            _log_check(db, key, fp, 'fp_mismatch', client_ver)
            return jsonify({
                "status": "fp_mismatch",
                "message": "This license is registered to a different machine. Contact support to transfer."
            })

        # All checks passed
        response = {
            "status": "valid",
            "grace_days": row['grace_days'],
            "latest_version": LATEST_VERSION,
            "server_time": datetime.utcnow().isoformat(),
            "message": ""
        }

        # Check if client is entitled to the latest version
        if row['max_version'] and _parse_version(row['max_version']) < _parse_version(LATEST_VERSION):
            response['latest_version'] = row['max_version']

        # Include update URL if newer version available
        if client_ver and _parse_version(client_ver) < _parse_version(response['latest_version']):
            response['update_url'] = f"https://your-distribution-url/releases/{response['latest_version']}"
            response['message'] = f"Update available: v{response['latest_version']}"

        _log_check(db, key, fp, 'valid', client_ver)
        return jsonify(response)

    finally:
        db.close()


def _log_check(db, key, fp, result, client_ver):
    """Log every validation attempt for audit trail."""
    db.execute(
        "INSERT INTO check_log (license_key, hardware_fp, ip_address, result, client_version) VALUES (?, ?, ?, ?, ?)",
        (key, fp, request.remote_addr, result, client_ver)
    )
    db.commit()


# ── Public endpoint: version check (lightweight, no auth) ────────────────

@app.route('/version', methods=['GET'])
def version_info():
    """Simple endpoint the client can hit to check latest version without full validation."""
    return jsonify({"latest_version": LATEST_VERSION})


# ── Admin endpoints (protected by API key) ───────────────────────────────

def require_admin():
    """Check admin API key in Authorization header."""
    auth = request.headers.get('Authorization', '')
    return auth == f'Bearer {ADMIN_API_KEY}'

@app.route('/admin/clients', methods=['GET'])
def list_clients():
    if not require_admin():
        return jsonify({"error": "Unauthorized"}), 401
    db = get_db()
    rows = db.execute("SELECT id, client_name, license_key, status, hardware_fp, subscription_end FROM clients").fetchall()
    db.close()
    return jsonify([dict(r) for r in rows])

@app.route('/admin/clients', methods=['POST'])
def create_client():
    """Create a new client license. Generates a UUID license key."""
    if not require_admin():
        return jsonify({"error": "Unauthorized"}), 401
    import uuid
    data = request.get_json()
    key = f"RSP-{uuid.uuid4()}"
    db = get_db()
    db.execute(
        """INSERT INTO clients (client_name, contact_email, license_key, status, subscription_start, grace_days)
           VALUES (?, ?, ?, 'active', ?, ?)""",
        (data['client_name'], data.get('contact_email'), key, date.today().isoformat(), data.get('grace_days', 14))
    )
    db.commit()
    db.close()
    return jsonify({"license_key": key, "client_name": data['client_name']}), 201

@app.route('/admin/clients/<key>/suspend', methods=['POST'])
def suspend_client(key):
    if not require_admin():
        return jsonify({"error": "Unauthorized"}), 401
    db = get_db()
    db.execute("UPDATE clients SET status = 'suspended', updated_at = ? WHERE license_key = ?",
               (datetime.utcnow().isoformat(), key))
    db.commit()
    db.close()
    return jsonify({"status": "suspended"})

@app.route('/admin/clients/<key>/revoke', methods=['POST'])
def revoke_client(key):
    if not require_admin():
        return jsonify({"error": "Unauthorized"}), 401
    db = get_db()
    db.execute("UPDATE clients SET status = 'revoked', updated_at = ? WHERE license_key = ?",
               (datetime.utcnow().isoformat(), key))
    db.commit()
    db.close()
    return jsonify({"status": "revoked"})

@app.route('/admin/clients/<key>/reset-fingerprint', methods=['POST'])
def reset_fingerprint(key):
    """Reset hardware fingerprint — use when client migrates to new server."""
    if not require_admin():
        return jsonify({"error": "Unauthorized"}), 401
    db = get_db()
    db.execute("UPDATE clients SET hardware_fp = NULL, updated_at = ? WHERE license_key = ?",
               (datetime.utcnow().isoformat(), key))
    db.commit()
    db.close()
    return jsonify({"status": "fingerprint_reset"})

@app.route('/admin/clients/<key>/reactivate', methods=['POST'])
def reactivate_client(key):
    if not require_admin():
        return jsonify({"error": "Unauthorized"}), 401
    db = get_db()
    db.execute("UPDATE clients SET status = 'active', updated_at = ? WHERE license_key = ?",
               (datetime.utcnow().isoformat(), key))
    db.commit()
    db.close()
    return jsonify({"status": "active"})
```

### 2.4 Deployment on PythonAnywhere

1. Create free account at pythonanywhere.com
2. Go to "Web" tab → "Add a new web app" → Manual config → Python 3.10
3. Upload `app.py` and `schema.sql` to `/home/yourusername/license_server/`
4. Initialize database: open a Bash console, run `sqlite3 /home/yourusername/license_server/licenses.db < schema.sql`
5. Set WSGI config to point to your Flask app
6. Set environment variable `ADMIN_API_KEY` to a strong random string
7. Reload the web app

**WSGI file** (PythonAnywhere provides a template, replace contents with):
```python
import sys
sys.path.insert(0, '/home/yourusername/license_server')
from app import app as application
```

---

## 3. Client Side — `license_manager.py`

This module lives in the Respondeo project root alongside `auth_manager.py`, `db_manager.py`, etc.

### 3.1 Hardware Fingerprinting

```python
def _generate_hardware_fingerprint() -> str:
    """
    Generate a stable hardware fingerprint for this machine.

    Uses: Windows machine GUID (from registry), hostname, and primary MAC address.
    Returns SHA-256 hex digest.

    Why these three:
    - Machine GUID: unique per Windows install, survives hardware swaps
    - Hostname: adds specificity, rarely changes on servers
    - MAC address: tied to physical NIC, survives OS reinstalls

    Any ONE changing (e.g., new NIC after motherboard swap) triggers a
    fingerprint mismatch — client contacts us for a reset. This is by design:
    we WANT to know when the hardware changes.
    """
    import hashlib
    import uuid
    import platform

    try:
        import winreg
    except ImportError:
        raise RuntimeError(
            "Respondeo requires Windows. The license manager uses the Windows "
            "registry for hardware fingerprinting and cannot run on other platforms."
        )

    parts = []

    # 1. Windows Machine GUID (most stable identifier)
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                            r"SOFTWARE\Microsoft\Cryptography") as key:
            machine_guid, _ = winreg.QueryValueEx(key, "MachineGuid")
            parts.append(machine_guid)
    except OSError:
        parts.append("no-machine-guid")

    # 2. Hostname
    parts.append(platform.node())

    # 3. Primary MAC address
    mac = ':'.join(f'{(uuid.getnode() >> i) & 0xff:02x}' for i in range(0, 48, 8))
    parts.append(mac)

    combined = '|'.join(parts)
    return hashlib.sha256(combined.encode('utf-8')).hexdigest()
```

### 3.2 Encrypted Local Cache

The cache stores the last successful validation result so the app works during network outages (grace period).

```python
import json
import os
import time
import hashlib
from cryptography.fernet import Fernet

# Cache lives OUTSIDE the code directory — in a dot-folder in the cases root.
# This way it survives code updates (unzip over existing install).
# Path: {CASES_ROOT}/.respondeo/license_cache.enc

def _get_cache_path() -> str:
    """Return path to encrypted license cache file."""
    import config
    cache_dir = os.path.join(config.CASES_ROOT, '.respondeo')
    os.makedirs(cache_dir, exist_ok=True)
    return os.path.join(cache_dir, 'license_cache.enc')

def _derive_cache_key(hardware_fp: str) -> bytes:
    """
    Derive a Fernet encryption key from the hardware fingerprint.

    This ties the cache to THIS machine — copying the cache file to a
    different machine won't work because the fingerprint (and therefore
    the decryption key) will be different.
    """
    # Fernet needs a 32-byte URL-safe base64 key. We derive it from the
    # fingerprint using a fixed salt (not secret — the security comes from
    # the fingerprint being machine-specific).
    import base64
    key_material = hashlib.sha256(
        (hardware_fp + ':respondeo-cache-salt').encode()
    ).digest()
    return base64.urlsafe_b64encode(key_material)

def _write_cache(data: dict, hardware_fp: str):
    """Encrypt and write license validation result to local cache."""
    key = _derive_cache_key(hardware_fp)
    f = Fernet(key)
    payload = json.dumps(data).encode()
    encrypted = f.encrypt(payload)  # Fernet includes a timestamp
    with open(_get_cache_path(), 'wb') as fh:
        fh.write(encrypted)

def _read_cache(hardware_fp: str) -> dict | None:
    """Read and decrypt cached license validation. Returns None if missing/invalid."""
    cache_path = _get_cache_path()
    if not os.path.exists(cache_path):
        return None
    try:
        key = _derive_cache_key(hardware_fp)
        f = Fernet(key)
        with open(cache_path, 'rb') as fh:
            encrypted = fh.read()
        decrypted = f.decrypt(encrypted)
        return json.loads(decrypted)
    except Exception:
        return None  # Corrupted, tampered, or from different machine
```

### 3.3 Main Validation Function

```python
import requests
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

def _parse_version(v: str) -> tuple:
    """Parse version string to tuple for correct numeric comparison.
    '2.10.0' → (2, 10, 0).  Avoids string comparison bug where '2.10.0' < '2.9.0'."""
    try:
        return tuple(int(x) for x in v.split('.'))
    except (ValueError, AttributeError):
        return (0, 0, 0)

LICENSE_SERVER_URL = "https://yourusername.pythonanywhere.com"
LICENSE_KEY_FILE = "license.key"  # In project root, gitignored

def _read_license_key() -> str | None:
    """Read license key from local file."""
    key_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), LICENSE_KEY_FILE)
    if not os.path.exists(key_path):
        return None
    with open(key_path, 'r') as f:
        return f.read().strip()

def validate(show_ui: bool = True) -> dict:
    """
    Main entry point. Call from home.py before auth gate.

    Returns:
        {
            "valid": True/False,
            "status": "valid" | "grace_period" | "expired" | ... ,
            "message": "..." ,
            "latest_version": "2.9.0",
            "update_available": True/False,
            "days_remaining": 12  # grace period days left, if applicable
        }

    Behavior:
        1. Read license key from file
        2. Generate hardware fingerprint
        3. Try phone-home to license server
        4. On success: cache result, return status
        5. On network failure: check cached result + grace period
        6. On no cache / expired grace: return invalid
    """
    import config

    result = {
        "valid": False,
        "status": "error",
        "message": "",
        "latest_version": config.__version__,
        "update_available": False,
        "days_remaining": 0
    }

    # Step 1: Read license key
    license_key = _read_license_key()
    if not license_key:
        result["status"] = "no_license"
        result["message"] = "No license key found. Place your license.key file in the application directory."
        return result

    # Step 2: Generate hardware fingerprint
    hardware_fp = _generate_hardware_fingerprint()

    # Step 3: Try phone-home
    try:
        response = requests.post(
            f"{LICENSE_SERVER_URL}/validate",
            json={
                "license_key": license_key,
                "hardware_fp": hardware_fp,
                "client_version": config.__version__
            },
            timeout=10  # 10 second timeout — don't block startup too long
        )

        if response.status_code == 200:
            server_data = response.json()
            status = server_data.get("status", "error")

            if status == "valid":
                # Cache the successful result
                cache_data = {
                    "status": "valid",
                    "checked_at": datetime.utcnow().isoformat(),
                    "grace_days": server_data.get("grace_days", 14),
                    "server_time": server_data.get("server_time"),
                    "latest_version": server_data.get("latest_version", config.__version__)
                }
                _write_cache(cache_data, hardware_fp)

                result["valid"] = True
                result["status"] = "valid"
                result["latest_version"] = server_data.get("latest_version", config.__version__)
                result["update_available"] = (
                    _parse_version(result["latest_version"]) > _parse_version(config.__version__)
                    and server_data.get("update_url") is not None
                )
                if result["update_available"]:
                    result["message"] = server_data.get("message", "")
                return result
            else:
                # Server explicitly rejected — revoked, suspended, expired, fp_mismatch
                result["status"] = status
                result["message"] = server_data.get("message", "License validation failed")
                # Clear cache on explicit rejection so grace period doesn't save them
                _clear_cache()
                return result

    except requests.RequestException as e:
        # Network failure — fall through to grace period check
        logger.warning(f"License server unreachable: {e}")

    # Step 4: Network failed — check grace period from cache
    cached = _read_cache(hardware_fp)
    if cached and cached.get("status") == "valid":
        checked_at = datetime.fromisoformat(cached["checked_at"])
        grace_days = cached.get("grace_days", 14)
        grace_deadline = checked_at + timedelta(days=grace_days)
        now = datetime.utcnow()

        if now < grace_deadline:
            days_left = (grace_deadline - now).days
            result["valid"] = True
            result["status"] = "grace_period"
            result["days_remaining"] = days_left
            result["message"] = f"Operating offline — {days_left} days until license re-verification required"
            result["latest_version"] = cached.get("latest_version", config.__version__)
            return result
        else:
            result["status"] = "grace_expired"
            result["message"] = "Offline grace period expired. Connect to the internet to re-verify your license."
            return result

    # Step 5: No cache, no network — can't validate
    result["status"] = "no_connection"
    result["message"] = "Cannot reach license server and no cached validation exists. Check your internet connection."
    return result


def _clear_cache():
    """Remove cached license data (used on explicit server rejection)."""
    cache_path = _get_cache_path()
    if os.path.exists(cache_path):
        os.remove(cache_path)
```

### 3.4 Config & Gitignore Additions

**Add to `config.example.py`:**
```python
# --- Licensing ---
# License server URL. Do not change unless instructed.
LICENSE_SERVER_URL = "https://yourusername.pythonanywhere.com"
```

**Add to `.gitignore`:**
```
license.key
```

### 3.5 New Dependency

```
# Add to requirements.txt (exact pin)
cryptography==44.0.0   # Fernet encryption for license cache
```

`requests` is already in the project dependencies. `cryptography` is the only new one — it's a well-established, PyCA-maintained package with minimal transitive dependencies (`cffi` + `pycparser`, both mature).

---

## 4. Integration with Existing App

### 4.1 Startup Gate in `home.py`

The license check runs **before** the auth gate. This is important: if the license is invalid, there's no point showing a login screen.

```python
# home.py — add BEFORE the existing auth gate

import license_manager

# --- LICENSE GATE ---
license_status = license_manager.validate()

if not license_status["valid"]:
    st.error(f"⚠️ {license_status['message']}")
    if license_status["status"] in ("expired", "suspended", "revoked"):
        st.info("Contact Respondeo support to resolve your subscription.")
    st.stop()

# Show grace period warning (non-blocking)
if license_status["status"] == "grace_period":
    st.warning(
        f"⚠️ {license_status['message']}"
    )

# Show update notification (non-blocking)
if license_status.get("update_available"):
    st.info(f"📦 {license_status['message']}")

# --- AUTH GATE (existing) ---
if not auth_manager.setup_initial_admin():
    st.stop()
if not auth_manager.check_login():
    st.stop()
```

### 4.2 Page-Level Protection (Optional Hardening)

The `home.py` gate catches normal startup. But Streamlit's multipage architecture means someone could theoretically navigate directly to a page URL. For defense in depth, add a lightweight cached check to `auth_manager.py`:

```python
# In auth_manager.py — add a function that pages can call

def require_valid_license():
    """Quick license check using session state (set by home.py gate)."""
    if not st.session_state.get("_license_valid", False):
        st.error("License validation required. Return to the Home page.")
        st.stop()
```

And in `home.py`, after the license check passes:
```python
st.session_state["_license_valid"] = True
```

### 4.3 Session State Key

| Key | Set By | Read By | Values |
|-----|--------|---------|--------|
| `_license_valid` | `home.py` (license gate) | `auth_manager.require_valid_license()` | `True` / absent |

Add this to `DEPENDENCY_MAP.md` §3 (Session State Keys) when implementing.

---

## 5. Hardware Fingerprint — Design Decisions

### Why these three identifiers?

| Identifier | Stability | What changes it |
|-----------|-----------|-----------------|
| Windows Machine GUID | Very high — survives reboots, hardware changes | Only changes on full OS reinstall |
| Hostname | High — servers rarely renamed | Admin renames machine |
| Primary MAC address | Moderate — tied to physical NIC | New NIC, or VM migration |

### Deliberate trade-off

We want the fingerprint to be **stable enough** that normal operation never triggers a mismatch, but **sensitive enough** that moving to a genuinely different machine does. A full OS reinstall + new NIC + rename (i.e., a truly different machine) will always trigger it. A single change (new NIC on same machine after motherboard swap) will also trigger it — this is a support interaction, not a crisis. You reset the fingerprint on the server, client reactivates, done.

### What we intentionally DON'T include

- **Disk serial numbers:** unreliable in VMs and RAID setups
- **CPU info:** identical across identical hardware purchases (common at law firms buying in bulk)
- **IP address:** changes constantly, as discussed earlier

---

## 6. Grace Period — Design Decisions

### Default: 14 days

Law firms have unpredictable IT situations — internet outages, office moves, server maintenance. 14 days is long enough to ride out any reasonable disruption. Configurable per-client on the server side if a firm has known connectivity issues.

### Grace period starts from last successful check, not from failure

This is important. If a client's app successfully validated on Monday and their internet goes out Tuesday, the grace period is 14 days from Monday. They have until two Mondays later. If they open the app daily, it tries to phone home each time and fails gracefully. The countdown doesn't reset on each failure.

### Clock tampering resistance

The cache stores the `server_time` from the last successful check. A future enhancement could compare local clock against server time and flag discrepancies. For now, the Fernet token includes its own creation timestamp which provides some protection — but this is a low-priority concern given the client profile.

---

## 7. Update Distribution

### Mechanism

Updates are distributed as zip files. The license server's `/validate` response includes `latest_version` and `update_url` when a newer version is available. The client app displays a notification.

### Release Checklist

Every release must touch both client and server. There is no automated sync between them — this checklist is your safeguard against forgetting a step.

1. Bump `__version__` in `config.py` (client side)
2. Cut a release branch and tag it in git
3. Create a zip of the release (excluding `.git/`, `config.py`, `license.key`, `__pycache__/`, `.respondeo/`)
4. Upload the zip to your distribution location (see options below)
5. Update `LATEST_VERSION` in the Flask server's `app.py` to match the new `__version__`
6. Verify: hit the server's `/version` endpoint and confirm it returns the new version number
7. Clients see the update notification on next app launch
8. Client downloads zip, extracts over existing install
9. `config.py`, `license.key`, and `.respondeo/` cache survive because they're excluded from the zip

**Critical:** If you forget step 5, clients will never see the update notification. If you do step 5 before step 4, clients see a notification that points to a download that doesn't exist yet. Always upload the zip before updating the server.

### Distribution hosting options (cheapest first)

| Option | Cost | Effort | Notes |
|--------|------|--------|-------|
| Google Drive shared link | Free | Low | Upload zip, generate shareable link, paste into server config. Simple but links can be reshared. |
| GitHub Releases (separate private repo) | Free | Low | Create a `respondeo-releases` repo, upload zips as release assets. Clients get a personal access token. Better access control. |
| Backblaze B2 + signed URLs | Free (10GB) | Medium | Programmatic signed URLs that expire. Best security but more setup. |
| S3 presigned URLs | ~$0.02/mo | Medium | Same idea as B2, AWS ecosystem. |

**Recommendation for now:** GitHub Releases on a separate private `respondeo-releases` repo. Each client gets a fine-grained personal access token scoped to that repo only (read-only, no source code access). When they unsubscribe, you revoke the token. This is fully ToS-compliant because each client uses their own real GitHub account or a single service account you create per firm.

---

## 8. What the License System Does NOT Prevent (and What Covers the Gap)

| Threat | Technical defense | Contractual defense |
|--------|-------------------|---------------------|
| Client keeps using software after unsubscribing | License check blocks startup; grace period expires | Subscription agreement requires deletion of all copies |
| Client modifies Python source to remove license check | Cython-compiled `license_manager.pyd` makes this very difficult | Software license prohibits modification/reverse engineering |
| Client copies install to second machine | Hardware fingerprint detects mismatch | License is per-machine; additional seats require additional licenses |
| Client shares zip with non-client | No license key in the zip; recipient can't activate | Subscription agreement prohibits redistribution |
| Client extracts and reuses your code in their own tool | Nothing (fundamental limit of distributing source) | Copyright + license agreement; statutory damages available |

The Cython compilation of `license_manager.py` into a `.pyd` binary is a **Phase 2 hardening step.** It's not needed for launch — your initial clients are law firms with no technical motivation to tamper. Add it before you scale beyond trusted early adopters.

---

## 9. File Inventory (New Files)

### Server side (PythonAnywhere)
```
license_server/
├── app.py           # Flask application
├── schema.sql       # Database schema
└── licenses.db      # SQLite database (created from schema)
```

### Client side (Respondeo project)
```
license_manager.py    # New module — license validation, fingerprinting, cache
license.key           # Per-install file (gitignored) — contains RSP-uuid key
```

### Modified files
```
home.py              # Add license gate before auth gate
config.example.py    # Add LICENSE_SERVER_URL
auth_manager.py      # Add require_valid_license() (optional hardening)
.gitignore           # Add license.key
requirements.txt     # Add cryptography==44.0.0
DEPENDENCY_MAP.md    # Add _license_valid session state key
```

---

## 10. Implementation Order

When you're ready to build this, the recommended order is:

1. **`license_manager.py`** — the client module with fingerprinting, cache, and validation logic. Can be tested locally with a mock server.
2. **`home.py` integration** — add the license gate. Test with a deliberately failing validation to confirm the block works.
3. **PythonAnywhere setup** — deploy the Flask server, initialize the database, create your first test license.
4. **End-to-end test** — activate a real license, verify phone-home works, test offline grace period by disconnecting network.
5. **`auth_manager.py` hardening** — add `require_valid_license()` to page-level checks.
6. **Distribution pipeline** — set up the releases repo or chosen distribution channel.
7. **Phase 2 (later):** Cython-compile `license_manager.py` to `.pyd`.

---

## 11. Security Notes

- **HTTPS only.** PythonAnywhere free tier serves over HTTPS by default. Never downgrade to HTTP.
- **License keys are secrets.** Treat them like passwords — never log the full key in client-side logs. Log only the first 8 characters for debugging (`RSP-a4f8...`).
- **Admin API key rotation.** Change `ADMIN_API_KEY` periodically. It's the only thing protecting your admin endpoints.
- **Rate limiting.** PythonAnywhere has built-in rate limiting on the free tier, which is sufficient. If you move to a VPS later, add Flask-Limiter to prevent brute-force key guessing.
- **The `license.key` file should be read-only** (Windows file permissions) on client installs to prevent accidental modification.
