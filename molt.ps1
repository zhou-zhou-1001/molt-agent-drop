# Molt Drop first-run terminal wizard.
# This script intentionally guides; it does not open firewall ports or bypass SSH host-key checks.
[CmdletBinding()]
param(
  [ValidateSet('','host','agent')][string]$Role = '',
  [string]$Root = '',
  [string]$StateDir = '',
  [int]$Port = 8765
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
Header 'Molt Drop · first-run setup'
Say '把自己的 Agent 临时带到另一台电脑：明确授权、可审计、用完即走。'
Warn '这是安全 Demo：不会开放公网端口，不会关闭防火墙，也不会跳过 SSH host-key 校验。'
Write-Host ''
Write-Host '你现在是哪一端？'
Write-Host '  1. Host   文件所在的电脑（通常是 Windows）'
Write-Host '  2. Agent  运行 Agent 的电脑'
if (-not $Role) {
  $choice = Ask '请输入 1 或 2'
  if ($choice -eq '1') { $Role = 'host' } elseif ($choice -eq '2') { $Role = 'agent' } else { throw '请输入 1 或 2' }
}

$here = Split-Path -Parent $MyInvocation.MyCommand.Path
if ($Role -eq 'host') {
  Header 'Host 设置'
  if (-not $Root) { $Root = Ask '专用共享目录（不要填桌面、用户目录或真实业务目录）' 'C:\MoltDemoShare' }
  if (-not $StateDir) { $StateDir = Ask '私有状态目录（审计日志放这里）' "$env:LOCALAPPDATA\MoltDropDemo" }
  $python = $null
  $bootstrap = Join-Path $here 'bootstrap_python.ps1'
  Say '正在检查 Python；没有 Python 时会下载固定版本并校验 SHA-256……'
  $python = & $bootstrap
  if ($LASTEXITCODE -ne 0 -or -not $python -or -not (Test-Path ($python | Select-Object -Last 1))) { throw 'Python runtime 准备失败，已停止。' }
  $python = ($python | Select-Object -Last 1).ToString().Trim()
  Write-Host "Python: $python" -ForegroundColor Green
  Write-Host "共享目录: $Root"
  Write-Host "状态目录: $StateDir"
  $ok = Ask '确认创建/使用这个专用共享目录并启动 Host？输入 yes' 'no'
  if ($ok -ne 'yes') { Write-Host '已取消。'; exit 0 }
  Header 'Host 启动'
  Write-Host '启动后请把屏幕上的 MOLT_INVITATION_ID 和 SECRET，通过可信方式交给 Agent。' -ForegroundColor Green
  Write-Host 'Host 只监听 127.0.0.1；下一步需要你按文档建立已核验的 SSH tunnel。' -ForegroundColor Yellow
  & (Join-Path $here 'run_drop_host.ps1') -Root $Root -StateDir $StateDir -Port $Port
  exit $LASTEXITCODE
}

Header 'Agent 设置'
Say 'Agent 端不会自动连接陌生主机。请先确认 Host 管理员给你的 SSH host key 指纹。'
$url = Ask 'Tunnel 建立后，Agent 访问地址' 'http://127.0.0.1:18765'
$id = Ask 'Host 屏幕上的 MOLT_INVITATION_ID'
$secret = Ask 'Host 屏幕上的 MOLT_INVITATION_SECRET'
$label = Ask '给这次 Agent 取个名字' 'my-agent'
if ([string]::IsNullOrWhiteSpace($id) -or [string]::IsNullOrWhiteSpace($secret)) { throw 'Invitation ID/SECRET 不能为空。' }
Header '开始配对'
Say '即将发起一次性配对请求；Host 屏幕会显示 request id，必须由 Host Owner 明确批准。'
$client = Join-Path $here 'drop_client.py'
$py = Get-Command py -ErrorAction SilentlyContinue
if (-not $py) { $py = Get-Command python -ErrorAction SilentlyContinue }
if (-not $py) { throw 'Agent 端需要 Python 3。请先安装 Python 3，再重新运行本向导。' }
& $py.Source $client --url $url pair --invitation-id $id --invitation-secret $secret --label $label
Header '配对完成后的示例'
Write-Host "python drop_client.py --url $url --token TOKEN list ."
Write-Host "python drop_client.py --url $url --token TOKEN read hello.txt"
Write-Host "python drop_client.py --url $url --token TOKEN create agent-result.txt --content 'created by my agent'"
Warn 'TOKEN 只在当前终端使用，不要粘贴到聊天、Issue 或日志。结束后请让 Host 输入 revoke。'
