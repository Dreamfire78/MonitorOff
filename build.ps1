# Builds dist\MonitorOff.exe (requires uv: https://docs.astral.sh/uv/)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

# Generate the icons from monitor_icon.svg
uv run --no-project --with-requirements requirements-build.txt python make_icon.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

uv run --no-project --with-requirements requirements-build.txt pyinstaller --noconfirm --clean --onefile --windowed `
    --name MonitorOff --icon monitor_off.ico `
    --add-data "monitor_off.ico;." --add-data "monitor_off_light.ico;." --add-data "monitor_off_dark.ico;." `
    --add-data "lang;lang" `
    monitor_off.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "Done: $PSScriptRoot\dist\MonitorOff.exe"
