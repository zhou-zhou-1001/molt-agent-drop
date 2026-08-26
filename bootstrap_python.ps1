# bootstrap_python.ps1 - Molt Drop demo Python runtime bootstrap
#
# Derived from PythonEmbed4Win (MIT, Copyright (c) 2022 James Thomas Moon)
#   https://github.com/jtmoon79/PythonEmbed4Win
# Modifications for Molt Drop:
#   * Pin an exact Python version (no "latest" tracking).
#   * Mandatory SHA-256 verification of the downloaded zip; fail closed on mismatch.
#   * Multi-source download with fallback (official python.org + mirrors); every
#     source is verified against the same pinned SHA-256, so a mirror cannot
#     substitute a tampered artifact. On mismatch the zip is deleted and the next
#     source is tried; if all fail, nothing is executed.
#   * Private runtime directory under %LOCALAPPDATA%; no PATH / registry / global install.
#   * No pip bootstrap (Molt host only needs Python standard library).
#   * Idempotent: reuses an already-verified runtime unless -Force is given.
#
# Behavior:
#   1. If a working system `py`/`python` exists, print its path and exit 0.
#   2. Otherwise download the pinned official python.org embeddable zip
#      (official first, then npmmirror, then huaweicloud).
#   3. Verify SHA-256 against the pinned value; mismatch => delete + next source.
#   4. Extract into a private runtime dir, fix python._pth, run a stdlib self-test.
#   5. Print the path to the verified python.exe.
#
# Exit codes: 0 = python path printed on stdout; 1 = failure (message on stderr).

param(
  [string]$Version = '3.13.15',
  [string]$Arch = 'amd64',
  [string]$RuntimeDir = (Join-Path $env:LOCALAPPDATA 'MoltDropDemo\runtime'),
  [switch]$Force
)

