#Requires -Version 5.1
<#
.SYNOPSIS
    DIY eDiscovery Hub - Fresh Machine Bootstrap Script

.DESCRIPTION
    Automated deployment script for setting up the eDiscovery platform on a
    clean Windows machine. Designed for consultant-assisted deployment.

    This script will:
      1. Verify/install Python 3.11
      2. Verify/install Git
      3. Verify/install Java 21 (Eclipse Temurin)
      4. Verify/install system tools (wkhtmltopdf, Tesseract OCR, LibreOffice)
      5. Download and configure Apache Tika Server
      6. Download and configure OpenSearch
      7. Clone the project repository
      8. Create Python virtual environment and install dependencies
      9. Generate machine-specific config.py
     10. Apply post-install patches and validate

.NOTES
    Platform:    DIY eDiscovery Hub v2.7+
    Author:      Respondeo maintainer
    Requires:    Windows 10/11, PowerShell 5.1+, Internet connection, Admin rights

.EXAMPLE
    Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
    .\Deploy-Platform.ps1
#>

# -----------------------------------------------------------------------------
# CONFIGURATION - Edit these before running if defaults don't suit the target
# -----------------------------------------------------------------------------

$Config = @{
    # Where the project repo will be cloned
    ProjectDir       = "C:\Projects\ediscovery"

    # Where Java services (Tika, OpenSearch) will live
    ToolsDir         = "C:\Tools"

    # Tika version to download
    TikaVersion      = "3.2.3"

    # OpenSearch version to download
    OpenSearchVersion = "2.19.1"

    # Where case data will be stored
    CasesRoot        = "C:\eDiscovery\Cases"

    # Git repo URL
    GitRepoURL       = "https://github.com/YOUR-ORG/ediscovery-platform.git"

    # Branch to checkout after cloning (set to $null to prompt interactively)
    Branch           = "beta-2.8"

    # Python version - MUST be 3.11.x (3.14+ breaks streamlit-drawable-canvas)
    PythonTargetVersion = "3.11"
    PythonMinVersion = "3.11"
    PythonMaxVersion = "3.13"
}

# -----------------------------------------------------------------------------
# HELPER FUNCTIONS
# -----------------------------------------------------------------------------

function Write-Banner {
    param([string]$Text)
    $line = "=" * 70
    Write-Host ""
    Write-Host $line -ForegroundColor Cyan
    Write-Host "  $Text" -ForegroundColor Cyan
    Write-Host $line -ForegroundColor Cyan
    Write-Host ""
}

function Write-Step {
    param([string]$Number, [string]$Text)
    Write-Host ""
    Write-Host "--- Step $Number -------------------------------------------------" -ForegroundColor Yellow
    Write-Host "  $Text" -ForegroundColor White
    Write-Host ""
}

function Write-OK   { param([string]$Text) Write-Host "  [OK] $Text" -ForegroundColor Green }
function Write-Warn { param([string]$Text) Write-Host "  [!!] $Text" -ForegroundColor Yellow }
function Write-Err  { param([string]$Text) Write-Host "  [XX] $Text" -ForegroundColor Red }
function Write-Info { param([string]$Text) Write-Host "  [..] $Text" -ForegroundColor Gray }

