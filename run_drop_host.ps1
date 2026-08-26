param(
  [Parameter(Mandatory=$true)][string]$Root,
  [string]$StateDir = (Join-Path $env:LOCALAPPDATA 'MoltDropDemo'),
  [int]$Port = 8765,
  [double]$InviteTtl = 10,
  [double]$SessionTtl = 60
)
$ErrorActionPreference = 'Stop'
# Resolve a working Python: reuse an existing one, or download the pinned
# official embeddable runtime into a private directory (SHA-256 verified).
$bootstrap = Join-Path $PSScriptRoot 'bootstrap_python.ps1'
$pythonPath = & $bootstrap
if ($LASTEXITCODE -ne 0 -or -not $pythonPath -or -not (Test-Path $pythonPath)) {
  throw 'Failed to resolve a Python runtime via bootstrap_python.ps1'
}
$python = Get-Item $pythonPath
# Embeddable Python ignores the script dir and PYTHONPATH when a ._pth file is
# present. Point the private runtime at the Molt script dir with a site-packages
# .pth entry (standard Python mechanism; scoped to this private runtime only).
$runtimeRoot = Split-Path $python.FullName -Parent
$sitePackages = Join-Path $runtimeRoot 'Lib\site-packages'
if (-not (Test-Path $sitePackages)) { New-Item -ItemType Directory -Force -Path $sitePackages | Out-Null }
$moltPth = Join-Path $sitePackages 'molt_drop.pth'
if (-not (Test-Path $moltPth) -or ((Get-Content $moltPth -Raw).Trim() -ne $PSScriptRoot)) {
  Set-Content -Path $moltPth -Value $PSScriptRoot -Encoding ascii
}
$hostScript = Join-Path $PSScriptRoot 'drop_host.py'
$args = @($hostScript, '--root', $Root, '--create-root', '--state-dir', $StateDir, '--port', $Port, '--invite-ttl', $InviteTtl, '--session-ttl', $SessionTtl)
Write-Host "Molt Drop Demo binds only 127.0.0.1; root=$Root; audit=$StateDir"
& $python.FullName @args
exit $LASTEXITCODE
