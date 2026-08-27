# Molt 跨不同局域网：自建 SSH relay 极简流程

Molt 不提供云 Relay，也不要求特定 VPS。只需一台双方都能通过 SSH 主动连接的机器（自有 VPS、堡垒机、家中公网 SSH 主机均可）。Relay 不运行 Molt，不接触 invitation/token，只承载两个 SSH 转发。

```text
Windows Host                         自建 SSH relay                         Agent/Mac
127.0.0.1:8765 <-- SSH -R -- 127.0.0.1:18765 <-- SSH -L -- 127.0.0.1:18765
```

三个 HTTP 监听地址全部是 `127.0.0.1`。不要开放、防火墙放行或端口映射 `8765/18765`，不要在 sshd 设置 `GatewayPorts yes`。

## 1. Relay 一次性准备

Relay 需要普通 SSH 账户、密钥认证和 `AllowTcpForwarding yes`（OpenSSH 默认允许）。建议创建权限最小的专用账户；不需要安装 Molt。Host 和 Agent 各自使用现有 OpenSSH 私钥或 ssh-agent，配置文件不接受密码。

在 Relay 控制台通过可信渠道取得 host key 指纹：

```sh
sudo ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub -E sha256
```

Host 和 Agent 分别创建专用 known_hosts 文件。先用 `ssh-keyscan relay.example` 获取公钥行，再将其指纹与上一步独立取得的指纹逐字核对：

```sh
ssh-keyscan -t ed25519 relay.example > ~/.ssh/molt_relay_known_hosts
ssh-keygen -lf ~/.ssh/molt_relay_known_hosts -E sha256
```

`ssh-keyscan` 本身不证明身份；只有独立比对一致才可继续。Windows 路径可用 `$env:USERPROFILE\.ssh\molt_relay_known_hosts`。禁止使用 `StrictHostKeyChecking=no` 或 `UserKnownHostsFile=/dev/null`。先验证两端都能通过密钥或 ssh-agent 非交互登录：

```sh
ssh -o BatchMode=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile=~/.ssh/molt_relay_known_hosts molt-relay@relay.example true
```

## 2. 两端各写一个无凭据配置

Host 上保存 `host-tunnel.json`：

```json
{
  "mode": "host-reverse",
  "relay_host": "relay.example",
  "relay_user": "molt-relay",
  "known_hosts": "C:\\Users\\you\\.ssh\\molt_relay_known_hosts",
  "host_key_fingerprint": "SHA256:替换为独立核验的完整43字符摘要"
}
```

Agent/Mac 上保存 `agent-tunnel.json`：

```json
{
  "mode": "agent-local",
  "relay_host": "relay.example",
  "relay_user": "molt-relay",
  "known_hosts": "/Users/you/.ssh/molt_relay_known_hosts",
  "host_key_fingerprint": "SHA256:替换为同一个完整43字符摘要"
}
```

可选字段：`relay_ssh_port`（22）、`host_port`（8765）、`relay_port`（18765）、`agent_port`（18765）、`reconnect_delay`（5 秒）、`health_timeout`（15 秒）、`identity_file`。相对路径按 JSON 所在目录解析。`identity_file` 只写私钥路径，不写 passphrase；优先不配置，让 ssh-agent 管理解锁密钥。

先执行只读检查；它会校验 JSON、文件类型、端口、指纹并打印实际 SSH argv：

```powershell
.\run_molt_tunnel.ps1 -Config .\host-tunnel.json -Check
```

```sh
python3 molt_tunnel.py agent-tunnel.json --check
```

## 3. Windows Host：启动 Host 和反向隧道

终端 A 启动 Molt Host（也可运行 `molt.ps1 -Role host`）：

```powershell
.\run_drop_host.ps1 -Root C:\MoltDemoShare -StateDir "$env:LOCALAPPDATA\MoltDropDemo"
```

终端 B 只运行一个入口：

```powershell
.\run_molt_tunnel.ps1 -Config .\host-tunnel.json
```

管理器先检查 `http://127.0.0.1:8765/health`，再建立 `-R`。`ExitOnForwardFailure` 确保 Relay 端口被占用等问题不会伪装成成功。

## 4. Agent/Mac：启动本地转发并运行 Molt

终端 A：

```sh
python3 molt_tunnel.py agent-tunnel.json
```

看到 `Tunnel healthy: http://127.0.0.1:18765/health` 后，终端 B：

```sh
./molt --role agent --url http://127.0.0.1:18765
```

Windows Agent 使用相同 PowerShell 入口：

```powershell
.\run_molt_tunnel.ps1 -Config .\agent-tunnel.json
.\molt.ps1 -Role agent
```

输入 Host 显示的 invitation id/secret；Host Owner 仍须输入 `approve REQUEST_ID`。完成后使用 `list/read/create`，并在 Host 输入 `revoke`。

## 断线与失败行为

- SSH 网络中断按 `reconnect_delay` 自动重连；`ServerAliveInterval=15`、`ServerAliveCountMax=3` 检测死连接。
- host-key 改变/不匹配、认证失败、identity 权限错误、DNS 配置错误不会循环重试，错误会原样显示并退出。先人工修复，绝不要绕过校验。
- Agent 转发必须在 `health_timeout` 内通过 `/health`，否则退出。Host 建立 SSH 前检查本机 `/health`。
- Relay 重启后可恢复网络类中断，但 Molt session 不因 SSH 断线自动撤销；异常时 Host Owner 应 `freeze` 或 `revoke`。

## 同一局域网简化

同一 LAN 可把 Agent/Mac 自身当 Relay：Host 使用 `host-reverse` 连接 Agent sshd，此时 Agent 已直接拥有回环 `18765`，无需运行 `agent-local`。仍须独立核验 Agent SSH host key。

## 限制

这是开发者 Demo，不是应用层 E2EE、设备身份或强沙箱。Relay SSH 管理员能观察连接元数据；HTTP 内容由 SSH 加密。Relay 必须允许 TCP forwarding，双方必须能主动访问它。同一 Relay 账户/端口一次只能承载一组默认端口隧道；多组应使用不同 `relay_port`。
