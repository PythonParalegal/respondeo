<#
.SYNOPSIS
    Automated Dependency Installer for eDiscovery Platform
.DESCRIPTION
    This script downloads and installs all necessary external dependencies 
    required to run the eDiscovery platform, including Java, OpenSearch, 
    LibreOffice, wkhtmltopdf, and Python packages.
#>

Write-Host "======================================================" -ForegroundColor Cyan
Write-Host "  eDiscovery Platform — Dependency Setup Wizard" -ForegroundColor Cyan
Write-Host "======================================================" -ForegroundColor Cyan
Write-Host ""

# Require Run as Administrator for Winget and env variables
$IsAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $IsAdmin) {
    Write-Host "WARNING: This script is not running as Administrator." -ForegroundColor Yellow
    Write-Host "Some global installations (like wkhtmltopdf PATH variables) may fail." -ForegroundColor Yellow
    Write-Host "Please close this window and run PowerShell as Administrator if errors occur." -ForegroundColor Yellow
    Write-Host ""
}

# 1. Install Java (Required for Tika and OpenSearch)
Write-Host "[1/6] Checking Java Installation..." -ForegroundColor Blue
if (Get-Command java -ErrorAction SilentlyContinue) {
    Write-Host "  Java is already installed." -ForegroundColor Green
}
else {
    Write-Host "  Installing OpenJDK 21 via Winget..." -ForegroundColor Yellow
    winget install -e --id Microsoft.OpenJDK.21
    # Note: winget may require opening a new terminal to recognize the PATH change
}

# 2. Install LibreOffice (Headless PDF rendering for .docx/.xlsx)
Write-Host "`n[2/6] Checking LibreOffice Installation..." -ForegroundColor Blue
$LibreOfficePath = "C:\Program Files\LibreOffice\program\soffice.exe"
if (Test-Path $LibreOfficePath) {
    Write-Host "  LibreOffice is already installed." -ForegroundColor Green
}
else {
    Write-Host "  Installing LibreOffice via Winget..." -ForegroundColor Yellow
    winget install -e --id TheDocumentFoundation.LibreOffice --accept-package-agreements --accept-source-agreements
}

# 3. Install wkhtmltopdf (HTML rendering for .eml/.msg)
Write-Host "`n[3/6] Checking wkhtmltopdf Installation..." -ForegroundColor Blue
$WkhtmlPath = "C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe"
if (Test-Path $WkhtmlPath) {
    Write-Host "  wkhtmltopdf is already installed." -ForegroundColor Green
}
else {
    Write-Host "  Installing wkhtmltopdf via Winget..." -ForegroundColor Yellow
    winget install -e --id wkhtmltopdf.wkhtmltopdf --accept-package-agreements --accept-source-agreements
}

# 4. Download Apache Tika
Write-Host "`n[4/6] Setting up Apache Tika Server..." -ForegroundColor Blue
$TikaVer = "2.9.1"
$TikaUrl = "https://archive.apache.org/dist/tika/2.9.1/tika-server-standard-2.9.1.jar"
$TikaDest = ".\tika-server.jar"
if (Test-Path $TikaDest) {
    Write-Host "  Tika Server JAR is already present." -ForegroundColor Green
}
else {
    Write-Host "  Downloading Apache Tika Server v$TikaVer..." -ForegroundColor Yellow
    Invoke-WebRequest -Uri $TikaUrl -OutFile $TikaDest
    Write-Host "  Downloaded successfully." -ForegroundColor Green
}

# 5. Download and Extract OpenSearch
Write-Host "`n[5/6] Setting up OpenSearch..." -ForegroundColor Blue
$OSFolder = "C:\opensearch"
if (Test-Path "$OSFolder\bin\opensearch.bat") {
    Write-Host "  OpenSearch is already installed at $OSFolder." -ForegroundColor Green
}
else {
    Write-Host "  Downloading OpenSearch 2.11.1 (Windows zip)..." -ForegroundColor Yellow
    $OSZipUrl = "https://artifacts.opensearch.org/releases/bundle/opensearch/2.11.1/opensearch-2.11.1-windows-x64.zip"
    $OSZipDest = "$env:TEMP\opensearch.zip"
    Invoke-WebRequest -Uri $OSZipUrl -OutFile $OSZipDest
    
    Write-Host "  Extracting OpenSearch to C:\ ..." -ForegroundColor Yellow
    Expand-Archive -Path $OSZipDest -DestinationPath "C:\" -Force
    Rename-Item -Path "C:\opensearch-2.11.1" -NewName "opensearch" -ErrorAction SilentlyContinue
    
    # Configure OpenSearch defaults
    Write-Host "  Configuring opensearch.yml..." -ForegroundColor Yellow
    $OSYaml = "$OSFolder\config\opensearch.yml"
    Add-Content -Path $OSYaml -Value "`nplugins.security.disabled: true"
    Add-Content -Path $OSYaml -Value "discovery.type: single-node"
    
    # Cleanup zip
    Remove-Item $OSZipDest -Force
    Write-Host "  OpenSearch installed successfully." -ForegroundColor Green
}

# 6. Install Python Requirements
Write-Host "`n[6/6] Installing Python Packages..." -ForegroundColor Blue
if (Test-Path "requirements.txt") {
    pip install -r requirements.txt
    Write-Host "  PIP requirements installed successfully." -ForegroundColor Green
}
else {
    Write-Host "  WARNING: requirements.txt not found in current directory." -ForegroundColor Yellow
}

Write-Host "`n======================================================" -ForegroundColor Cyan
Write-Host "  Setup Complete! 🎉" -ForegroundColor Cyan
Write-Host "  NOTE: If Java was just installed, you may need to close and" -ForegroundColor Cyan
Write-Host "  restart PowerShell before running the platform." -ForegroundColor Cyan
Write-Host "======================================================" -ForegroundColor Cyan
