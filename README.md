# Molt Agent Drop Demo

这是一个真实可演示、但非生产级的跨机器 Agent Drop。Host 只监听 `127.0.0.1`；跨机器连接必须由用户显式建立 SSH tunnel。Python 3 标准库，无第三方依赖。

## 小白从这里开始：终端向导

不要先读完整文档。Host 和 Agent 都可以先运行统一向导：

macOS / Linux / Git Bash：

```bash
git clone https://github.com/zhou-zhou-1001/molt-agent-drop.git
cd molt-agent-drop
./molt
```

Windows PowerShell 5.1（推荐，不需要 Git 或 Python）：

```powershell
$ErrorActionPreference="Stop";[Net.ServicePointManager]::SecurityProtocol=[Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12;$u=@("https://cdn.jsdelivr.net/gh/zhou-zhou-1001/molt-agent-drop@main/bootstrap.ps1","https://raw.githubusercontent.com/zhou-zhou-1001/molt-agent-drop/main/bootstrap.ps1","https://github.com/zhou-zhou-1001/molt-agent-drop/raw/refs/heads/main/bootstrap.ps1");$s=$null;$last=$null;foreach($x in $u){try{$r=[Net.HttpWebRequest]::Create($x);$r.Method="GET";$r.UserAgent="Molt-Agent-Drop-Launcher";$r.Timeout=30000;$r.ReadWriteTimeout=30000;$p=[Net.HttpWebResponse]$r.GetResponse();if([int]$p.StatusCode -ne 200){throw "HTTP $([int]$p.StatusCode)"};$q=New-Object IO.StreamReader($p.GetResponseStream());$s=$q.ReadToEnd();$q.Dispose();$p.Dispose();if(-not [string]::IsNullOrEmpty($s)){break}}catch{$last=$_;if($p){$p.Dispose()}}};if([string]::IsNullOrEmpty($s) -or $s.Length -lt 1000 -or $s -match "[^\x00-\x7F]"){$z=Join-Path ([IO.Path]::GetTempPath()) ([IO.Path]::GetRandomFileName());$p=$null;$i=$null;$o=$null;$a=$null;$q=$null;try{$r=[Net.HttpWebRequest]::Create("https://codeload.github.com/zhou-zhou-1001/molt-agent-drop/zip/main");$r.Method="GET";$r.UserAgent="Molt-Agent-Drop-Launcher";$r.Timeout=30000;$r.ReadWriteTimeout=120000;$p=[Net.HttpWebResponse]$r.GetResponse();if([int]$p.StatusCode -ne 200){throw "HTTP $([int]$p.StatusCode)"};$i=$p.GetResponseStream();$o=[IO.File]::Open($z,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None);$i.CopyTo($o);$o.Dispose();$o=$null;$i.Dispose();$i=$null;$p.Dispose();$p=$null;[void][Reflection.Assembly]::LoadWithPartialName("System.IO.Compression.FileSystem");$a=[IO.Compression.ZipFile]::OpenRead($z);$e=$a.Entries|Where-Object {$_.FullName -match '(^|/)bootstrap[.]ps1$'}|Select-Object -First 1;if(-not $e){throw "bootstrap.ps1 missing from ZIP"};$q=New-Object IO.StreamReader($e.Open());$s=$q.ReadToEnd()}catch{$last=$_;$s=$null}finally{if($q){$q.Dispose()};if($a){$a.Dispose()};if($o){$o.Dispose()};if($i){$i.Dispose()};if($p){$p.Dispose()};if([IO.File]::Exists($z)){[IO.File]::Delete($z)}}};if([string]::IsNullOrEmpty($s) -or $s.Length -lt 1000 -or $s -match "[^\x00-\x7F]"){throw "Bootstrap download failed: $last"};& ([ScriptBlock]::Create($s))
```

