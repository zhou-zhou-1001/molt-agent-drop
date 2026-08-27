[CmdletBinding()]
param(
  [Parameter(Mandatory=$true)][string]$Config,
  [switch]$Check
)
$ErrorActionPreference = 'Stop'
$bootstrap = Join-Path $PSScriptRoot 'bootstrap_python.ps1'
$pythonOutput = & $bootstrap
$pythonPath = @($pythonOutput | Select-Object -Last 1)[0]
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace([string]$pythonPath) -or -not (Test-Path -LiteralPath $pythonPath -PathType Leaf)) {
  throw 'Failed to resolve a Python runtime via bootstrap_python.ps1'
}
$pythonPath = ([string]$pythonPath).Trim()
$script = Join-Path $PSScriptRoot 'molt_tunnel.py'
$arguments = @($script, $Config)
if ($Check) { $arguments += '--check' }
& $pythonPath @arguments
exit $LASTEXITCODE
