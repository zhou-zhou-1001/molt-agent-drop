# Molt Drop 跨机器实机演示（推荐路径）

本文只给一条推荐路径：**Agent 机器执行 SSH 本地转发，Host 继续只监听本机回环地址**。

```text
┌────────────── Agent 机器 ──────────────┐
│ SSH client                             │
│ 127.0.0.1:18765  ───── SSH ─────┐      │
│ drop_client.py                   │      │
└──────────────────────────────────┼──────┘
                                   │
                         127.0.0.1:8765
┌────────────── Host 机器 ─────────┴──────┐
│ drop_host.py                            │
│ 专用共享目录 + 审计日志                 │
└─────────────────────────────────────────┘
```

**不要把 8765 或 18765 开到公网，不要关闭防火墙，不要使用 `StrictHostKeyChecking=no`。**

## 0. 先准备两台机器

- **Host**：文件所在电脑。下面示例是 Windows。
- **Agent**：运行 Agent 的电脑，可以是 macOS、Linux 或另一台 Windows。
- Host 必须有可用的 SSH Server，Agent 必须有 `ssh` 客户端。
- 你需要知道 Host 的 SSH 用户名、地址，以及 Host SSH 公钥的指纹。

如果只是两台同一局域网电脑，也仍然建议走 SSH，不要改成明文 LAN HTTP。

## 1. 在 Host 机器启动 Molt

在 **Host 的 PowerShell** 执行。Windows 没有 Git 也没关系，使用系统自带 PowerShell 下载 ZIP：

```powershell
$zip = Join-Path $env:TEMP 'molt-agent-drop.zip'
$tmp = Join-Path $env:TEMP 'molt-agent-drop-extract'
$dest = Join-Path $HOME 'molt-agent-drop'
if (Test-Path $dest) { throw "目录已存在，请确认后换目录： $dest" }
Invoke-WebRequest 'https://github.com/zhou-zhou-1001/molt-agent-drop/archive/refs/heads/main.zip' -OutFile $zip
if (Test-Path $tmp) { Remove-Item $tmp -Recurse -Force }
Expand-Archive $zip -DestinationPath $tmp -Force
Move-Item (Join-Path $tmp 'molt-agent-drop-main') $dest
Remove-Item $zip -Force
Set-Location $dest
.\molt.ps1
```

如果脚本执行策略阻止运行，只对当前 PowerShell 窗口临时放行：

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\molt.ps1
```

不要为了这个 Demo 修改 LocalMachine 或 CurrentUser 的全局执行策略。选择 `1. Host`，接受一个**专用、无敏感文件**的共享目录，例如：

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

## 2. 独立核对 Host 的 SSH host key（必须）

在 Host 上查看 SSH 公钥指纹。Windows PowerShell 示例：

```powershell
ssh-keygen -lf "$env:ProgramData\ssh\ssh_host_ed25519_key.pub"
```

通过可信的独立渠道把**指纹**交给 Agent 操作者。第一次 SSH 连接时，只有屏幕指纹完全一致才继续。

不要使用：

```text
-o StrictHostKeyChecking=no
-o UserKnownHostsFile=/dev/null
```

## 3. 在 Agent 机器建立本地 SSH tunnel

这一条命令必须在 **Agent 机器**执行，不是在 Host 执行。

### macOS / Linux

```bash
mkdir -p ~/.ssh
ssh-keyscan -t ed25519 HOST_ADDRESS
# 仅在与可信渠道提供的指纹核对一致后，才把完整公钥行写入专用文件：
# ~/.ssh/molt_demo_known_hosts

ssh -N -T \
  -o ExitOnForwardFailure=yes \
  -o StrictHostKeyChecking=yes \
  -o UserKnownHostsFile="$HOME/.ssh/molt_demo_known_hosts" \
  -L 127.0.0.1:18765:127.0.0.1:8765 \
  HOST_USER@HOST_ADDRESS
```

### Windows PowerShell

先建立专用 known-hosts 文件，并把已经独立核对过的 Host 公钥行放入其中，例如：

```powershell
$KnownHosts = "$env:USERPROFILE\.ssh\molt_demo_known_hosts"
```

然后在 **Agent 的 PowerShell** 执行：

```powershell
ssh -N -T `
  -o ExitOnForwardFailure=yes `
  -o StrictHostKeyChecking=yes `
  -o "UserKnownHostsFile=$KnownHosts" `
  -L 127.0.0.1:18765:127.0.0.1:8765 `
  HOST_USER@HOST_ADDRESS
```

输入 Host 的 SSH 凭据后，这个窗口保持打开。不要把 `127.0.0.1:18765` 改成 `0.0.0.0:18765`。

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

Windows：

```powershell
Set-Location molt-agent-drop
.\molt.ps1
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

## 为什么不把 reverse tunnel 作为默认

reverse tunnel 也能工作，但需要用户理解 `-R`、远端监听地址和 SSH Server 的 forwarding 策略，容易把监听地址误改成公网。Molt Demo 的小白默认路径统一使用 Agent 侧 `-L` 本地转发；只有高级用户明确理解网络拓扑时，才自行采用其他安全 tunnel 方案。

## Demo 限制

这是开发者预览，不是生产级 E2EE、设备身份、强沙箱或管理员/root 对抗方案。SSH tunnel 提供传输保护，但 Molt 本身的 HTTP 协议不宣称应用层 E2EE。Host 的专用目录、Windows ACL、SSH 账户和 host-key 核验仍是操作者责任。
