# DEPLOYMENT_GUIDE.md — Respondeo eDiscovery Platform

> **Document Classification:** Internal Engineering Reference
> **Platform Version:** Beta 2.8 (March 2026)
> **Author:** Respondeo maintainer

---

## Overview

This guide covers deploying Respondeo on a fresh Windows machine. The platform is designed for **consultant-assisted deployment** — the `Deploy-Platform.ps1` bootstrap script automates the heavy lifting, while the deploying technician handles configuration decisions.

**Why not a self-installer?** The platform manages privileged and confidential legal materials. A hands-on deployment creates an accountability chain for the data environment, ensures paths and storage locations are intentional, and matches the deployment model of every commercial eDiscovery platform (Relativity, Concordance, IPRO, etc.).

---

## Prerequisites

| Requirement | Notes |
|---|---|
| Windows 10 or 11 (64-bit) | Server editions also supported |
| Administrator access | Required for winget, PATH changes, and service configuration |
| Internet connection | For downloading dependencies (offline install instructions below) |
| 8 GB RAM minimum | 16+ GB recommended for OpenSearch + Tika running concurrently |
| Python 3.11 | 3.14+ NOT supported; 3.12/3.13 untested |
| 20 GB free disk space | For tools and services; case data storage is separate |
| Microsoft Outlook (desktop) | Optional. libpff is the primary PST extraction method; Outlook COM is a fallback only |

---

## Dependency Stack

The platform has four layers, installed in order because each depends on the one above it:

```
Layer 1 — Core Runtime
├── Python 3.11           (app runtime; 3.12/3.13 untested, 3.14+ NOT supported)
├── Java 21+              (required by Tika)
└── Git                   (version control)

Layer 2 — Services (background processes)
├── Apache Tika Server    (text extraction — Java-based)
└── OpenSearch            (full-text search index — Java-based)

Layer 3 — System Tools (executables called by Python)
├── wkhtmltopdf           (HTML → PDF conversion)
├── Tesseract OCR         (scanned document text recognition)
├── LibreOffice           (Office → PDF conversion — strongly recommended)
└── Microsoft Outlook     (PST extraction via COM — optional)

Layer 4 — Python Environment
├── Virtual environment   (.venv)
├── pip dependencies      (requirements.txt)
└── Post-install patches  (streamlit-drawable-canvas fix)
```

---

## Automated Deployment

### Running the Bootstrap Script

1. Copy `Deploy-Platform.ps1` to the target machine (USB, network share, etc.)
2. Open PowerShell **as Administrator**
3. Allow script execution for the session:
   ```powershell
   Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
   ```
4. Run the script:
   ```powershell
   .\Deploy-Platform.ps1
   ```
5. The script will prompt for:
   - Git repository URL or local path to copy from
   - Case data root directory (where case folders will live)
   - Filevine subdomain (optional — press Enter to skip)

### What the Script Does

The script is **idempotent** — it detects already-installed components and skips them. You can safely re-run it after a partial failure or shell restart.

| Step | Action | Manual Fallback |
|---|---|---|
| 1 | Install Python 3.11 via winget | python.org/downloads |
| 2 | Install Git via winget | git-scm.com |
| 3 | Install Java 21 (Temurin) via winget | adoptium.net |
| 4 | Install wkhtmltopdf + Tesseract + LibreOffice via winget | See links below |
| 5 | Download Tika Server JAR to C:\Tools\tika\ | tika.apache.org/download.html |
| 6 | Download + extract OpenSearch to C:\Tools\ | opensearch.org/downloads.html |
| 7 | Clone project repository | `git clone <url>` manually |
| 8 | Create .venv, install pip dependencies | `python -m venv .venv` manually |
| 9 | Generate config.py with detected paths | Copy config.example.py and edit |
| 10 | Apply canvas patch, run setup_check.py | See Post-Install below |

### What the Script Creates

After a successful run, the project directory will contain two convenience launchers:

- **`Start-Services.bat`** — Opens Tika and OpenSearch in background terminal windows with proper startup delays
- **`Start-Platform.bat`** — Activates the Python venv and launches Streamlit on port 8501

---

## Manual Deployment (Step-by-Step)

Use this if the bootstrap script isn't available or if you're deploying in a restricted environment.

### Step 1 — Python