function Test-IsAdmin {
    $principal = New-Object Security.Principal.WindowsPrincipal(
        [Security.Principal.WindowsIdentity]::GetCurrent()
    )
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Test-CommandExists {
    param([string]$Command)
    return [bool](Get-Command $Command -ErrorAction SilentlyContinue)
}

function Get-UserConfirmation {
    param([string]$Prompt)
    $response = Read-Host "$Prompt (Y/n)"
    return ($response -eq "" -or $response -match "^[Yy]")
}

function Refresh-Path {
    $machinePath = [Environment]::GetEnvironmentVariable("Path", "Machine")
    $userPath    = [Environment]::GetEnvironmentVariable("Path", "User")
    $env:Path = "$machinePath;$userPath"
}

# -----------------------------------------------------------------------------
# PRE-FLIGHT
# -----------------------------------------------------------------------------

Write-Banner "DIY eDiscovery Hub - Fresh Machine Deployment"

Write-Host "  Target machine:  $env:COMPUTERNAME" -ForegroundColor White
Write-Host "  Windows version: $([System.Environment]::OSVersion.VersionString)" -ForegroundColor White
Write-Host "  PowerShell:      $($PSVersionTable.PSVersion)" -ForegroundColor White
Write-Host "  Date:            $(Get-Date -Format 'yyyy-MM-dd HH:mm')" -ForegroundColor White
Write-Host ""

# Admin check
if (-not (Test-IsAdmin)) {
    Write-Err "This script must be run as Administrator."
    Write-Err "Right-click PowerShell -> 'Run as administrator', then re-run."
    exit 1
}
Write-OK "Running as Administrator"

# Execution policy check
$execPolicy = Get-ExecutionPolicy -Scope Process
if ($execPolicy -eq "Restricted" -or $execPolicy -eq "AllSigned") {
    Write-Warn "Current execution policy ($execPolicy) may block script execution."
    Write-Warn "If this script fails, run this command first:"
    Write-Host "    Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass" -ForegroundColor Yellow
    Write-Host ""
    if (-not (Get-UserConfirmation "Continue anyway?")) {
        exit 1
    }
} else {
    Write-OK "Execution policy: $execPolicy"
}

# winget check
if (-not (Test-CommandExists "winget")) {
    Write-Err "winget (Windows Package Manager) not found."
    Write-Err "Install it from the Microsoft Store (App Installer) and re-run."
    exit 1
}
Write-OK "winget available"

# Create tools directory
if (-not (Test-Path $Config.ToolsDir)) {
    New-Item -ItemType Directory -Path $Config.ToolsDir -Force | Out-Null
    Write-OK "Created $($Config.ToolsDir)"
} else {
    Write-OK "$($Config.ToolsDir) exists"
}

# -----------------------------------------------------------------------------
# STEP 1 - PYTHON
# -----------------------------------------------------------------------------

Write-Step "1/10" "Python $($Config.PythonTargetVersion) (3.14+ NOT supported)"

$pythonCmd = $null
$maximum = [version]$Config.PythonMaxVersion

# First, try the py launcher targeting 3.11 specifically
if (Test-CommandExists "py") {
    try {
        $pyVer = & py -3.11 --version 2>&1
        if ($pyVer -match "Python 3\.11") {
            $pyPath = (& py -3.11 -c "import sys; print(sys.executable)" 2>&1).Trim()
            if (Test-Path $pyPath) {
                $pythonCmd = $pyPath
                Write-OK "Found $pyVer (resolved to '$pyPath')"
            }
        }
    } catch { }
}

# Fall back to checking python/python3 on PATH
if (-not $pythonCmd) {
    foreach ($candidate in @("python", "python3")) {
        if (Test-CommandExists $candidate) {
            $ver = & $candidate --version 2>&1
            if ($ver -match "Python (\d+\.\d+)") {
                $found = [version]$Matches[1]
                $minimum = [version]$Config.PythonMinVersion
                if ($found -ge $minimum -and $found -le $maximum) {
                    $pythonCmd = $candidate
                    Write-OK "Found $ver (using '$candidate')"
                    break
                } elseif ($found -gt $maximum) {
                    Write-Warn "Found $ver but Python $($found) is too new (max $($Config.PythonMaxVersion))."
                    Write-Warn "streamlit-drawable-canvas breaks on Python 3.14+."
                }
            }
        }
    }
}

if (-not $pythonCmd) {
    Write-Warn "Python $($Config.PythonTargetVersion) not found. Installing via winget..."
    winget install Python.Python.3.11 --source winget --accept-source-agreements --accept-package-agreements
    Refresh-Path

    # Try py launcher first (most reliable after fresh install)
    try {
        $pyPath = (& py -3.11 -c "import sys; print(sys.executable)" 2>&1).Trim()
        if (Test-Path $pyPath) {
            $pythonCmd = $pyPath
            Write-OK "Python 3.11 installed: $pyPath"
        }
    } catch { }

    # Fall back to python on PATH (but reject the Windows Store stub)
    if (-not $pythonCmd -and (Test-CommandExists "python")) {
        $verCheck = & python --version 2>&1
        if ($verCheck -match "Python \d+\.\d+") {
            $pythonCmd = "python"
            Write-OK "Python installed: $verCheck"
        } else {
            Write-Warn "Found 'python' on PATH but it is the Windows Store stub, not real Python."
            Write-Info "You may need to close and reopen PowerShell for PATH to update."
        }
    }

    if (-not $pythonCmd) {
        Write-Err "Python installation failed. Install Python 3.11 manually from python.org and re-run."
        Write-Err "IMPORTANT: Check 'Add to PATH' during installation."
        Write-Err "DO NOT install Python 3.14 -- it breaks required dependencies."
        exit 1
    }
}

# Verify pip
$pipCheck = & $pythonCmd -m pip --version 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Warn "pip not found. Bootstrapping..."
    & $pythonCmd -m ensurepip --upgrade
}
Write-OK "pip available"

