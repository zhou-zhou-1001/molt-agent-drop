# 明日跨机器现场步骤（Windows Host）

假设：Windows 是文件 Host；Agent 机器运行 SSH server，并能被 Windows 登录。下面的 `18765` 是 Agent 机器上的 tunnel 端口，`8765` 是 Windows Host 本地端口。

## 1. 预先核验 SSH host key（必须）

在现场连接前，通过可信的独立渠道向 Agent 机器管理员取得 SSH host-key 指纹（例如当面查看 Agent 机器的 `ssh-keygen -lf` 输出），逐字符核对。不得使用 `StrictHostKeyChecking=no`、`accept-new`，也不得在首次连接提示中盲目输入 yes。

将已核验的 key 写入专用 known-hosts 文件。可先由可信渠道取得完整公钥行，再保存为：

```powershell
$KnownHosts = "$env:USERPROFILE\.ssh\molt_demo_known_hosts"
# 将已独立核验的“agent.example ssh-ed25519 AAAA...”写入 $KnownHosts
ssh-keygen -lf $KnownHosts
```

确认这里显示的指纹与可信渠道完全一致。若不一致，停止演示并调查。

## 2. Windows 启动 Host

```powershell
Set-Location C:\demo\molt
.\run_drop_host.ps1 -Root C:\MoltDemoShare -StateDir "$env:LOCALAPPDATA\MoltDropDemo" -Port 8765 -InviteTtl 10 -SessionTtl 60
```

Host 固定监听 `127.0.0.1`，不绑定 `0.0.0.0`，无需也不应修改防火墙。记录屏幕上的 invitation id/secret，通过现场可信方式交给 Agent 操作者。

## 3. 用户显式建立 reverse tunnel

在 Windows 新开 PowerShell，使用已经核验的专用 known-hosts 文件：

```powershell
ssh -N -T -o ExitOnForwardFailure=yes -o StrictHostKeyChecking=yes -o "UserKnownHostsFile=$KnownHosts" -R 127.0.0.1:18765:127.0.0.1:8765 demo-user@agent.example
```

保持窗口打开。`-R` 令 Agent 机器的 `127.0.0.1:18765` 转发到 Windows Host 的 `127.0.0.1:8765`。SSH server 必须允许 remote forwarding；不要设置 GatewayPorts，也不要把 remote bind address 改成 `0.0.0.0`。

## 4. Agent 请求、owner 批准、演示文件操作

Agent 机器：

```powershell
py -3 drop_client.py --url http://127.0.0.1:18765 pair --invitation-id ID --invitation-secret SECRET --label stage-agent
```

Windows Host 控制台核对 label/request id，并明确输入 `approve REQUEST_ID`。Agent 得到一次性返回的 session token 后执行：

```powershell
py -3 drop_client.py --url http://127.0.0.1:18765 --token TOKEN list .
py -3 drop_client.py --url http://127.0.0.1:18765 --token TOKEN read hello.txt
py -3 drop_client.py --url http://127.0.0.1:18765 --token TOKEN create agent-result.txt --content "created through Molt demo"
```

CI/无人值守验收可选择 `--owner-cmd-file`，但它只是本地自动化入口，不是生产身份认证。文件必须在私有 `-StateDir` 直属目录中，由可信本地进程写入单条、换行结尾的命令后原子 rename 发布；不要让 Agent API、授权 root 或远端共享目录接触该文件。交互演示仍优先使用控制台人工批准。

## 5. 结束与异常处理

正常结束时先在 Host 输入 `revoke`，再 Ctrl-C 停止 Host 和 SSH。若 tunnel 窗口关闭、网络中断或状态不确定，立即在 Host 输入 `freeze` 或 `revoke`。Demo 无法可靠把 SSH 断开事件关联到 session，因此不会声称自动断线撤权；TTL 与每请求状态检查是兜底。

Audit 默认在 `%LOCALAPPDATA%\MoltDropDemo\audit.jsonl`，位于授权 root 外，Agent API 无法访问。
