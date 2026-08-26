# Molt Drop 跨机器实机演示（推荐路径）

本文首选实机验证路径：**Windows Host 使用系统自带 SSH 客户端，向 Agent/Mac 建立反向隧道**。Windows Host 无需安装 OpenSSH Server，Molt 仍只监听本机回环地址。

```text
┌────────────── Agent 机器 ──────────────┐
│ SSH Server                             │
│ 127.0.0.1:18765  ◀──── SSH ─────┐      │
│ drop_client.py                   │      │
└──────────────────────────────────┼──────┘
                                   │
                         127.0.0.1:8765
┌────────────── Host 机器 ─────────┴──────┐
│ drop_host.py + Windows SSH client       │
│ 专用共享目录 + 审计日志                 │
└─────────────────────────────────────────┘
```

**不要把 8765 或 18765 开到公网，不要关闭防火墙，不要使用 `StrictHostKeyChecking=no`。**

## 0. 先准备两台机器

- **Host**：文件所在电脑。下面示例是 Windows。
- **Agent**：运行 Agent 的电脑，可以是 macOS、Linux 或另一台 Windows。
- Host 只需 Windows 自带的 OpenSSH **客户端**；不要先运行 `Add-WindowsCapability` 安装 OpenSSH Server。
- Agent/Mac 需开启 SSH Server（macOS 为“系统设置 → 通用 → 共享 → 远程登录”）。
- 你需要知道 Agent/Mac 的 SSH 用户名、地址，以及它的 SSH host key 指纹。

如果只是两台同一局域网电脑，也仍然建议走 SSH，不要改成明文 LAN HTTP。

## 1. 在 Host 机器启动 Molt

在 **Host 的 Windows PowerShell 5.1** 复制下面完整的一行。不需要先安装 Git 或 Python，也不要拆行或替换其中内容：

```powershell
$ErrorActionPreference="Stop";[Net.ServicePointManager]::SecurityProtocol=[Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12;$u=@("https://cdn.jsdelivr.net/gh/zhou-zhou-1001/molt-agent-drop@main/bootstrap.ps1","https://raw.githubusercontent.com/zhou-zhou-1001/molt-agent-drop/main/bootstrap.ps1","https://github.com/zhou-zhou-1001/molt-agent-drop/raw/refs/heads/main/bootstrap.ps1");$s=$null;$last=$null;foreach($x in $u){try{$r=[Net.HttpWebRequest]::Create($x);$r.Method="GET";$r.UserAgent="Molt-Agent-Drop-Launcher";$r.Timeout=30000;$r.ReadWriteTimeout=30000;$p=[Net.HttpWebResponse]$r.GetResponse();if([int]$p.StatusCode -ne 200){throw "HTTP $([int]$p.StatusCode)"};$q=New-Object IO.StreamReader($p.GetResponseStream());$s=$q.ReadToEnd();$q.Dispose();$p.Dispose();if(-not [string]::IsNullOrEmpty($s)){break}}catch{$last=$_;if($p){$p.Dispose()}}};if([string]::IsNullOrEmpty($s) -or $s.Length -lt 1000 -or $s -match "[^\x00-\x7F]"){throw "Bootstrap download failed: $last"};& ([ScriptBlock]::Create($s))
```

命令优先使用 jsDelivr CDN，GitHub 双地址作为回退；它直接在当前 Windows PowerShell 5.1 进程内运行，不启动子 `powershell.exe`，也不修改全局或用户执行策略。它会启用 TLS 1.2，并在下载异常、内容为空或过短、内容含非 ASCII 字符时立即停止。仓库 bootstrap 会先取得准确 commit，再校验下载状态、文件大小、ZIP 内容和 commit marker，只从随机 staging 发布完整目录。失败会立即停止，旧的 `%USERPROFILE%\molt-agent-drop` 不会被启动。

网络抖动时直接重跑同一条命令。若提示 commit 目录缺少或不匹配 marker，只删除 bootstrap 自己管理的 source cache，再重跑：

```powershell
Remove-Item -LiteralPath "$env:LOCALAPPDATA\MoltDropDemo\source" -Recurse -Force
```

不要删除 `%LOCALAPPDATA%\MoltDropDemo` 整体，因为其中还可能有 runtime 和 audit state。选择 `1. Host`，接受一个**专用、无敏感文件**的共享目录，例如：

```text
C:\MoltDemoShare
```

不要选择桌面、整个用户目录、下载目录、项目目录或真实业务目录。

向导会自动准备 Python 并启动 Host。记下屏幕上的三项信息：

```text
MOLT_URL=http://127.0.0.1:8765
MOLT_INVITATION_ID=...
MOLT_INVITATION_SECRET=...
```

Host 窗口必须保持打开。Host 端口只绑定 `127.0.0.1`，不需要开放入站 8765。

## 2. 独立核对 Agent/Mac 的 SSH host key（必须）

在 Agent/Mac 上查看 SSH 公钥指纹。macOS Terminal 示例：

```powershell
sudo ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub
```

通过可信的独立渠道把**指纹**交给 Windows Host 操作者。第一次 SSH 连接时，只有屏幕指纹完全一致才继续。

不要使用：

```text
-o StrictHostKeyChecking=no
-o UserKnownHostsFile=/dev/null
```

## 3. 在 Windows Host 建立反向 SSH tunnel

先建立专用 known-hosts 文件，并把已经独立核对过的 Agent/Mac 公钥行放入其中，例如：