**IMPORTANT: Install Python 3.11 specifically.** Python 3.14+ breaks `streamlit-drawable-canvas` (a critical dependency for the in-browser redaction tool). Python 3.12 and 3.13 may work but are untested. 3.11 is the verified production version.

```powershell
winget install Python.Python.3.11
# OR download from https://www.python.org/downloads/release/python-3119/
# IMPORTANT: Check "Add Python to PATH" during installation
python --version   # Verify: should show 3.11.x
pip --version      # Verify
```

### Step 2 — Git

```powershell
winget install Git.Git
# OR download from https://git-scm.com/download/win
git --version      # Verify
```

### Step 3 — Java

```powershell
winget install EclipseAdoptium.Temurin.21.JDK
# OR download from https://adoptium.net/
java -version      # Verify: should show 21.x
```

### Step 4 — System Tools

```powershell
winget install wkhtmltopdf.wkhtmltopdf
winget install UB-Mannheim.TesseractOCR
winget install TheDocumentFoundation.LibreOffice   # Strongly recommended
```

Default install paths:
- wkhtmltopdf: `C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe`
- Tesseract: `C:\Program Files\Tesseract-OCR\tesseract.exe`
- LibreOffice: `C:\Program Files\LibreOffice\program\soffice.exe`

**LibreOffice note:** This is strongly recommended but not strictly required. It provides high-fidelity Office-to-PDF conversion during processing. If not installed, the platform falls back to `mammoth` for Word documents, which produces functional but lower-quality PDFs. The code checks for the executable at runtime and degrades gracefully.

### Step 5 — Apache Tika Server

1. Download the JAR from https://tika.apache.org/download.html
   - File: `tika-server-standard-3.2.3.jar` (or latest)
2. Place it in `C:\Tools\tika\`
3. Test it:
   ```
   java -jar C:\Tools\tika\tika-server-standard-3.2.3.jar --host 0.0.0.0 --port 9998
   ```
4. Verify: Open `http://localhost:9998/tika` in a browser — you should see an HTML page

### Step 6 — OpenSearch

1. Download the Windows ZIP from https://opensearch.org/downloads.html
2. Extract to `C:\Tools\opensearch-X.X.X\`
3. Edit `config\opensearch.yml` — add these lines at the bottom:
   ```yaml
   plugins.security.disabled: true
   discovery.type: single-node
   network.host: 0.0.0.0
   ```
4. Start it:
   ```
   C:\Tools\opensearch-X.X.X\bin\opensearch.bat
   ```
5. Verify: `curl http://localhost:9200` should return a JSON response

### Step 7 — Project Setup

```powershell
git clone <repo-url> C:\Projects\ediscovery
cd C:\Projects\ediscovery
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### Step 8 — Configuration

Copy `config.example.py` to `config.py` and update all paths:

```python
TIKA_JAR = r"C:\Tools\tika\tika-server-standard-3.2.3.jar"
OPENSEARCH_HOME = r"C:\Tools\opensearch-X.X.X"
CASES_ROOT = r"C:\eDiscovery\Cases"  # Your chosen location
WKHTMLTOPDF_PATH = r"C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe"
TESSERACT_PATH = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
LIBREOFFICE_PATH = r"C:\Program Files\LibreOffice\program\soffice.exe"
```

### Step 9 — Validate

```powershell
python setup_check.py
```

All checks should show PASS. Fix any failures before proceeding.

### Step 10 — Launch

```powershell
streamlit run home.py --server.address 0.0.0.0 --server.port 8501
```

Open `http://localhost:8501` in a browser.

---

## Post-Install: Canvas Patch

The `streamlit-drawable-canvas` package has a known bug in its JS bundle that affects the in-browser redaction tool. After installing Python dependencies, apply the patch:

```powershell
python _scratchpad\post_install_patch.py
```

This must be re-applied any time `streamlit-drawable-canvas` is upgraded via pip.

---

## Startup Order (Every Launch)

Services must be started before the platform:

1. **OpenSearch** — `Start-Services.bat` handles this, or run `opensearch.bat` manually
2. **Wait ~15 seconds** for OpenSearch to initialize
3. **Tika Server** — `Start-Services.bat` handles this, or run `java -jar tika-server-standard-*.jar`
4. **Wait ~10 seconds** for Tika to initialize
5. **Platform** — `Start-Platform.bat`, or `streamlit run home.py`

The platform's Home page shows service status indicators (green/red) for both Tika and OpenSearch.

---

## Offline Deployment