整条命令只有一行，没有需要替换的占位符。请直接粘贴到已经打开的 Windows PowerShell 5.1；它依次尝试 jsDelivr 和两个 GitHub 脚本地址，前三源均无有效内容时从 codeload ZIP 读取 bootstrap。命令在当前进程内下载并执行 bootstrap，不启动子 `powershell.exe`，也不修改系统或用户的执行策略。launcher 会让错误立即停止、启用 TLS 1.2，并在执行前拒绝空白、过短或非 ASCII 的下载内容。`bootstrap.ps1` 会再次设置 TLS 1.2；GitHub commit API 可用时锁定 40 位 commit，不可用时警告并降级使用 `main`，随后下载 ZIP、检查 HTTP 状态、长度、ZIP 根目录和必需文件，再从随机 staging 目录发布到：

```text
%LOCALAPPDATA%\MoltDropDemo\source\main-or-40-character-commit
```

目录里的 `.molt-source.json` 记录 repository、commit 和 ZIP SHA-256；只有 marker 与目录 commit 一致才会启动向导。旧的 `%USERPROFILE%\molt-agent-drop` 不会被使用。任何下载、校验、解压或 Python 准备失败都会以非零状态立即停止，不会继续进入下一步。

失败后先直接重跑同一条命令；随机 staging 会被自动清理。若错误明确提示某个 commit 目录 marker 不匹配，可只清理 bootstrap 管理的 source cache 后重跑（不会删除共享目录或 audit state）：

```powershell
Remove-Item -LiteralPath "$env:LOCALAPPDATA\MoltDropDemo\source" -Recurse -Force
```

向导会先问你是哪一端：

- **Host**：选择专用共享目录，自动准备已校验的 Python，启动 Host，并显示一次性 invitation。
- **Agent**：输入 Host 给你的 invitation，发起配对；Host Owner 仍必须明确批准 request id。

向导不会开放公网端口、关闭防火墙或跳过 SSH host-key 校验。两台电脑之间仍需先按 [跨机器步骤](docs/demo-cross-machine.md) 建立已核验的 SSH tunnel。向导是 Demo 的友好入口，不是生产安装器。Windows 的 Host 和 Agent 分支都会自动准备固定版本 Python；macOS/Linux 的统一入口要求本机已有 Python 3。

## 自动获取 Python（bootstrap）

目标机没有 Python 也不怕：`bootstrap_python.ps1` 会自动检测 `py`/`python`，没有则用 PowerShell 5.1 自带的 `WebClient` 下载**固定版本**（默认 3.13.15 amd64）官方 embeddable 包到私有目录（`%LOCALAPPDATA%\MoltDropDemo\runtime`），**强制 SHA-256 校验**（多源 fallback，任一源下载后哈希不符即删除并换源，全部失败则 fail-closed），解压后修正 `python._pth` 并自检标准库，幂等（已验证的 runtime 直接复用）。不依赖 `curl.exe`，不改 PATH、不写注册表、不做全局安装。

## 能力与配对

Host 只开放结构化 `list`、读取 UTF-8 普通文本、排他 `create`。不支持覆盖、删除、shell、GUI、浏览器、摄像头、桌面控制或公网 Relay。

启动 Host（Windows 推荐用脚本）：

```powershell
Set-Location C:\demo\molt
.\run_drop_host.ps1 -Root C:\MoltDemoShare -StateDir "$env:LOCALAPPDATA\MoltDropDemo" -Port 8765
```

`-Root` 是 owner 明确指定/创建的专用目录。程序拒绝 filesystem/drive root、用户 home/profile 和 link/reparse root。audit 位于 root 外的私有 state directory。

Agent 通过 tunnel URL 发起请求：

```powershell
py -3 drop_client.py --url http://127.0.0.1:18765 pair --invitation-id ID --invitation-secret SECRET --label demo-agent
```

Host 控制台出现 request id 后，owner 必须现场输入：

```text
approve REQUEST_ID
```