# -----------------------------------------------------------------------------
# STEP 2 - GIT
# -----------------------------------------------------------------------------

Write-Step "2/10" "Git"

if (Test-CommandExists "git") {
    Write-OK "Found $(git --version 2>&1)"
} else {
    Write-Warn "Git not found. Installing via winget..."
    winget install Git.Git --source winget --accept-source-agreements --accept-package-agreements
    Refresh-Path

    if (Test-CommandExists "git") {
        Write-OK "Git installed: $(git --version 2>&1)"
    } else {
        Write-Err "Git installation failed. Install from https://git-scm.com and re-run."
        exit 1
    }
}

# -----------------------------------------------------------------------------
# STEP 3 - JAVA (for Tika)
# -----------------------------------------------------------------------------

Write-Step "3/10" "Java 21 (Eclipse Temurin - required by Apache Tika)"

$javaOK = $false
if (Test-CommandExists "java") {
    $javaVer = & java -version 2>&1 | Select-Object -First 1
    if ($javaVer -match '"(\d+)') {
        $javaMajor = [int]$Matches[1]
        if ($javaMajor -ge 11) {
            Write-OK "Found Java $javaMajor ($javaVer)"
            $javaOK = $true
        }
    }
}

if (-not $javaOK) {
    Write-Warn "Java 11+ not found. Installing Eclipse Temurin JDK 21..."
    winget install EclipseAdoptium.Temurin.21.JDK --source winget --accept-source-agreements --accept-package-agreements
    Refresh-Path

    if (Test-CommandExists "java") {
        Write-OK "Java installed: $(java -version 2>&1 | Select-Object -First 1)"
    } else {
        Write-Err "Java installation may require a shell restart."
        Write-Warn "Close and reopen PowerShell as Admin, then re-run this script."
        Write-Info "The script will pick up where it left off (already-installed tools are detected)."
        exit 1
    }
}

# -----------------------------------------------------------------------------
# STEP 4 - SYSTEM TOOLS (wkhtmltopdf, Tesseract, LibreOffice)
# -----------------------------------------------------------------------------

Write-Step "4/10" "System tools (wkhtmltopdf, Tesseract OCR, LibreOffice)"

# wkhtmltopdf
$wkPath = $null
foreach ($p in @(
    "C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe",
    "${env:ProgramFiles}\wkhtmltopdf\bin\wkhtmltopdf.exe",
    "${env:ProgramFiles(x86)}\wkhtmltopdf\bin\wkhtmltopdf.exe"
)) {
    if (Test-Path $p) { $wkPath = $p; break }
}

if ($wkPath) {
    Write-OK "wkhtmltopdf found: $wkPath"
} elseif (Test-CommandExists "wkhtmltopdf") {
    $wkPath = (Get-Command wkhtmltopdf).Source
    Write-OK "wkhtmltopdf found on PATH: $wkPath"
} else {
    Write-Warn "wkhtmltopdf not found. Attempting winget install..."

    # Try multiple known package IDs (winget catalog varies by machine/region)
    $wkInstalled = $false
    foreach ($pkgId in @("wkhtmltox.wkhtmltox", "wkhtmltopdf.wkhtmltopdf")) {
        Write-Info "Trying winget package: $pkgId"
        winget install $pkgId --source winget --accept-source-agreements --accept-package-agreements 2>&1 | Out-Null
        if ($LASTEXITCODE -eq 0) {
            $wkInstalled = $true
            break
        }
    }

    Refresh-Path
    $wkPath = "C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe"

    if (Test-Path $wkPath) {
        Write-OK "wkhtmltopdf installed: $wkPath"
    } elseif (-not $wkInstalled) {
        Write-Warn "wkhtmltopdf could not be installed via winget."
        Write-Warn "Manual install required:"
        Write-Host "    1. Download from: https://wkhtmltopdf.org/downloads.html" -ForegroundColor Yellow
        Write-Host "    2. Install the Windows (MSVC) 64-bit installer" -ForegroundColor Yellow
        Write-Host "    3. Default path: C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe" -ForegroundColor Yellow
        Write-Host "    4. Update WKHTMLTOPDF_PATH in config.py after install" -ForegroundColor Yellow
        Write-Host ""
        $wkPath = "C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe"
    } else {
        Write-Warn "wkhtmltopdf winget reported success but binary not at expected path."
        Write-Warn "You may need to update WKHTMLTOPDF_PATH in config.py manually."
        $wkPath = "C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe"
    }
}

