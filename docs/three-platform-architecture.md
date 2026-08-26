# Molt Agent Drop：三平台可落地架构

目标不是把完整 OpenClaw/Codex 安装到别人电脑，而是在电脑主人明确同意后，启动一个短时 Host，让 Agent 通过统一能力协议做有限工作；结束或 TTL 到期即停。

## 统一协议

- `GET /health`：无需 token，仅返回会话是否有效与剩余秒数。
- 其余请求带 `Authorization: Bearer <session-token>`。
- `GET /files?path=相对路径`：列目录。
- `GET /file?path=相对路径`：读 UTF-8 文本。
- `PUT /file?path=相对路径` body `{"content":"..."}`：写文本。
- `POST /command` body `{"name":"pwd|ls|git status|python version"}`：只执行平台白名单 argv。
- 所有请求把 `audit.jsonl` 写入授权 root 外的 Host 私有 state directory；TTL 到期返回 410 并停止授权。
- 路径协议统一使用 `/` 分隔的相对路径；拒绝绝对路径、`..`、NUL、反斜杠和 root 外对象。

## 三个平台实际差异

| 平台 | 启动 | 白名单映射 | 文件风险 | 清理 |
|---|---|---|---|---|
| Windows | `py -3 drop_host.py` 或 PowerShell 脚本 | `cmd.exe /d /c cd/dir`、`git.exe`、当前 Python | symlink 与 junction/reparse point 只允许在根内且检测到即拒绝；没有管理员级强隔离 | Ctrl-C、PowerShell 停止、TTL |
| macOS | `python3 drop_host.py` | `pwd`、`ls -la`、`git`、当前 Python | symlink 拒绝；仅能力边界，不是沙箱 | Ctrl-C、SIGTERM、TTL |
| Linux | `python3 drop_host.py` | 同 macOS | symlink 拒绝；生产版应叠加 Landlock/bubblewrap | Ctrl-C、SIGTERM、TTL |

当前 MVP 默认只绑定 `127.0.0.1`。这意味着它不会直接让另一台电脑连接；明天若 Agent 在同一台 Windows 上运行，直接使用 localhost。若 Agent 在另一台电脑，使用用户明确控制的 SSH 本地端口转发或后续 Relay，不开放公网端口。

## Windows 明天现场流程

1. 把 `molt` 文件夹复制到目标电脑；不要安装服务、注册表项或防火墙规则。
2. 在 PowerShell 中运行：

```powershell
Set-Location C:\path\to\molt
.\run_drop_host.ps1 -Root C:\Users\Name\Desktop\AgentWork -Port 8765 -Ttl 60
```

3. 终端会打印 `MOLT_SESSION_TOKEN` 和 `MOLT_URL`，只把 token 交给自己的 Agent，不发群聊。
4. 在同一台电脑验证：

```powershell
$h=@{Authorization='Bearer TOKEN'}
Invoke-RestMethod http://127.0.0.1:8765/health -Headers $h
Invoke-RestMethod 'http://127.0.0.1:8765/files?path=.' -Headers $h
```

5. 做完先 `revoke` 再按 Ctrl-C；检查 root 外 state directory 中的 `audit.jsonl`。TTL 到期会让后续请求返回 410，但不会代替进程退出或 SSH 清理。

## macOS/Linux

```bash
python3 molt/drop_host.py --root ~/AgentWork --port 8765 --ttl 60
python3 molt/drop_client.py --url http://127.0.0.1:8765 --token TOKEN list .
```

## 能力矩阵

| 能力 | MVP | 默认边界 |
|---|---:|---|
| 列目录/读写 UTF-8 文本 | 是 | 仅授权根；单次内容约 2 MB |
| 命令 | 是 | 固定白名单、无任意 shell 拼接、30 秒超时 |
| 浏览器/屏幕/摄像头 | 否 | 不实现 |
| 公网 Relay/二维码配对 | 否 | 后续版本 |
| 任意 Agent 代码执行 | 否 | 不把模型或密钥复制到 Host |
| 强隔离沙箱 | 否 | 当前是能力限制，不是恶意 Agent 防护 |

## 已知限制

Python `Path.resolve` 加 symlink/reparse 检查不能完全消除所有 Windows TOCTOU、hard link、ACL 和管理员级攻击；因此不要把不可信 Agent 指向敏感目录。生产版需要 Windows 受限 token/Job Object 或 AppContainer、Linux Landlock/bubblewrap、macOS App Sandbox/helper，并加入 Host 主人可见的批准 UI、E2EE Relay 和签名发行包。
