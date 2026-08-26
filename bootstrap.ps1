# Molt Agent Drop Windows source bootstrap.
# ASCII-only and compatible with Windows PowerShell 5.1.
[CmdletBinding()]
param(
  [string]$InstallRoot = (Join-Path $env:LOCALAPPDATA 'MoltDropDemo\source'),
  [switch]$Force
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$repoOwner = 'zhou-zhou-1001'
$repoName = 'molt-agent-drop'
$repoRef = 'main'
$minimumZipBytes = 10000
$requiredFiles = @('molt.ps1', 'bootstrap_python.ps1', 'run_drop_host.ps1', 'drop_host.py', 'drop_client.py')

function Fail([string]$Message) {
  throw "Molt source bootstrap failed: $Message"
}

function Enable-Tls12 {
  $tls12 = [Net.SecurityProtocolType]::Tls12
  [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor $tls12
}

function New-WebClient {
  $client = New-Object Net.WebClient
  $client.Headers['User-Agent'] = 'Molt-Agent-Drop-Bootstrap'
  $client.Headers['Accept'] = 'application/vnd.github+json'
  return $client
}

function Get-Commit {
  $url = "https://api.github.com/repos/$repoOwner/$repoName/commits/$repoRef"
  $client = New-WebClient
  try {
    try {
      $body = $client.DownloadString($url)
    } catch {
      Write-Warning "commit API unavailable ($($_.Exception.Message)); using ref '$repoRef'"
      return $repoRef
    }
  } finally {
    $client.Dispose()
  }
  # Windows PowerShell 5.1 ConvertFrom-Json can fail on the large GitHub
  # commit document (especially when it contains patch text). Extract only
  # the top-level SHA instead of parsing the entire response.
  $match = [regex]::Match($body, '"sha"\s*:\s*"([0-9a-f]{40})"')
  if (-not $match.Success) { Fail 'GitHub response did not contain a valid commit id.' }
  $commit = $match.Groups[1].Value
  if ($commit -notmatch '^[0-9a-f]{40}$') { Fail 'GitHub returned an invalid commit id.' }
  return $commit
}

function Download-Zip([string]$Url, [string]$Path) {
  $request = [Net.HttpWebRequest]::Create($Url)
  $request.Method = 'GET'
  $request.UserAgent = 'Molt-Agent-Drop-Bootstrap'
  $request.AllowAutoRedirect = $true
  $request.Timeout = 30000
  $request.ReadWriteTimeout = 120000
  $response = $null
  $input = $null
  $output = $null
  try {
    $response = [Net.HttpWebResponse]$request.GetResponse()
    if ([int]$response.StatusCode -ne 200) { Fail "download returned HTTP $([int]$response.StatusCode)." }
    $declaredLength = $response.ContentLength
    $input = $response.GetResponseStream()
    $output = [IO.File]::Open($Path, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
    $buffer = New-Object byte[] 65536
    $count = 0L
    while (($read = $input.Read($buffer, 0, $buffer.Length)) -gt 0) {
      $output.Write($buffer, 0, $read)
      $count += $read
    }
    $output.Flush()
    if ($count -lt $minimumZipBytes) { Fail "download was too small ($count bytes)." }
    if ($declaredLength -ge 0 -and $count -ne $declaredLength) { Fail "download was incomplete ($count of $declaredLength bytes)." }
  } finally {
    if ($output) { $output.Dispose() }
    if ($input) { $input.Dispose() }
    if ($response) { $response.Dispose() }
  }
}

function Validate-Zip([string]$Path, [string]$ExpectedRoot) {
  Add-Type -AssemblyName System.IO.Compression.FileSystem
  $archive = [IO.Compression.ZipFile]::OpenRead($Path)
  try {
    if ($archive.Entries.Count -lt $requiredFiles.Count) { Fail 'ZIP contains too few entries.' }
    $names = @{}
    foreach ($entry in $archive.Entries) {
      $name = $entry.FullName.Replace('\', '/')
      if (-not $name.StartsWith($ExpectedRoot + '/', [StringComparison]::Ordinal)) { Fail "unexpected ZIP entry root: $name" }
      $relative = $name.Substring($ExpectedRoot.Length + 1)
      if ($relative -match '(^|/)\.\.(/|$)' -or $relative.StartsWith('/')) { Fail "unsafe ZIP entry: $name" }
      $names[$relative] = $true
    }
    foreach ($required in $requiredFiles) {
      if (-not $names.ContainsKey($required)) { Fail "ZIP is missing $required." }
    }
  } finally {
    $archive.Dispose()
  }
}

function Read-Marker([string]$Directory, [string]$Commit) {
  $markerPath = Join-Path $Directory '.molt-source.json'
  if (-not (Test-Path -LiteralPath $markerPath -PathType Leaf)) { return $false }
  try {
    $marker = Get-Content -LiteralPath $markerPath -Raw | ConvertFrom-Json
    return ($marker.repository -eq "$repoOwner/$repoName" -and $marker.commit -eq $Commit)
  } catch {
    return $false
  }
}

try {
  Enable-Tls12
  if ([string]::IsNullOrWhiteSpace($env:LOCALAPPDATA) -and $PSBoundParameters.ContainsKey('InstallRoot') -eq $false) {
    Fail 'LOCALAPPDATA is not set.'
  }
  New-Item -ItemType Directory -Force -Path $InstallRoot | Out-Null
  $commit = Get-Commit
  $installDir = Join-Path $InstallRoot $commit
  if (Test-Path -LiteralPath $installDir) {
    if (-not $Force -and (Read-Marker $installDir $commit)) {
      Write-Host "Molt source already verified: $installDir" -ForegroundColor Green
      & (Join-Path $installDir 'molt.ps1')
      if ($LASTEXITCODE -ne 0) { Fail "molt.ps1 failed with exit code $LASTEXITCODE." }
      return
    }
    if (-not $Force) { Fail "target exists without a matching marker: $installDir (rerun with -Force to replace only this commit directory)." }
    Remove-Item -LiteralPath $installDir -Recurse -Force
  }

  $work = Join-Path $InstallRoot ('.staging-' + [Guid]::NewGuid().ToString('N'))
  $zipPath = Join-Path $work 'source.zip'
  $extractDir = Join-Path $work 'extract'
  New-Item -ItemType Directory -Path $extractDir -Force | Out-Null
  try {
    Write-Host "Downloading Molt commit $commit..." -ForegroundColor Cyan
    Download-Zip "https://codeload.github.com/$repoOwner/$repoName/zip/$commit" $zipPath
    $zipHash = (Get-FileHash -LiteralPath $zipPath -Algorithm SHA256).Hash.ToLowerInvariant()
    $archiveRoot = "$repoName-$commit"
    Validate-Zip $zipPath $archiveRoot
    Expand-Archive -LiteralPath $zipPath -DestinationPath $extractDir
    $sourceDir = Join-Path $extractDir $archiveRoot
    foreach ($required in $requiredFiles) {
      if (-not (Test-Path -LiteralPath (Join-Path $sourceDir $required) -PathType Leaf)) { Fail "extracted source is missing $required." }
    }
    @{
      repository = "$repoOwner/$repoName"
      ref = $repoRef
      commit = $commit
      zip_sha256 = $zipHash
      installed_at = (Get-Date -Format o)
    } | ConvertTo-Json | Out-File -LiteralPath (Join-Path $sourceDir '.molt-source.json') -Encoding ascii
    Move-Item -LiteralPath $sourceDir -Destination $installDir
  } finally {
    if (Test-Path -LiteralPath $work) { Remove-Item -LiteralPath $work -Recurse -Force -ErrorAction SilentlyContinue }
  }

  if (-not (Read-Marker $installDir $commit)) { Fail 'published source marker validation failed.' }
  Write-Host "Molt source verified and installed: $installDir" -ForegroundColor Green
  & (Join-Path $installDir 'molt.ps1')
  if ($LASTEXITCODE -ne 0) { Fail "molt.ps1 failed with exit code $LASTEXITCODE." }
} catch {
  [Console]::Error.WriteLine($_.Exception.Message)
  throw
}
