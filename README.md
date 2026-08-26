# Molt Agent Drop Demo

这是一个真实可演示、但非生产级的跨机器 Agent Drop。Host 只监听 `127.0.0.1`；跨机器连接必须由用户显式建立 SSH tunnel。Python 3 标准库，无第三方依赖。

## 小白从这里开始：终端向导

不要先读完整文档。Host 和 Agent 都可以先运行向导：

```powershell
git clone https://github.com/zhou-zhou-1001/molt-agent-drop.git
cd molt-agent-drop
.\molt.ps1
```

向导会先问你是哪一端：

- **Host**：选择专用共享目录，自动准备已校验的 Python，启动 Host，并显示一次性 invitation。
- **Agent**：输入 Host 给你的 invitation，发起配对；Host Owner 仍必须明确批准 request id。

向导不会开放公网端口、关闭防火墙或跳过 SSH host-key 校验。两台电脑之间仍需先按 [跨机器步骤](docs/demo-cross-machine.md) 建立已核验的 SSH tunnel。向导是 Demo 的友好入口，不是生产安装器。

如果 PowerShell 阻止本地脚本，**不要**为了运行它而降低全局执行策略；请在当前终端临时使用：

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\\molt.ps1
```

## 自动获取 Python（bootstrap）

目标机没有 Python 也不怕：`bootstrap_python.ps1` 会自动检测 `py`/`python`，没有则下载**固定版本**（默认 3.13.15 amd64）官方 embeddable 包到私有目录（`%LOCALAPPDATA%\MoltDropDemo\runtime`），**强制 SHA-256 校验**（多源 fallback：npmmirror → 华为云 → python.org，任一源下载后哈希不符即删除并换源，全部失败则 fail-closed），解压后修正 `python._pth` 并自检标准库，幂等（已验证的 runtime 直接复用）。不改 PATH、不写注册表、不做全局安装。

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

Host 控制台可输入 `revoke`、`freeze` 或按 Ctrl-C 停止。每次文件请求都会检查 session 状态和 TTL。

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