For air-gapped or restricted networks, pre-stage these files on a USB drive:

| Component | What to Download | Where to Place |
|---|---|---|
| Python 3.11 | Installer from python.org | Run installer |
| Git | Installer from git-scm.com | Run installer |
| Java 21 | MSI from adoptium.net | Run installer |
| wkhtmltopdf | Installer from wkhtmltopdf.org | Run installer |
| Tesseract | Installer from github.com/UB-Mannheim/tesseract/releases | Run installer |
| LibreOffice | Installer from libreoffice.org | Run installer (strongly recommended) |
| Tika Server | JAR from tika.apache.org | `C:\Tools\tika\` |
| OpenSearch | ZIP from opensearch.org | Extract to `C:\Tools\` |
| pip packages | `pip download -r requirements.txt -d ./packages` | `pip install --no-index --find-links=./packages -r requirements.txt` |
| Project repo | `git bundle create ediscovery.bundle --all` | `git clone ediscovery.bundle` |

---

## Developer Setup (Claude Code)

If using Claude Code in VSCode for development on this machine:

### Git Bash Path

Claude Code requires Git Bash for terminal operations. On fresh Windows installs, you may need to set:

```powershell
# PowerShell (run as Administrator)
[Environment]::SetEnvironmentVariable("CLAUDE_CODE_GIT_BASH_PATH", "C:\Program Files\Git\bin\bash.exe", "User")
```

Restart VSCode after setting this variable.

### Execution Policy for Development

For ongoing development sessions (not just deployment), set a persistent policy:

```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

This allows locally-created scripts to run without re-setting policy each session.

---

## Troubleshooting

### "Python not found" after installation
Close and reopen your terminal. winget installations may not update the current session's PATH. The bootstrap script calls `Refresh-Path` to handle this, but a terminal restart is sometimes needed.

### OpenSearch won't start
- Check if another process is using port 9200: `netstat -an | findstr 9200`
- Ensure `plugins.security.disabled: true` is in `opensearch.yml`
- OpenSearch requires significant memory. If it fails silently, check logs in `opensearch-X.X.X\logs\`

### Tika connection refused
- Tika takes 5–15 seconds to start. Wait and retry.
- Check port 9998: `netstat -an | findstr 9998`
- If Java isn't found, ensure JAVA_HOME is set or Java is on PATH

### pywin32 / Outlook COM errors
- `pywin32` only works on Windows with Outlook installed
- If Outlook is not installed, PST extraction falls back to `libpff-python` automatically
- The `setup_check.py` script reports a missing Outlook as a non-blocking warning

### libpff-python install fails (no C++ Build Tools)
- On machines without Visual C++ Build Tools, `pip install libpff-python` will fail with a compiler error
- Use the pre-built wheel vendored in the repo instead:
  ```powershell
  pip install vendor\wheels\libpff_python-20231205-cp311-cp311-win_amd64.whl
  ```
- This wheel is built for **Python 3.11 / Windows x64** — must match your Python version exactly
- If you are on a different Python version, you will need to build from source or obtain a matching wheel

### Canvas patch not applied
- Re-run `python _scratchpad\post_install_patch.py` after any pip upgrade
- The patch modifies a bundled JS file inside the installed package

---

## Updating an Existing Deployment

```powershell
cd C:\Projects\ediscovery
git pull origin main       # or beta-2.6
.venv\Scripts\activate
pip install -r requirements.txt --upgrade
python _scratchpad\post_install_patch.py   # re-apply canvas patch
python setup_check.py                       # verify
```

---

## Security Notes for Law Firm Deployments

- The platform runs entirely on the local machine/LAN — no data leaves the network unless Filevine sync is configured
- OpenSearch security is disabled (`plugins.security.disabled: true`) because access is controlled at the application layer via RBAC
- `auth_config.yaml` stores bcrypt-hashed passwords (work factor 12)
- `config.py` and `auth_config.yaml` are gitignored — they never enter version control
- Case data (`CASES_ROOT`) should be on an encrypted volume with appropriate backup policies
- For multi-workstation access, the machine running the platform should have a static LAN IP

---

## Remote Access via Tailscale

Tailscale provides secure, zero-configuration remote access for expert reviewers or attorneys working off-site. It creates a private encrypted mesh network (a "tailnet") between enrolled devices — no port forwarding, no public IP, no VPN server to maintain.

**Use case:** The platform runs on a firm machine. An expert reviewer on their own laptop connects to it from home or another location, accessing the Streamlit UI exactly as if they were on the local network.

### How It Works

Each enrolled device gets a stable private IP in the `100.x.x.x` range. The expert's laptop connects to `http://100.x.x.x:8501` — the platform's login page — and authenticates with their platform credentials (role: expert). Tailscale handles the encrypted tunnel; the platform handles identity and access control.

