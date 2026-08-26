# Molt Drop first-run terminal wizard.
# This script intentionally guides; it does not open firewall ports or bypass SSH host-key checks.
[CmdletBinding()]
param(
  [ValidateSet('','host','agent')][string]$Role = '',
  [string]$Root = '',
  [string]$StateDir = '',
  [int]$Port = 8765,
  [switch]$EnableDiagnostics
)
$ErrorActionPreference = 'Stop'

function Say([string]$Text) { Write-Host $Text -ForegroundColor Cyan }
function Warn([string]$Text) { Write-Host $Text -ForegroundColor Yellow }
function Ask([string]$Prompt, [string]$Default='') {
  if ($Default) { $v = Read-Host "$Prompt [$Default]"; if ([string]::IsNullOrWhiteSpace($v)) { return $Default }; return $v }
  return Read-Host $Prompt
}
function Header([string]$Text) {
  Write-Host ''
  Write-Host ('=' * 64) -ForegroundColor DarkGray
  Write-Host "  $Text" -ForegroundColor White
  Write-Host ('=' * 64) -ForegroundColor DarkGray
}

Clear-Host
Header 'Molt Drop - first-run setup'
Say 'Bring your Agent to another computer: temporary, permissioned, auditable.'
Warn 'Safety demo: no public ports, no firewall changes, no SSH host-key bypass.'
Write-Host ''
Write-Host 'Which side is this computer?'
Write-Host '  1. Host   computer containing the files (usually Windows)'
Write-Host '  2. Agent  computer running the Agent'
if (-not $Role) {
  $choice = Ask 'Enter 1 or 2'
  if ($choice -eq '1') { $Role = 'host' } elseif ($choice -eq '2') { $Role = 'agent' } else { throw 'Enter 1 or 2' }
}

$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$pythonOutput = & (Join-Path $here 'bootstrap_python.ps1')
$pythonExit = $LASTEXITCODE
$python = @($pythonOutput | Select-Object -Last 1)[0]
if ($pythonExit -ne 0 -or [string]::IsNullOrWhiteSpace([string]$python) -or -not (Test-Path -LiteralPath $python -PathType Leaf)) {
  throw 'Python runtime setup failed; no role action was started.'
}
$python = ([string]$python).Trim()
Write-Host "Python: $python" -ForegroundColor Green
if ($Role -eq 'host') {
  Header 'Host setup'
  if (-not $Root) { $Root = Ask 'Dedicated share directory (never use Desktop, home, or real business files)' 'C:\MoltDemoShare' }
  if (-not $StateDir) { $StateDir = Ask 'Private state directory (audit log goes here)' "$env:LOCALAPPDATA\MoltDropDemo" }
  Write-Host "Share directory: $Root"
  Write-Host "State directory: $StateDir"
  $ok = Ask 'Create/use this dedicated directory and start Host? Type yes' 'no'
  if ($ok -ne 'yes') { Write-Host 'Cancelled.'; exit 0 }
  Header 'Host starting'
  Write-Host 'After startup, transfer MOLT_INVITATION_ID and SECRET to the Agent operator through a trusted channel.' -ForegroundColor Green
  Write-Host 'Host listens only on 127.0.0.1; next, create a verified SSH tunnel as documented.' -ForegroundColor Yellow
  $hostArgs = @('-Root', $Root, '-StateDir', $StateDir, '-Port', $Port)
  if ($EnableDiagnostics) { $hostArgs += '-EnableDiagnostics' }
  & (Join-Path $here 'run_drop_host.ps1') @hostArgs
  exit $LASTEXITCODE
}

Header 'Agent setup'
Say 'Agent will not connect to an unknown host automatically. Verify the Host SSH key fingerprint first.'
$url = Ask 'Agent URL after tunnel is established' 'http://127.0.0.1:18765'
$id = Ask 'MOLT_INVITATION_ID shown by Host'
$secret = Ask 'MOLT_INVITATION_SECRET shown by Host'
$label = Ask 'Name for this Agent session' 'my-agent'
if ([string]::IsNullOrWhiteSpace($id) -or [string]::IsNullOrWhiteSpace($secret)) { throw 'Invitation ID/SECRET cannot be empty.' }
Header 'Pairing'
Say 'Sending one-time pairing request; Host Owner must approve the request id on the Host screen.'
$client = Join-Path $here 'drop_client.py'
& $python $client --url $url pair --invitation-id $id --invitation-secret $secret --label $label
if ($LASTEXITCODE -ne 0) { throw "Pairing client failed with exit code $LASTEXITCODE." }
Header 'Examples after pairing'
Write-Host "python drop_client.py --url $url --token TOKEN list ."
Write-Host "python drop_client.py --url $url --token TOKEN read hello.txt"
Write-Host "python drop_client.py --url $url --token TOKEN create agent-result.txt --content 'created by my agent'"
Warn 'Use TOKEN only in this terminal; never paste it into chat, issues, or logs. Ask Host to type revoke when done.'