# Tesseract
$tessPath = $null
foreach ($p in @(
    "C:\Program Files\Tesseract-OCR\tesseract.exe",
    "C:\Tesseract-OCR\tesseract.exe",
    "${env:ProgramFiles}\Tesseract-OCR\tesseract.exe"
)) {
    if (Test-Path $p) { $tessPath = $p; break }
}

if ($tessPath) {
    Write-OK "Tesseract found: $tessPath"
} elseif (Test-CommandExists "tesseract") {
    $tessPath = (Get-Command tesseract).Source
    Write-OK "Tesseract found on PATH: $tessPath"
} else {
    Write-Warn "Tesseract OCR not found. Installing..."
    winget install UB-Mannheim.TesseractOCR --source winget --accept-source-agreements --accept-package-agreements
    Refresh-Path
    $tessPath = "C:\Program Files\Tesseract-OCR\tesseract.exe"
    if (Test-Path $tessPath) {
        Write-OK "Tesseract installed: $tessPath"
    } else {
        Write-Warn "Tesseract installed but path not confirmed. You may need to update config.py manually."
        $tessPath = "C:\Program Files\Tesseract-OCR\tesseract.exe"
    }
}

# LibreOffice (strongly recommended - used for high-fidelity Office-to-PDF conversion)
$librePath = $null
foreach ($p in @(
    "C:\Program Files\LibreOffice\program\soffice.exe",
    "${env:ProgramFiles}\LibreOffice\program\soffice.exe",
    "${env:ProgramFiles(x86)}\LibreOffice\program\soffice.exe"
)) {
    if (Test-Path $p) { $librePath = $p; break }
}

if ($librePath) {
    Write-OK "LibreOffice found: $librePath"
} else {
    Write-Warn "LibreOffice not found (strongly recommended for Office-to-PDF conversion)."
    Write-Info "Without it, Office documents will use mammoth fallback (lower fidelity PDFs)."
    if (Get-UserConfirmation "Install LibreOffice now? (~350 MB download)") {
        winget install TheDocumentFoundation.LibreOffice --source winget --accept-source-agreements --accept-package-agreements
        Refresh-Path
        $librePath = "C:\Program Files\LibreOffice\program\soffice.exe"
        if (Test-Path $librePath) {
            Write-OK "LibreOffice installed: $librePath"
        } else {
            Write-Warn "LibreOffice installed but path not confirmed. Update LIBREOFFICE_PATH in config.py manually."
            $librePath = "C:\Program Files\LibreOffice\program\soffice.exe"
        }
    } else {
        Write-Info "Skipped. You can install later: winget install TheDocumentFoundation.LibreOffice"
        $librePath = ""
    }
}

# -----------------------------------------------------------------------------
# STEP 5 - APACHE TIKA SERVER
# -----------------------------------------------------------------------------

Write-Step "5/10" "Apache Tika Server $($Config.TikaVersion)"

$tikaDir = Join-Path $Config.ToolsDir "tika"
$tikaJar = Join-Path $tikaDir "tika-server-standard-$($Config.TikaVersion).jar"

if (Test-Path $tikaJar) {
    Write-OK "Tika JAR already present: $tikaJar"
} else {
    Write-Info "Downloading Apache Tika Server $($Config.TikaVersion)..."
    New-Item -ItemType Directory -Path $tikaDir -Force | Out-Null

    $tikaURL = "https://downloads.apache.org/tika/$($Config.TikaVersion)/tika-server-standard-$($Config.TikaVersion).jar"
    $tikaBackupURL = "https://archive.apache.org/dist/tika/$($Config.TikaVersion)/tika-server-standard-$($Config.TikaVersion).jar"

    $downloaded = $false
    try {
        Write-Info "Trying primary mirror..."
        Invoke-WebRequest -Uri $tikaURL -OutFile $tikaJar -UseBasicParsing
        $downloaded = $true
    } catch {
        Write-Warn "Primary mirror failed. Trying Apache archive..."
        try {
            Invoke-WebRequest -Uri $tikaBackupURL -OutFile $tikaJar -UseBasicParsing
            $downloaded = $true
        } catch {
            Write-Err "Could not download Tika automatically."
        }
    }

    if ($downloaded -and (Test-Path $tikaJar)) {
        $size = (Get-Item $tikaJar).Length / 1MB
        Write-OK "Tika downloaded ($([math]::Round($size, 1)) MB): $tikaJar"
    } else {
        Write-Err "Tika download failed."
        Write-Info "Manual download: https://tika.apache.org/download.html"
        Write-Info "Place the JAR at: $tikaJar"
    }
}