自动化验收也可以加 `--owner-cmd-file C:\path\owner_cmd.txt`。该路径必须是 `-StateDir` 的直属文件，不能是 link/reparse point，且不能位于授权 root。发布方必须先在同目录写好权限受限的临时文件（POSIX 为 `0600`），内容恰好为一条以换行结尾的命令（例如 `approve REQUEST_ID`），再用原子 rename/replace 发布为指定文件名；Host 会原子认领并消费。不要直接向被轮询文件逐字追加。

`--owner-cmd-file` **仅是无人值守自动化验收辅助**，信任边界是 Host 本地 state directory 及其本机访问控制；它不验证操作者身份，不等同于生产身份认证或人工 owner 确认。生产或非受控多用户主机不要启用。

批准前文件 API 不可用。Agent 随后只收到一次明文 session token；Host 仅保留 SHA-256 hash。使用 token：

```powershell
py -3 drop_client.py --url http://127.0.0.1:18765 --token TOKEN list .
py -3 drop_client.py --url http://127.0.0.1:18765 --token TOKEN read hello.txt
py -3 drop_client.py --url http://127.0.0.1:18765 --token TOKEN create result.txt --content "demo result"
```

邀请过期或需要作废未完成的配对时，Host Owner 可输入 `new-invite`，Host 会审计并打印新的 `MOLT_INVITATION_ID` / `MOLT_INVITATION_SECRET`，重新开始一次性 10 分钟邀请窗口。Host 控制台也可输入 `revoke`、`freeze` 或按 Ctrl-C 停止。每次文件请求都会检查 session 状态和 TTL。

跨机器首选路径是让 Windows Host 使用系统自带 SSH 客户端，主动连接 Agent/Mac 并建立反向隧道：`ssh -R 18765:127.0.0.1:8765 USER@MAC_ADDRESS`。这样 Host 无需安装 Windows OpenSSH Server；仍须独立核对 Mac 的 host key，且不得使用 `StrictHostKeyChecking=no`。只有无法让 Host 主动连接 Agent 时，才考虑在 Host 安装 SSH Server 并使用传统 `-L` 转发。

跨机器完整步骤与 host-key 要求见 [docs/demo-cross-machine.md](docs/demo-cross-machine.md)。bootstrap 源自 [PythonEmbed4Win](https://github.com/jtmoon79/PythonEmbed4Win)（MIT，Copyright (c) 2022 James Thomas Moon），Molt 改造：固定版本 + 强制哈希校验 + 多源 fallback + 私有目录。

## Demo 限制（必须诚实说明）

- 这是演示协议，不是生产级配对、安全沙箱或 E2EE；HTTP 的机密性仅依赖用户正确建立的 SSH 通道。
- 没有 Windows handle-based root containment；使用路径规范化并拒绝 symlink/junction/reparse point，但不承诺抵抗本机并发换链等竞态攻击。
- 不能可靠获知某条 SSH tunnel 已断开。断开会阻止请求，但 session 在 Host 仍可能保持 active；每次请求检查 freeze/revoke/TTL，现场断线后应立即输入 `freeze` 或 `revoke`。
- session token 在 Agent 终端出现并由 Agent 进程持有。不要贴到聊天、命令历史或日志；audit 不记录 token。
- audit 写入失败时，授权/批准及 create 会 fail-closed。此 Demo 不提供抗篡改日志、账户隔离或管理员攻击防护。
- Windows 上 Python 标准库无法独立证明 state directory 的 DACL 是否只授予当前 owner；`--owner-cmd-file` 依赖 owner 事先用 Windows ACL 保护 `-StateDir`。Host 会拒绝 reparse point，POSIX 上还会拒绝 group/other 可访问的命令文件。
- `read` 仅接受最大 2 MB 的严格 UTF-8 普通文件；`create` 不自动创建父目录，也绝不覆盖已有文件。

## 测试

```powershell
py -3 -m py_compile drop_host.py drop_client.py test_drop.py
py -3 -m unittest -v test_drop.py
```