```powershell
$KnownHosts = "$env:USERPROFILE\.ssh\molt_demo_known_hosts"
```

然后在 **Host 的 PowerShell** 执行（`AGENT_USER` 和 `AGENT_ADDRESS` 替换为 Mac 的 SSH 用户和地址）：

```powershell
ssh -N -T `
  -o ExitOnForwardFailure=yes `
  -o StrictHostKeyChecking=yes `
  -o "UserKnownHostsFile=$KnownHosts" `
  -R 18765:127.0.0.1:8765 `
  AGENT_USER@AGENT_ADDRESS
```

输入 Agent/Mac 的 SSH 凭据后，这个窗口保持打开。默认远端转发只在 Agent/Mac 的回环地址监听；不要设置 `GatewayPorts=yes`，也不要把监听地址改成 `0.0.0.0`。

验证 tunnel 是否通了：在 **Agent 机器**执行：

```bash
curl http://127.0.0.1:18765/health
```

Windows 没有 curl 时：

```powershell
Invoke-WebRequest http://127.0.0.1:18765/health
```

看到 JSON 健康状态后再继续。

## 4. 在 Agent 机器运行向导并配对

保持 SSH tunnel 窗口打开，另开一个 **Agent 终端**：

macOS / Linux：

```bash
cd molt-agent-drop
./molt
```

Windows（如果这台 Agent 机器尚未下载项目，也使用第 1 节的同一条 bootstrap 命令并选择 `2. Agent`）：

```powershell
$ErrorActionPreference="Stop";[Net.ServicePointManager]::SecurityProtocol=[Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12;$u=@("https://cdn.jsdelivr.net/gh/zhou-zhou-1001/molt-agent-drop@main/bootstrap.ps1","https://raw.githubusercontent.com/zhou-zhou-1001/molt-agent-drop/main/bootstrap.ps1","https://github.com/zhou-zhou-1001/molt-agent-drop/raw/refs/heads/main/bootstrap.ps1");$s=$null;$last=$null;foreach($x in $u){try{$r=[Net.HttpWebRequest]::Create($x);$r.Method="GET";$r.UserAgent="Molt-Agent-Drop-Launcher";$r.Timeout=30000;$r.ReadWriteTimeout=30000;$p=[Net.HttpWebResponse]$r.GetResponse();if([int]$p.StatusCode -ne 200){throw "HTTP $([int]$p.StatusCode)"};$q=New-Object IO.StreamReader($p.GetResponseStream());$s=$q.ReadToEnd();$q.Dispose();$p.Dispose();if(-not [string]::IsNullOrEmpty($s)){break}}catch{$last=$_;if($p){$p.Dispose()}}};if([string]::IsNullOrEmpty($s) -or $s.Length -lt 1000 -or $s -match "[^\x00-\x7F]"){throw "Bootstrap download failed: $last"};& ([ScriptBlock]::Create($s))
```

选择 `2. Agent`，填入 Host 显示的 invitation ID 和 secret。向导会访问默认地址：

```text
http://127.0.0.1:18765
```

Host 窗口会出现类似：

```text
Pair request pending: REQUEST_ID
```

在 **Host 窗口**人工核对 request id 后输入：

```text
approve REQUEST_ID
```

不要批准不认识的 label 或 request id。

## 5. 在 Agent 机器验证最小能力

配对成功后，只在专用共享目录里测试：

```bash
python3 drop_client.py --url http://127.0.0.1:18765 --token TOKEN list .
python3 drop_client.py --url http://127.0.0.1:18765 --token TOKEN read hello.txt
python3 drop_client.py --url http://127.0.0.1:18765 --token TOKEN create agent-result.txt --content 'created by my agent'
```

Windows 将 `python3` 换成 `py -3` 或 `python`。`TOKEN` 只放在本机终端，不要粘贴到聊天、Issue、截图或日志。

能力边界固定为：

- `list`
- 读取 UTF-8 普通文本
- 创建不存在的新文件
- 不覆盖已有文件
- 不删除、不执行 shell、不控制桌面

## 6. 结束流程（必须）

1. 在 **Host 窗口**输入：

   ```text
   revoke
   ```

2. 确认 Agent 再访问得到 `410 revoked`。
3. Ctrl-C 停止 Host。
4. Ctrl-C 关闭 Agent 上的 SSH tunnel。
5. 检查专用共享目录和 Host 状态目录，没有遗留敏感测试文件。

如果 tunnel 意外断开，Host 不会把 SSH 断开自动等价为撤销；立即回到 Host 窗口输入 `freeze` 或 `revoke`。

## 备选：在 Windows Host 安装 OpenSSH Server

只有网络方向不允许 Host 主动连接 Agent/Mac 时，才考虑用 `Add-WindowsCapability` 安装 Windows OpenSSH Server，再由 Agent 使用 `-L 127.0.0.1:18765:127.0.0.1:8765` 本地转发。该安装在部分家庭机上可能非常慢或卡住，因此不是首选；备选路径同样必须独立核对 Windows Host 的 host key，且禁止 `StrictHostKeyChecking=no`。

## Demo 限制

这是开发者预览，不是生产级 E2EE、设备身份、强沙箱或管理员/root 对抗方案。SSH tunnel 提供传输保护，但 Molt 本身的 HTTP 协议不宣称应用层 E2EE。Host 的专用目录、Windows ACL、SSH 账户和 host-key 核验仍是操作者责任。