# Create Tika launch script
$tikaLauncher = Join-Path $tikaDir "start-tika.bat"
if (-not (Test-Path $tikaLauncher)) {
    @"
@echo off
echo Starting Apache Tika Server on port 9998...
echo Press Ctrl+C to stop.
java -jar "$tikaJar" --host 0.0.0.0 --port 9998
"@ | Out-File -FilePath $tikaLauncher -Encoding ASCII
    Write-OK "Created Tika launcher: $tikaLauncher"
}

# -----------------------------------------------------------------------------
# STEP 6 - OPENSEARCH
# -----------------------------------------------------------------------------

Write-Step "6/10" "OpenSearch $($Config.OpenSearchVersion)"

$osDir = Join-Path $Config.ToolsDir "opensearch-$($Config.OpenSearchVersion)"

if (Test-Path (Join-Path $osDir "bin\opensearch.bat")) {
    Write-OK "OpenSearch already present: $osDir"
} else {
    Write-Info "Downloading OpenSearch $($Config.OpenSearchVersion)..."
    $osZip = Join-Path $Config.ToolsDir "opensearch-$($Config.OpenSearchVersion)-windows-x64.zip"
    $osURL = "https://artifacts.opensearch.org/releases/bundle/opensearch/$($Config.OpenSearchVersion)/opensearch-$($Config.OpenSearchVersion)-windows-x64.zip"

    $downloaded = $false
    try {
        Start-BitsTransfer -Source $osURL -Destination $osZip -Description "Downloading OpenSearch..."
        $downloaded = $true
    } catch {
        Write-Warn "BITS transfer failed. Trying WebRequest (this may take a while)..."
        try {
            Invoke-WebRequest -Uri $osURL -OutFile $osZip -UseBasicParsing
            $downloaded = $true
        } catch {
            Write-Err "Could not download OpenSearch automatically."
        }
    }

    if ($downloaded -and (Test-Path $osZip)) {
        Write-Info "Extracting OpenSearch (this takes a minute)..."
        Expand-Archive -Path $osZip -DestinationPath $Config.ToolsDir -Force
        Remove-Item $osZip -Force
        Write-OK "OpenSearch extracted to: $osDir"
    } else {
        Write-Err "OpenSearch download failed."
        Write-Info "Manual download: https://opensearch.org/downloads.html"
        Write-Info "Extract to: $osDir"
    }
}

# Configure OpenSearch - disable security plugin (local deployment, no auth)
$osConfigFile = Join-Path $osDir "config\opensearch.yml"
if (Test-Path $osConfigFile) {
    $osConfig = Get-Content $osConfigFile -Raw
    if ($osConfig -notmatch "plugins\.security\.disabled\s*:\s*true") {
        Write-Info "Configuring OpenSearch (disabling security plugin for local use)..."
        $additions = @"

# --- DIY eDiscovery Hub - Local deployment settings ---
plugins.security.disabled: true
discovery.type: single-node
network.host: 0.0.0.0
"@
        Add-Content -Path $osConfigFile -Value $additions
        Write-OK "OpenSearch configured for local single-node deployment"
    } else {
        Write-OK "OpenSearch already configured"
    }
} else {
    Write-Warn "OpenSearch config file not found at expected location."
    Write-Info "You may need to configure it manually after extraction."
}

# Create OpenSearch launch script
$osLauncher = Join-Path $osDir "start-opensearch.bat"
if (-not (Test-Path $osLauncher)) {
    @"
@echo off
echo Starting OpenSearch on port 9200...
echo Press Ctrl+C to stop.
cd /d "$osDir"
bin\opensearch.bat
"@ | Out-File -FilePath $osLauncher -Encoding ASCII
    Write-OK "Created OpenSearch launcher: $osLauncher"
}

# -----------------------------------------------------------------------------
# STEP 7 - CLONE REPOSITORY
# -----------------------------------------------------------------------------

Write-Step "7/10" "Project Repository"