$ErrorActionPreference = 'Stop'
[Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12

function Write-Fail {
  param([string]$Msg)
  [Console]::Error.WriteLine("MoltBootstrap: $Msg")
  exit 1
}

# --- 1. Reuse an existing system Python if it actually works -----------------
$existing = Get-Command py -ErrorAction SilentlyContinue
if (-not $existing) { $existing = Get-Command python -ErrorAction SilentlyContinue }
if ($existing) {
  try {
    $ver = & $existing.Source -c "import sys; print(sys.version.split()[0])" 2>$null
    if ($LASTEXITCODE -eq 0 -and $ver) {
      Write-Host "MoltBootstrap: using existing Python $ver at $($existing.Source)"
      Write-Output $existing.Source
      exit 0
    }
  } catch { }
}

# --- 2. Architecture detection (only amd64 is pinned today) ------------------
$osArch = $env:PROCESSOR_ARCHITECTURE
if ($osArch -match 'ARM64') { $arch = 'arm64' }
elseif ($osArch -match 'AMD64|x64') { $arch = 'amd64' }
else { $arch = 'win32' }
if ($arch -ne 'amd64') {
  Write-Fail "this bootstrap pins amd64 only; detected arch=$arch (PROCESSOR_ARCHITECTURE=$osArch)"
}

# --- 3. Pinned official artifact, hash verified at download ------------------
# python-3.13.15-embed-amd64.zip. All sources below serve the identical file;
# the pinned SHA-256 below is the integrity anchor.
$expectedZipHash = 'd1f04d990aee1253d8569e8e5104e30fa9f5fa830899f14843448872d936a2cf'
$sources = @(
  "https://registry.npmmirror.com/-/binary/python/$Version/python-$Version-embed-$Arch.zip",
  "https://mirrors.huaweicloud.com/python/$Version/python-$Version-embed-$Arch.zip",
  "https://www.python.org/ftp/python/$Version/python-$Version-embed-$Arch.zip"
)

New-Item -ItemType Directory -Force -Path $RuntimeDir | Out-Null
$installDir = Join-Path $RuntimeDir "$Version-$Arch"
$pythonExe = Join-Path $installDir 'python.exe'
$markerFile = Join-Path $installDir '.molt-bootstrap.json'
$zipPath = Join-Path $RuntimeDir "python-$Version-embed-$Arch.zip"

# Reuse an already-verified runtime if marker matches the pinned hash.
if (-not $Force -and (Test-Path $pythonExe) -and (Test-Path $markerFile)) {
  try {
    $marker = Get-Content -Raw $markerFile | ConvertFrom-Json
    if ($marker.zip_sha256 -eq $expectedZipHash) {
      Write-Host "MoltBootstrap: verified runtime already present at $installDir"
      Write-Output $pythonExe
      exit 0
    }
  } catch { }
}

# --- 4. Download with a PowerShell 5.1-compatible WebClient -------------------
$zipOk = $false
foreach ($url in $sources) {
  Write-Host "MoltBootstrap: downloading $url"
  Remove-Item -Force $zipPath -ErrorAction SilentlyContinue
  try {
    $client = New-Object Net.WebClient
    $client.Headers['User-Agent'] = 'Molt-Agent-Drop-Python-Bootstrap'
    $client.DownloadFile($url, $zipPath)
  } catch {
    Write-Host "MoltBootstrap: source failed ($($_.Exception.Message)); trying next"
    Remove-Item -Force $zipPath -ErrorAction SilentlyContinue
    continue
  } finally {
    if ($client) { $client.Dispose(); $client = $null }
  }
  if (-not (Test-Path $zipPath)) {
    Write-Host 'MoltBootstrap: source produced no file; trying next'
    continue
  }
  $actualHash = (Get-FileHash -Algorithm SHA256 -Path $zipPath).Hash.ToLowerInvariant()
  if ($actualHash -ne $expectedZipHash) {
    Remove-Item -Force $zipPath -ErrorAction SilentlyContinue
    Write-Host "MoltBootstrap: SHA-256 mismatch (got $actualHash); zip deleted; trying next source"
    continue
  }
  $zipOk = $true
  break
}
if (-not $zipOk) { Write-Fail 'all download sources failed or failed hash verification; nothing executed' }

# --- 5. Extract into private runtime dir --------------------------------------
if (Test-Path $installDir) { Remove-Item -Recurse -Force $installDir }
New-Item -ItemType Directory -Force -Path $installDir | Out-Null
try {
  Expand-Archive -Path $zipPath -DestinationPath $installDir
} catch {
  Remove-Item -Recurse -Force $installDir -ErrorAction SilentlyContinue
  Write-Fail "extract failed: $($_.Exception.Message)"
}
Remove-Item -Force $zipPath

# --- 6. Fix python._pth (embeddable default only loads python3XX.zip + '.') --
$pth = Get-ChildItem -Path $installDir -Filter 'python*._pth' -File -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $pth) { $pthPath = Join-Path $installDir 'python._pth' } else { $pthPath = $pth.FullName }
$pthContent = @(
  "# python._pth (Molt Drop bootstrap; derived from PythonEmbed4Win, MIT)"
  "python313.zip"
  ".\DLLs"
  ".\Lib"
  "."
  ".\Lib\site-packages"
  "import site"
) -join "`n"
$pthContent | Out-File -FilePath $pthPath -Encoding ascii -Force

# --- 7. Self-test: standard library modules Molt host depends on --------------
# Two PowerShell 5.1 pitfalls avoided here:
#   1. Passing code with quotes via `-c` strips the quotes (NameError); so write a
#      temp .py file and execute the file instead.
#   2. With $ErrorActionPreference='Stop', native stderr becomes a terminating
#      NativeCommandError even with 2>$null; so run the test under 'Continue'
#      and judge by $LASTEXITCODE only.
$testPy = Join-Path $installDir 'molt_selftest.py'
@'
import http.server, json, hashlib, hmac, argparse, threading, secrets
print("molt-stdlib-ok")
'@ | Out-File -FilePath $testPy -Encoding ascii -Force
$prevEAP = $ErrorActionPreference
$ErrorActionPreference = 'Continue'
$testOut = & $pythonExe $testPy 2>&1 | Out-String
$testExit = $LASTEXITCODE
$ErrorActionPreference = $prevEAP
Remove-Item -Force $testPy -ErrorAction SilentlyContinue
if ($testExit -ne 0) {
  Remove-Item -Recurse -Force $installDir -ErrorAction SilentlyContinue
  Write-Fail "runtime self-test failed: $testOut"
}
Write-Host "MoltBootstrap: runtime self-test ok ($($testOut.Trim()))"

# --- 8. Marker + output --------------------------------------------------------
@{ version = $Version; arch = $arch; zip_sha256 = $expectedZipHash; installed_at = (Get-Date -Format o) } |
  ConvertTo-Json | Out-File -FilePath $markerFile -Encoding ascii -Force
Write-Host "MoltBootstrap: verified runtime at $installDir"
Write-Output $pythonExe
exit 0
