# Installs a GitHub Actions self-hosted runner (label: israel) as a Windows service,
# so this home computer can download prices from chains that block non-Israeli servers.
# Run via setup.bat (it asks for administrator permission).
$ErrorActionPreference = "Stop"
$Repo     = "omrimalbin/supr-prices"
$Dir      = "C:\actions-runner-prices"
$PyDir    = "C:\Program Files\Python312"
$PyExe    = Join-Path $PyDir "python.exe"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

function Step($t) { Write-Host ""; Write-Host "==> $t" -ForegroundColor Cyan }

# 1. Python for all users (the runner service cannot see a per-user Python)
Step "Checking Python (all users)..."
if (-not (Test-Path $PyExe)) {
    $installer = Join-Path $env:TEMP "python-3.12-amd64.exe"
    Write-Host "Downloading Python 3.12..."
    Invoke-WebRequest "https://www.python.org/ftp/python/3.12.7/python-3.12.7-amd64.exe" -OutFile $installer -UseBasicParsing
    Write-Host "Installing Python (takes a minute)..."
    Start-Process $installer -Wait -ArgumentList "/quiet InstallAllUsers=1 PrependPath=1 Include_launcher=1 InstallLauncherAllUsers=1 Include_test=0"
    if (-not (Test-Path $PyExe)) { throw "Python installation failed. Install Python 3.12 for ALL USERS from python.org and run again." }
}
Write-Host "Python OK: $PyExe"

# 2. Download the GitHub Actions runner
Step "Downloading the GitHub runner..."
New-Item -ItemType Directory -Force -Path $Dir | Out-Null
Set-Location $Dir
if (-not (Test-Path (Join-Path $Dir "config.cmd"))) {
    $rel = Invoke-RestMethod "https://api.github.com/repos/actions/runner/releases/latest" -UseBasicParsing
    $asset = $rel.assets | Where-Object { $_.name -like "actions-runner-win-x64-*.zip" } | Select-Object -First 1
    $zip = Join-Path $env:TEMP $asset.name
    Invoke-WebRequest $asset.browser_download_url -OutFile $zip -UseBasicParsing
    Expand-Archive -Path $zip -DestinationPath $Dir -Force
}
# environment for the jobs
Set-Content -Path (Join-Path $Dir ".env") -Encoding ASCII -Value @("PRICES_PYTHON=`"$PyExe`"", "PYTHONUTF8=1")

# 3. Registration token from GitHub
Step "Connecting to GitHub"
$url = "https://github.com/$Repo/settings/actions/runners/new?arch=x64&os=win"
Write-Host "A GitHub page will open now. Scroll to the 'Configure' section and copy the token"
Write-Host "that appears after --token  (a long code of letters and digits)."
Start-Process $url
$token = (Read-Host "Paste the token here and press Enter").Trim()
if ($token -match "--token\s+(\S+)") { $token = $Matches[1] }
if (-not $token) { throw "No token entered." }

# 4. Register as a Windows service (starts automatically whenever the computer is on)
Step "Registering this computer and starting the service..."
& .\config.cmd --unattended --url "https://github.com/$Repo" --token $token `
    --name "home-$env:COMPUTERNAME" --labels israel --runasservice --replace
if ($LASTEXITCODE -ne 0) { throw "Registration failed (exit $LASTEXITCODE). The token may have expired - run again." }

Step "Done!"
Write-Host "This computer is now connected. Whenever it is on, it will download prices for"
Write-Host "Hazi Hinam, Victory, Carrefour, Mahsanei HaShuk, Super-Pharm and others."
Write-Host "Nothing else to do. You can close this window."