if (Test-Path (Join-Path $Config.ProjectDir "home.py")) {
    Write-OK "Project already exists at $($Config.ProjectDir)"
} else {
    $repoURL = $Config.GitRepoURL
    if (-not $repoURL) {
        Write-Host ""
        Write-Host "  Enter the Git repository URL for the eDiscovery project." -ForegroundColor White
        Write-Host "  (e.g., https://github.com/yourname/ediscovery.git)" -ForegroundColor Gray
        Write-Host "  Or enter a local path to copy from (e.g., D:\Backup\ediscovery)" -ForegroundColor Gray
        Write-Host ""
        $repoURL = Read-Host "  Repository URL or path"
    }

    if (Test-Path $repoURL) {
        Write-Info "Copying from local path..."
        Copy-Item -Path $repoURL -Destination $Config.ProjectDir -Recurse -Force
        Write-OK "Project copied to $($Config.ProjectDir)"
    } elseif ($repoURL) {
        Write-Info "Cloning repository..."
        git clone $repoURL $Config.ProjectDir
        if ($LASTEXITCODE -eq 0) {
            Write-OK "Repository cloned to $($Config.ProjectDir)"
        } else {
            Write-Err "git clone failed. Check the URL and your network connection."
            Write-Info "You can manually clone and re-run this script -- it will pick up from here."
            exit 1
        }
    } else {
        Write-Err "No repository URL provided. Create the project directory manually and re-run."
        exit 1
    }
}

# Branch selection + checkout
Push-Location $Config.ProjectDir

$targetBranch = $Config.Branch

if (-not $targetBranch) {
    # List remote branches for user selection
    $remoteBranches = git branch -r --list "origin/*" 2>&1 |
        ForEach-Object { $_.Trim() -replace "^origin/", "" } |
        Where-Object { $_ -and $_ -notmatch "HEAD" }

    if ($remoteBranches.Count -gt 0) {
        Write-Host ""
        Write-Host "  Available branches:" -ForegroundColor White
        for ($i = 0; $i -lt $remoteBranches.Count; $i++) {
            $marker = if ($remoteBranches[$i] -eq "beta-2.7") { " (recommended)" } else { "" }
            Write-Host "    [$($i+1)] $($remoteBranches[$i])$marker" -ForegroundColor Gray
        }
        Write-Host ""
        $branchInput = Read-Host "  Select branch number (default: 1)"
        if (-not $branchInput) { $branchInput = "1" }
        $idx = [int]$branchInput - 1
        if ($idx -ge 0 -and $idx -lt $remoteBranches.Count) {
            $targetBranch = $remoteBranches[$idx]
        } else {
            $targetBranch = $remoteBranches[0]
            Write-Warn "Invalid selection. Using $targetBranch"
        }
    } else {
        Write-Warn "No remote branches found. Staying on default branch."
        $targetBranch = $null
    }
}

if ($targetBranch) {
    Write-Info "Checking out branch: $targetBranch"
    git checkout $targetBranch 2>&1 | Out-Null
    if ($LASTEXITCODE -eq 0) {
        Write-OK "Checked out branch: $targetBranch"
    } else {
        Write-Warn "Could not checkout '$targetBranch'. Continuing on current branch."
        Write-Info "You can switch manually later: git checkout $targetBranch"
    }
}

Pop-Location

# -----------------------------------------------------------------------------
# STEP 8 - PYTHON VIRTUAL ENVIRONMENT + DEPENDENCIES
# -----------------------------------------------------------------------------

Write-Step "8/10" "Python virtual environment and dependencies"

$venvDir  = Join-Path $Config.ProjectDir ".venv"
$venvPip  = Join-Path $venvDir "Scripts\pip.exe"
$venvPy   = Join-Path $venvDir "Scripts\python.exe"
$reqFile  = Join-Path $Config.ProjectDir "requirements.txt"

if (Test-Path $venvPy) {
    Write-OK "Virtual environment already exists"
} else {
    Write-Info "Creating virtual environment..."
    & $pythonCmd -m venv $venvDir
    if (Test-Path $venvPy) {
        Write-OK "Virtual environment created at $venvDir"
    } else {
        Write-Err "Failed to create virtual environment."
        exit 1
    }
}

# Upgrade pip inside venv
Write-Info "Upgrading pip..."
& $venvPy -m pip install --upgrade pip --quiet

# Install requirements
if (Test-Path $reqFile) {
    Write-Info "Installing Python dependencies (this may take a few minutes)..."
    & $venvPip install -r $reqFile
    if ($LASTEXITCODE -eq 0) {
        Write-OK "All Python dependencies installed"
    } else {
        Write-Warn "Some dependencies may have failed. Check the output above."
        Write-Info "You can retry with: $venvPip install -r $reqFile"
    }
} else {
    Write-Err "requirements.txt not found at $reqFile"
    Write-Info "Make sure the repository was cloned correctly."
}

# -----------------------------------------------------------------------------
# STEP 9 - GENERATE config.py
# -----------------------------------------------------------------------------