No case data transits a third-party server. Tailscale routes traffic peer-to-peer between enrolled devices using WireGuard encryption. The coordination server (Tailscale's infrastructure) only brokers the connection — it never sees the payload.

### Step 1 — Install Tailscale on the Platform Machine (Server)

1. Download the Windows installer from [tailscale.com/download](https://tailscale.com/download)
2. Install and sign in with a Tailscale account (Google, Microsoft, or email — free tier supports up to 3 users and 100 devices)
3. Note the machine's **Tailscale IP** from the Tailscale system tray icon or the admin console at [login.tailscale.com](https://login.tailscale.com):
   ```
   Example: 100.64.0.1
   ```
4. Ensure the platform is running with `--server.address 0.0.0.0` so it listens on all interfaces (including the Tailscale interface):
   ```powershell
   streamlit run home.py --server.address 0.0.0.0 --server.port 8501
   ```
   The `Start-Platform.bat` launcher already uses `0.0.0.0` by default.

### Step 2 — Install Tailscale on the Expert's Device (Client)

1. Install Tailscale on the expert's laptop (Windows, Mac, iOS, Android all supported)
2. Sign in with the **same Tailscale account** (or invite them via the admin console — see Sharing below)
3. Verify the connection: the expert should see the server's machine name appear in their Tailscale client

### Step 3 — Connect the Expert to the Platform

The expert opens a browser and navigates to:
```
http://<server-tailscale-ip>:8501
```

They will see the platform login page and authenticate with their assigned credentials (role: `expert`). Their access is governed entirely by the platform's RBAC — Tailscale provides the secure tunnel only.

**Tip:** Use the Tailscale MagicDNS hostname instead of the raw IP for a friendlier URL. If enabled, the server is reachable at something like:
```
http://firm-ediscovery-machine:8501
```

### Sharing with External Users (Non-Account Members)

If the expert cannot or should not create a Tailscale account under the firm's account, use **Tailscale node sharing**:

1. In the Tailscale admin console ([login.tailscale.com](https://login.tailscale.com)), select the server machine
2. Click **Share** → enter the expert's email address
3. The expert installs Tailscale on their device, signs in with their own personal account, and accepts the share invitation
4. The shared node (the server) appears in their Tailscale client and is reachable at its Tailscale IP

The expert's personal Tailscale account remains separate from the firm's account. They can only reach the specific shared machine — not any other firm devices.

### Firewall Considerations

Tailscale operates over UDP port 41641 (with fallback to TCP 443 if UDP is blocked). No inbound firewall rules need to be opened on the server — Tailscale initiates outbound connections. If the firm has a strict outbound firewall, ensure UDP 41641 and TCP 443 are allowed to Tailscale's relay servers.

### Windows Defender Firewall — Allow Streamlit on Tailscale Interface

Windows Firewall may block inbound connections to port 8501 from the Tailscale network adapter. If the expert cannot reach the platform, run this once on the server (as Administrator):

```powershell
New-NetFirewallRule -DisplayName "eDiscovery Hub (Tailscale)" `
    -Direction Inbound -Protocol TCP -LocalPort 8501 `
    -Action Allow -Profile Any
```

### Security Notes for Remote Access

- **Authentication is the platform's responsibility.** Tailscale only provides the encrypted network path. Ensure every remote user has a strong password set via the admin panel.
- **Limit the expert role appropriately.** The expert role is designed for read-only access with download rights — they cannot ingest, process, tag, redact, or modify the case. Confirm via the Role Permission Editor on the Home page.
- **Audit trail.** All expert actions (searches, STR runs, produced PDF downloads) are logged to the case audit log. Review regularly from the Admin-only Audit Log viewer on the Home page.
- **Revoke access immediately** when the engagement ends: disable the user account via the User Management panel on the Home page. For Tailscale node shares, revoke via the Tailscale admin console.
- **Do not expose port 8501 to the public internet** — Streamlit is not hardened for direct internet exposure. Tailscale is the access layer.