Write-Step "9/10" "Machine-specific configuration (config.py)"

$configFile = Join-Path $Config.ProjectDir "config.py"

if (Test-Path $configFile) {
    Write-Warn "config.py already exists. Skipping generation."
    Write-Info "Review it manually to ensure paths are correct for this machine."
} else {
    # Prompt for cases root
    Write-Host ""
    Write-Host "  Where should case data be stored?" -ForegroundColor White
    Write-Host "  This is the root folder where all case subfolders will live." -ForegroundColor Gray
    Write-Host "  Default: $($Config.CasesRoot)" -ForegroundColor Gray
    Write-Host ""
    $casesInput = Read-Host "  Cases root (press Enter for default)"
    if (-not $casesInput) { $casesInput = $Config.CasesRoot }

    # Create cases root if it doesn't exist
    if (-not (Test-Path $casesInput)) {
        New-Item -ItemType Directory -Path $casesInput -Force | Out-Null
        Write-OK "Created cases directory: $casesInput"
    }

    # Prompt for Filevine subdomain (optional)
    Write-Host ""
    Write-Host "  Filevine subdomain (e.g., 'my-firm' for my-firm.filevine.com)" -ForegroundColor White
    Write-Host "  Press Enter to skip if not using Filevine." -ForegroundColor Gray
    $fvSubdomain = Read-Host "  Filevine subdomain"
    if (-not $fvSubdomain) { $fvSubdomain = "your-firm" }

    $configContent = @"
# Centralized Configuration for DIY E-Discovery Hub
# OpenSearch runs locally without authentication (plugins.security.disabled: true).
#
# This file was auto-generated by Deploy-Platform.ps1 on $(Get-Date -Format 'yyyy-MM-dd').
# Update paths below if you move any services.

__version__ = "2.9.0"
__branch__ = "$(if ($targetBranch) { $targetBranch } else { 'beta-2.8' })"

TIKA_ENDPOINT = "http://localhost:9998/tika"
TIKA_TIMEOUT = 1800

# OpenSearch connection
OS_HOST = "http://localhost:9200"

# --- Machine-Specific Service Paths ---
TIKA_JAR = r"$tikaJar"
OPENSEARCH_HOME = r"$osDir"

# Root directory where all case folders live.
CASES_ROOT = r"$casesInput"

# --- Third-Party Tool Paths ---
WKHTMLTOPDF_PATH = r"$wkPath"
TESSERACT_PATH = r"$tessPath"
LIBREOFFICE_PATH = r"$librePath"

# --- Performance Tuning ---
# Maximum parallel imaging workers for Production Pass 1.
# 0 = auto-detect: min(4, cpu_count - 1). Set explicitly for fixed deployments.
IMAGING_WORKERS = 0

# --- Filevine Integration ---
FILEVINE_SUBDOMAIN = "$fvSubdomain"
"@

    $configContent | Out-File -FilePath $configFile -Encoding UTF8
    Write-OK "Generated config.py with machine-specific paths"
}

# -----------------------------------------------------------------------------
# STEP 10 - POST-INSTALL PATCHES + VALIDATION
# -----------------------------------------------------------------------------

Write-Step "10/10" "Post-install patches and validation"

# Apply the streamlit-drawable-canvas patch if the patch script exists
$patchScript = Join-Path $Config.ProjectDir "_scratchpad\post_install_patch.py"
if (Test-Path $patchScript) {
    Write-Info "Applying streamlit-drawable-canvas patch..."
    & $venvPy $patchScript
    if ($LASTEXITCODE -eq 0) {
        Write-OK "Canvas patch applied"
    } else {
        Write-Warn "Canvas patch may have failed. Check output above."
    }
} else {
    Write-Info "Canvas patch script not found -- skipping (may not be needed)."
}

# Run setup_check.py
$setupCheck = Join-Path $Config.ProjectDir "setup_check.py"
if (Test-Path $setupCheck) {
    Write-Host ""
    Write-Banner "Running Platform Environment Validation"
    Write-Host ""
    Write-Info "NOTE: Tika and OpenSearch must be RUNNING for these checks to pass."
    Write-Info "Start them in separate terminals first if you haven't already:"
    Write-Host ""
    Write-Host "  Terminal 1:  $tikaLauncher" -ForegroundColor Cyan
    Write-Host "  Terminal 2:  $osLauncher" -ForegroundColor Cyan
    Write-Host ""

    if (Get-UserConfirmation "Run setup_check.py now?") {
        Push-Location $Config.ProjectDir
        & $venvPy $setupCheck
        Pop-Location
    } else {
        Write-Info "Skipped. Run it later with:"
        Write-Host "  cd $($Config.ProjectDir)" -ForegroundColor Cyan
        Write-Host "  .venv\Scripts\python setup_check.py" -ForegroundColor Cyan
    }
}

# -----------------------------------------------------------------------------
# CREATE CONVENIENCE LAUNCHERS
# -----------------------------------------------------------------------------

Write-Banner "Creating convenience launchers"

# Start-Services.bat - launches Tika + OpenSearch in background
$svcLauncher = Join-Path $Config.ProjectDir "Start-Services.bat"
if (-not (Test-Path $svcLauncher)) {
    @"
@echo off
echo ============================================================
echo  DIY eDiscovery Hub - Starting Background Services
echo ============================================================
echo.
echo Starting OpenSearch...
start "OpenSearch" cmd /c "cd /d "$osDir" && bin\opensearch.bat"
echo Waiting 15 seconds for OpenSearch to initialize...
timeout /t 15 /nobreak >nul
echo.
echo Starting Apache Tika Server...
start "Tika Server" cmd /c "java -jar "$tikaJar" --host 0.0.0.0 --port 9998"
echo Waiting 10 seconds for Tika to initialize...
timeout /t 10 /nobreak >nul
echo.
echo ============================================================
echo  Services started. You can now launch the platform.
echo  To stop services, close the OpenSearch and Tika windows.
echo ============================================================
echo.
pause
"@ | Out-File -FilePath $svcLauncher -Encoding ASCII
    Write-OK "Created: Start-Services.bat"
}

# Start-Platform.bat - activates venv and runs streamlit
$appLauncher = Join-Path $Config.ProjectDir "Start-Platform.bat"
if (-not (Test-Path $appLauncher)) {
    @"
@echo off
echo ============================================================
echo  DIY eDiscovery Hub - Launching Platform
echo ============================================================
echo.
cd /d "$($Config.ProjectDir)"
call .venv\Scripts\activate.bat
echo Starting Streamlit...
streamlit run home.py --server.address 0.0.0.0 --server.port 8501
"@ | Out-File -FilePath $appLauncher -Encoding ASCII
    Write-OK "Created: Start-Platform.bat"
}

# -----------------------------------------------------------------------------
# SUMMARY
# -----------------------------------------------------------------------------

Write-Banner "Deployment Summary"

Write-Host "  Component              Location" -ForegroundColor White
Write-Host "  ---------------------  --------------------------------------" -ForegroundColor Gray
Write-Host "  Project                $($Config.ProjectDir)" -ForegroundColor Green
Write-Host "  Python venv            $venvDir" -ForegroundColor Green
Write-Host "  Tika Server JAR        $tikaJar" -ForegroundColor Green
Write-Host "  OpenSearch             $osDir" -ForegroundColor Green
Write-Host "  wkhtmltopdf            $wkPath" -ForegroundColor Green
Write-Host "  Tesseract OCR          $tessPath" -ForegroundColor Green
if ($librePath) {
    Write-Host "  LibreOffice            $librePath" -ForegroundColor Green
} else {
    Write-Host "  LibreOffice            (not installed -- mammoth fallback active)" -ForegroundColor Yellow
}
Write-Host "  Cases Root             $($Config.CasesRoot)" -ForegroundColor Green
Write-Host ""
Write-Host "  --- Quick Start ---" -ForegroundColor Yellow
Write-Host ""
Write-Host "  1. Start services:     $svcLauncher" -ForegroundColor Cyan
Write-Host "  2. Launch platform:    $appLauncher" -ForegroundColor Cyan
Write-Host "  3. Open browser:       http://localhost:8501" -ForegroundColor Cyan
Write-Host ""
Write-Host "  --- First-Time Setup ---" -ForegroundColor Yellow
Write-Host ""
Write-Host "  After launching, log in with the default admin credentials" -ForegroundColor White
Write-Host "  from auth_config.yaml, then create user accounts via the" -ForegroundColor White
Write-Host "  User Management panel on the Home page." -ForegroundColor White
Write-Host ""
Write-Host "  --- Validation ---" -ForegroundColor Yellow
Write-Host ""
Write-Host "  Run the environment check at any time:" -ForegroundColor White
Write-Host "  cd $($Config.ProjectDir)" -ForegroundColor Cyan
Write-Host "  .venv\Scripts\python setup_check.py" -ForegroundColor Cyan
Write-Host ""

Write-Banner "Deployment Complete"
