# Molt Agent Drop 架构方案

> 状态：MVP 架构提案  
> 日期：2026-08-26  
> 目标：让用户把自己的 Agent 临时、可授权、可审计、用完即走地部署到另一台 macOS、Windows 或 Linux 电脑。

## 1. 摘要与核心决策

Agent Drop 不是“远程桌面”或“把完整 Agent 安装到别人电脑”，而是一段由电脑主人明确批准、能力受限、全程可见、随时可撤销的临时执行会话。

MVP 采用以下架构：

- Agent 的推理循环和长期身份留在发起方或云端；被访问电脑只运行轻量的 **Molt Host**，暴露经过授权的文件、终端和浏览器能力。
- 双方都只建立到云端 Relay 的出站 TLS 连接，控制面负责身份、配对、策略和审计索引，Relay 只转发端到端加密的会话消息。
- 每次会话由电脑主人选择目录、能力和时限；每次高风险操作还需单独批准。默认拒绝，授权不可由 Agent 自行扩大。
- Host 将“策略判断”和“操作执行”分层；所有能力都走结构化 RPC 和统一策略门，不开放任意入站端口。
- 文件访问以用户选定目录为根；终端在该目录的临时工作区内运行；浏览器 MVP 使用独立临时 profile，不接触主人现有 cookie。
- 会话结束立即停进程、撤销 token、关闭浏览器 profile、删除临时目录和本机短期密钥；审计摘要保留，敏感内容默认不上传。
- 明天的演示版本只支持同一局域网或临时 Relay、单个目录、macOS/Linux、结构化文件操作和受控命令；它是产品流程演示，不宣称生产级隔离。

最重要的非目标是：MVP 不允许无人值守永久驻留、不接管整台电脑、不复用主人的浏览器登录态、不把发起方的模型密钥复制给 Host，也不声称能安全运行任意恶意二进制。

## 2. 现状与设计依据

当前 `molt` 项目处于概念起点：`README.md` 将 Molt 定义为“为 OpenClaw agent 提供桌面实体化身体”，`hello.py` 是占位程序，尚无既定语言、协议、部署或安全实现。因此本方案按从零构建 MVP 设计，但保持与 OpenClaw/通用 Agent 工具调用模型兼容。

工作区现有相关实现提供了几个可复用原则：

- 能力应通过稳定接口与平台实现解耦；本地与远程执行只是不同 provider。
- 权限策略应按会话、按调用携带，而不是修改一个全局开关。
- 沙箱可用性必须做功能探测；无法强制执行时失败闭合，不能静默降级到裸执行。
- “完全强制”和“部分强制”必须显式展示，不能把平台能力差异藏起来。
- 模型可见、用户批准和工具执行均应进入追加式事件日志，以便重放和审计。

## 3. 产品边界

### 3.1 角色

- **Agent Owner（发起方）**：拥有 Agent、发起临时部署的人。
- **Host Owner（主机方）**：拥有目标电脑、决定授权范围的人。
- **Agent Runtime**：执行模型循环、保有 Agent 配置与模型凭据的一侧。
- **Molt Host**：目标电脑上的临时能力代理和策略执行点。
- **Molt Control Plane / Relay**：负责账户、配对、会话协调、消息中继及审计元数据。

一人可同时扮演两种 Owner，但协议不能依赖双方互相信任。

### 3.2 MVP 做什么

- 通过邀请码或二维码建立一次性会话。
- Host Owner 明确选择可访问目录、能力集合、会话时长和审批模式。
- 支持目录内的列举、读取、写入、创建、重命名和删除（删除默认需确认并优先进入系统废纸篓）。
- 支持受控的一次性 shell 命令、输出流、超时和进程终止。
- 支持一个隔离浏览器 profile 的打开页面、点击、输入、截图和下载到授权目录。
- 双方看到实时活动流；Host Owner 可暂停、拒绝单次操作或立即终止。
- 会话结束生成可验证的审计摘要并清理临时状态。

### 3.3 MVP 不做什么

- 不提供通用远程桌面、键鼠接管、屏幕常驻监控或摄像头/麦克风访问。
- 不支持内核驱动、提权、sudo/UAC 自动确认、修改系统安全设置。
- 不保证对抗已获得 Host Owner 管理员权限的本地攻击者。
- 不允许 Agent 安装永久服务、开机启动项或会话外后台任务。
- 不把任意 Agent 代码直接下载后以 Host Owner 权限运行；Agent 通过已知能力协议调用 Host。
- 不访问 Host Owner 的默认浏览器 profile、密码管理器、SSH agent、系统钥匙串或云盘根目录。
- 不做组织级设备管理、合规留存、多人协作和离线任务；这些属于后续版本。

## 4. 用户流程

### 4.1 发起与配对

1. Agent Owner 在 Molt 中选择“Drop to another computer”。
2. 控制面创建 10 分钟有效、单次消费的邀请，展示二维码和短码；邀请本身不包含会话权限。
3. Host Owner 打开已安装的 Molt Host，或运行签名的一次性 Host，扫描二维码/输入短码。
4. 双端展示相同的 4～6 位人类可核对短语，防止 Relay 或输错代码导致配错设备。
5. Host 展示发起方身份、Agent 名称、请求原因、所需能力和时长。Host Owner 可删减权限，不能被要求“一键全开”。
6. Host Owner 通过系统目录选择器选择授权根目录；如启用浏览器，明确说明使用全新临时 profile。
7. 双方确认后创建会话，Agent 才能看到能力清单；拒绝或超时则邀请作废。

### 4.2 会话中

- Host 常驻显示显眼的会话状态、倒计时、Agent 名、当前动作、暂停和结束按钮。
- 每个调用先经过本地策略门，再视风险弹出批准请求；批准必须绑定规范化后的具体参数和过期时间。
- Agent 仅收到必要结果。例如目录列举返回名称和元数据，不自动上传所有文件内容。
- 长命令显示实时输出，并可由 Host Owner 单独终止。
- 权限变更采用“新授权版本”：缩小立即生效，扩大必须再次由 Host Owner 明确确认。

### 4.3 结束

结束条件包括：任一方主动结束、超时、网络断开超过宽限期、Host 休眠/锁屏策略触发、异常或撤销。

Host 随即停止接受新调用，取消运行中任务，终止进程树，关闭浏览器，执行清理，向控制面提交结束状态。双方获得操作摘要；Host Owner 可检查本地详细日志和残留文件列表。

## 5. 配对、设备与会话模型

### 5.1 三种不同凭据

不要用一个 token 同时承担邀请、设备和会话身份：

- **Device credential**：安装时生成的设备密钥对。私钥存系统安全存储；只用于证明这是同一设备，不授予能力。
- **Pairing invitation**：128 位以上随机数，哈希后存服务端，10 分钟有效、单次消费、限速；只允许进入配对协商。
- **Session capability token**：绑定 `session_id`、调用方公钥、权限版本、受众、过期时间和随机 `jti` 的短期凭据；只能调用已批准能力。

短码只是邀请码的用户界面索引，不能是唯一熵源；连续失败后锁定，并限制 IP、设备和邀请码维度的尝试频率。

### 5.2 会话状态机

```text
INVITED -> PAIRING -> CONSENT_PENDING -> ACTIVE <-> PAUSED
    |          |              |             |
    +----------+--------------+-------------+-> REVOKING -> ENDED
                                           \-> EXPIRED
                                           \-> FAILED
```

- 只有 `ACTIVE` 接受能力调用。
- `PAUSED` 保留连接和审计，但拒绝新调用并暂停/终止活动任务（由能力定义）。
- `REVOKING` 是不可逆状态；终端和浏览器 shutdown 有短暂清理窗口，但不再接受调用。
- 会话采用绝对过期时间和最长空闲时间，不能由 Agent 自行续期。
- 网络断开默认立即冻结新动作；例如 30 秒内恢复可续接，超过后本地终止。破坏性操作不自动重放。

### 5.3 授权对象

建议的服务端/本地共享逻辑模型：

```json
{
  "session_id": "ses_...",
  "host_device_id": "dev_...",
  "agent_identity": { "owner_id": "usr_...", "agent_id": "agt_..." },
  "expires_at": "...",
  "policy_version": 3,
  "grants": {
    "fs": [{ "root_handle": "root_1", "read": true, "write": true, "delete": "ask" }],
    "terminal": { "enabled": true, "network": false, "max_seconds": 120, "mode": "ask" },
    "browser": { "profile": "ephemeral", "downloads_root": "root_1", "mode": "ask-sensitive" }
  }
}
```

协议中传递 `root_handle` 和根内相对路径，不向 Agent 暴露可伪造的宿主绝对路径。Host 本地把 handle 映射到用户选择且已规范化的目录。

## 6. 总体架构

```text
Agent UI / Runtime                    Molt Cloud                    Target computer
+-------------------+       TLS       +------------------+      TLS      +------------------+
| Agent loop        |<--------------->| Control API      |<------------->| Molt Host UI     |
| Molt capability   |                 | Pairing/session  |               | Policy engine    |
| provider          |<=== E2EE ======>| Relay (opaque)   |<== E2EE ====>| Capability broker|
+-------------------+                 | Audit metadata   |               | Sandbox runners  |
                                      +------------------+               +------------------+
```

### 6.1 Agent 侧

- `MoltRemoteProvider` 将标准 Agent 工具映射到远端结构化能力。
- 维护 request id、幂等键、取消信号、超时和流式结果。
- 不应把 Host 包装成“任意 RPC”；只暴露 Host 声明且当前策略允许的工具 schema。
- Agent Runtime 持有模型供应商密钥；Host 从不需要知道它。

### 6.2 Host 客户端

Host 建议拆为四层，即使 MVP 先在一个进程中实现也要保留接口边界：

1. **UI/Consent**：配对、授权、活动流、单次审批、结束和清理报告。
2. **Session daemon**：WebSocket、协议状态机、E2EE、心跳、重连、撤销。
3. **Policy engine**：把会话 grants 与具体调用参数合并，输出 allow / deny / ask；只收窄，不扩大。
4. **Capability executors**：文件、命令和浏览器；运行在低权限子进程，不能直接读取会话密钥。

生产版应让 daemon 与 UI 分离，UI 崩溃时 daemon 默认暂停；executor 使用本地认证 IPC，且每次请求仍携带 session、policy version 和 request id。

### 6.3 控制面

最小服务可由一个 API 服务和 PostgreSQL/SQLite（演示版）组成：

- 账户与设备公钥注册。
- 邀请创建/消费及防爆破。
- 会话状态和权限摘要，不存目录绝对路径或文件内容。
- 撤销列表、在线状态、推送通知。
- 审计事件的密文存储或仅存哈希/元数据。
- Relay 的连接鉴权、背压、消息大小限制和限速。

控制面不应持有会话内容解密密钥。初版若来不及实现完整 E2EE，必须在演示和文档中明确 Relay 可见内容，并禁止真实敏感数据；进入外部测试前 E2EE 是硬门槛。

## 7. 通信协议与可靠性

消息使用版本化 envelope（JSON 便于 MVP 调试，后续可换 CBOR/Protobuf）：

```json
{
  "v": 1,
  "session_id": "ses_...",
  "request_id": "req_...",
  "seq": 42,
  "type": "capability.request",
  "policy_version": 3,
  "sent_at": "...",
  "deadline": "...",
  "body": { "capability": "fs.read", "args": {} },
  "signature": "..."
}
```

- 配对时双方使用临时 X25519 密钥并通过设备身份密钥签名，基于共享秘密派生方向独立的会话密钥；用户核对短语绑定双方公钥和邀请。
- 使用带认证加密的帧，nonce/sequence 不可复用；Relay 只能看到路由元数据和包大小。
- 每个请求有唯一 ID、deadline 和取消消息。Host 对已完成 request id 做短期去重并返回相同结果。
- 只把明确标记为幂等的读取自动重试；写文件、命令、点击等在连接不确定时返回 `outcome_unknown`，由人或 Agent 检查后决定。
- 输出按 chunk 流式传输并有窗口/背压；限制单条消息、单文件和每会话总字节数。
- Host 以本地单调时钟执行 timeout，不能只信任调用方时间戳。

## 8. 权限与沙箱

### 8.1 权限原则

- 默认拒绝、最小权限、时限明确、范围可解释、随时可撤销。
- 权限由 Host 本地执行；云端判断只能作为额外拦截，不能是唯一边界。
- 每次调用都重新根据当前 policy version 判断，已签发 token 不覆盖本地撤销状态。
- 权限分为 `deny`、`allow during session`、`ask every time`；高风险操作不能被低风险批量批准隐式包含。
- 如果平台探测显示无法达到声明的隔离等级，则禁用相关能力，而非无提示裸跑。

### 8.2 风险分级建议

- **低风险自动允许**：授权根内列目录、读取明确文件、浏览临时 profile 的普通页面。
- **中风险可会话授权**：创建/修改文件、运行匹配允许规则且无网络的短命令、下载到授权根。
- **高风险每次确认**：删除/覆盖、执行新下载文件、网络命令、提交表单、上传文件、访问登录/支付页面。
- **MVP 永久拒绝**：提权、系统目录写入、读取凭据存储、默认浏览器 profile、持久化服务、绕过沙箱。

审批对话框必须展示展开后的命令、规范化目标路径、网络目的地、预计影响和调用理由；“批准”绑定参数哈希，Agent 修改参数后必须重新批准。

### 8.3 文件能力

文件 API 应结构化：`list/stat/read/write/create_dir/move/delete/search`，不以 shell 代替。关键约束：

- 用户通过原生文件选择器获得根目录；记录 canonical path 和尽可能稳定的文件标识。
- 每步操作打开目标前，在 Host 内做 canonicalization；拒绝绝对路径、`..` 逃逸、NUL、设备路径和不支持的 alternate data stream。
- 防 symlink/junction/reparse-point TOCTOU：优先使用基于目录 handle 的 `openat`/等价 API、禁止跟随最终 symlink，打开后再校验实际对象仍在根内。
- 写入采用同目录临时文件、flush、原子 rename；覆盖前可生成会话内备份。
- 删除默认移入系统废纸篓；无法安全回收时要求单次批准并在日志标为不可恢复。
- 限制文件大小、目录遍历项数、递归深度和并发；敏感文件名（`.env`、私钥、浏览器数据库等）默认 deny/ask。
- 审计记录路径的根内相对表示、操作、大小和前后内容哈希；文件内容默认只在 E2EE 通道传输，不进云端日志。

### 8.4 终端能力

终端是最高风险能力。MVP 宜先提供“一次性命令”而非完整交互 PTY：

- cwd 固定在授权根或其会话临时副本；环境变量使用白名单重建，不继承云凭据、SSH_AUTH_SOCK、代理凭据等。
- 每个命令在新进程组/job object 中运行，限制 wall time、CPU、内存、子进程数和输出量；结束时杀整个进程树。
- 默认无网络。需要网络时按请求展示域名/IP/端口；长期应由沙箱网络层而不是命令字符串检查执行。
- 不允许 sudo、runas、osascript 自动点权限框、系统配置修改和后台脱离。
- 命令参数采用 argv；只有明确 shell 模式才接受字符串，并将完整字符串展示给 Host Owner。
- sandbox launcher 与命令退出状态使用带外通道区分，避免子进程伪造“沙箱失败”诊断。

隔离后端建议：

| 平台 | MVP | 加固方向 | 必须展示的限制 |
|---|---|---|---|
| Linux | bubblewrap；不可用时对终端失败闭合 | Landlock 叠加、namespaces、seccomp、cgroups、无网络 namespace | 用户命名空间可能被发行版禁用；Landlock ABI 能力不同 |
| macOS | `sandbox-exec`/Seatbelt profile + 低权限子进程 | 专用 helper、Hardened Runtime、App Sandbox/虚拟化 | Seatbelt 私有接口稳定性有限；TCC 权限不能靠它替代 |
| Windows | 受限 token + Job Object + 会话专用目录 ACL | AppContainer/WDAG 或轻量 VM、网络 WFP 规则 | ACL/受限 token 对 hard link、已有 ACL 等只能算部分强制 |

如果后端只达到 `partial`，终端默认关闭；仅在开发者模式中经醒目确认开放，且不能描述为安全沙箱。

### 8.5 浏览器能力

MVP 启动 Playwright 管理的 Chromium 和全新临时 user-data-dir：

- 不连接用户正在使用的浏览器，不读取现有 cookie、历史、密码或扩展。
- 下载只写入一个授权根；上传文件只能由 Host Owner 在原生选择器中再次选取，或来自已授权且明确确认的路径。
- 导航可配置域名 allowlist；阻止 `file://`、浏览器内部页、本地网段和云实例 metadata 地址，防 SSRF。
- 提交表单、登录、支付、发布内容等副作用操作每次确认；密码字段默认要求 Host Owner 本地输入，内容不回传 Agent/审计。
- 浏览器 viewport 可由双方看到；每次点击/输入记录页面 URL、元素描述和截图哈希，敏感输入打码。
- 会话结束关闭进程并删除整个 profile；崩溃启动时扫描并清理过期 profile。

不要在 MVP 里把浏览器“远程调试端口”暴露到网络；Host daemon 与浏览器驱动只经 loopback/私有 IPC 通信。

## 9. 密钥、token 与秘密处理

- 设备私钥不可导出，分别存 macOS Keychain、Windows DPAPI/Credential Locker、Linux Secret Service；无安全存储时明确提示并只支持一次性设备身份。
- 邀请 token 只存哈希，消费即作废；日志不得记录原 token、二维码 URL 或 Authorization header。
- 会话 access token 建议 5 分钟过期并滚动刷新；refresh 只在在线会话内使用，绝对过期不能延长。
- token 包含 audience、会话、设备/调用方 key thumbprint、policy version、scope、expiry 和 jti；采用 proof-of-possession，避免 bearer token 被复制后直接使用。
- 撤销同时作用于控制面连接和 Host 本地状态；Host 本地撤销优先，断网也能立即生效。
- Agent 自有模型/API 凭据留在 Agent Runtime。若任务需要第三方网站秘密，由 Host Owner 本地输入到隔离浏览器；Agent 只得到成功/失败或脱敏结果。
- 内存中的会话密钥在结束时清零；不得写 crash dump。遥测、错误上报和日志统一做字段级脱敏。

## 10. 网络拓扑

### 10.1 MVP 推荐：云 Relay

双方均发起出站 `wss://` 连接，最适合 NAT、企业网络和跨平台 MVP：

- 无需在 Host 开端口、配置路由器或发现公网 IP。
- Control API 与 Relay 可同一部署起步，但代码和权限上分离。
- Relay 根据 session id 路由密文帧，实施认证、限速、连接数和帧大小限制，不解析能力 body。
- 心跳只表示通道活性，不表示授权仍有效；Host 本地状态是最终裁决。

### 10.2 后续：点对点优化

后续可用 WebRTC DataChannel/QUIC + STUN/TURN 尝试 P2P，失败回落 Relay。P2P 不改变端到端加密、授权、审计或撤销语义，因此不应成为 MVP 前置条件。局域网直连只适合开发演示，不能把未认证 HTTP/WebSocket 当产品模式。

## 11. 审计模型

审计日志是本地优先、追加式、哈希链连接的事件流：

```text
event_hash = H(previous_hash || canonical_event)
```

事件至少包含：会话创建/确认、权限版本变化、能力请求、批准/拒绝、执行开始/结束、结果摘要、错误、暂停、撤销和清理结果。每个能力事件关联 request id、主体、时间、规范化参数摘要、风险等级、策略决策和结果哈希。

审计需要同时满足“可验证”和“少收集”：

- Host 保存详细日志；云端默认只保存会话元数据、事件类型、哈希链头和结束签名。
- 命令 stdout、文件内容、网页正文不默认持久化；可存字节数、退出码和内容哈希。
- 双方在结束时对最终 transcript root 签名，各自可导出 JSONL + 摘要 HTML。
- 明确标记缺口：离线、进程被强杀、磁盘写满或本机日志被 Host Owner 修改。不能宣称审计日志在敌对 Host 上不可篡改。
- 配置短留存和主动删除；企业合规留存是后续独立功能。

## 12. 清理、撤销与崩溃恢复

### 12.1 正常清理顺序

1. 原子地将会话置为 `REVOKING`，拒绝所有新请求。
2. 取消排队审批和流式传输。
3. 向运行任务发送终止，宽限后强杀整个进程树/job object。
4. 关闭浏览器并删除临时 profile、下载暂存和 IPC socket。
5. 删除会话临时工作区、备份和本地会话 token；清零内存密钥。
6. 撤销控制面 session/jti，关闭 Relay channel。
7. 写入清理结果、无法删除的明确路径和最终审计链头。

清理不能回滚 Agent 已经获准写入用户目录的业务结果；产品需把“撤走运行环境”和“撤销已产生的文件改动”区分开。若需要撤销编辑，使用会话 staging/备份并提供人工 review-and-apply，而不是承诺万能回滚。

### 12.2 异常恢复

- Host 每次启动扫描带 Molt marker 且已过期的临时目录；只清理自己创建、路径和 owner 校验通过的对象。
- 保存一个不含秘密的本地 active-session journal，用于崩溃后找到进程组、profile 和临时目录。
- UI 或 Relay 断开即暂停；daemon 崩溃时由 OS job/process-death 语义确保子进程退出。
- 删除失败以退避重试并通知 Host Owner，不能静默声称“已清理”。
- “一键撤销全部设备”使所有会话进入撤销；设备密钥疑似泄漏时轮换并吊销旧公钥。

## 13. 威胁模型

### 13.1 保护资产与信任边界

保护资产包括 Host 文件与账号、Agent Owner 的身份和凭据、会话内容、授权意图、审计完整性以及 Host 可用性。主要边界是 Agent Runtime↔Relay、Relay↔Host、Host daemon↔executor、executor↔OS/文件系统/浏览器。

Host Owner 不信任远端 Agent；Agent Owner也不应信任 Host 会保密其发送的任务内容。云 Relay 按“诚实但好奇且可能被攻破”设计。若 Host OS 已被管理员级恶意软件控制，本方案无法提供秘密性或审计真实性。

### 13.2 主要威胁与缓解

| 威胁 | 典型路径 | MVP 缓解 | 剩余风险/后续 |
|---|---|---|---|
| 配对劫持 | 猜短码、替换二维码、Relay MITM | 高熵邀请、单次消费、限速、双端核对短语、设备签名 | 被钓鱼的人仍可能主动确认错误对象 |
| token 重放/窃取 | 日志泄漏、内存抓取、代理转发 | 短期 PoP token、jti、audience、TLS/E2EE、日志脱敏 | 已攻陷端点可在有效期内冒用 |
| 权限升级 | Agent 伪造 policy version 或调用隐藏 RPC | Host 本地策略为准、能力 allowlist、参数绑定审批 | executor/策略实现漏洞 |
| 路径逃逸 | `..`、symlink、junction、TOCTOU、ADS | handle-relative API、打开后校验、拒绝设备路径 | 跨平台文件语义边角需持续模糊测试 |
| 命令逃逸 | shell 注入、子进程脱离、提权 | argv API、低权限 sandbox、job/process group、禁提权、fail-closed | OS 沙箱尤其 Windows 仍可能只有 partial |
| 凭据外泄 | 读取 `.env`、SSH agent、浏览器 cookie | 敏感路径 deny、清洁环境、临时浏览器 profile、模型 key 不下发 | 用户主动授权的文件可能本身含秘密 |
| 浏览器 SSRF | 访问 localhost、metadata、内网管理页 | URL/IP 双重校验、DNS 重绑定防护、禁本地协议和私网 | 允许公网网站可能代理间接访问资源 |
| 提示注入 | 文件/网页诱导 Agent 扩权或泄密 | 工具层硬策略、审批展示真实参数、Agent 内容不等于授权 | 用户可能被社会工程误导批准 |
| Relay 滥用 | 偷看/修改/丢弃/排序消息 | E2EE、签名、sequence、哈希链、deadline | Relay 可观察流量元数据并拒绝服务 |
| 拒绝服务 | fork bomb、大输出、磁盘填满、无限浏览 | 资源/时间/字节/并发限额、背压、配额、kill tree | 本地内核/浏览器漏洞可造成更大影响 |
| 清理不彻底 | 崩溃、锁文件、进程脱离 | journal、启动扫描、OS job、清理报告 | 已写用户文件和外部网站副作用不可自动抹除 |
| 供应链攻击 | 假 Host、自动更新被替换 | 代码签名、公证、签名更新、固定依赖、可复现构建方向 | MVP 手工分发需特别提示校验来源 |
| 审计伪造 | 子进程写假日志、删本地日志 | daemon 独占日志、结构化带外事件、哈希链、双方签名 | 管理员级 Host 可篡改本机一切 |

### 13.3 发布安全门槛

公开测试前至少完成：E2EE、签名安装包、沙箱功能探测与失败闭合、路径逃逸测试、token 重放测试、断连/崩溃清理测试、统一限额、第三方依赖扫描和外部安全评审。未达到时产品应标注 developer preview，并只用非敏感测试数据。

## 14. 跨平台落地

### 14.1 共用核心

建议采用 Rust 实现 Host daemon、协议、策略和文件安全层，减少单二进制分发和内存安全风险；UI 可先用本地 Web UI/Tauri，后续按平台增强。Agent provider 可用 TypeScript，便于接入 OpenClaw 工具体系。浏览器通过 Playwright sidecar 或协议适配层。

共用接口包括：

- `SessionTransport`
- `PolicyEngine`
- `FileCapability`
- `CommandSandbox`
- `BrowserCapability`
- `SecretStore`
- `AuditSink`
- `PlatformLifecycle`

平台差异只实现这些 seam，不在业务层散布 `if platform`。

### 14.2 平台交付

- **macOS**：universal 或 arm64/x64 签名 app，Developer ID + notarization；Keychain；原生目录选择/TCC；launch agent 仅在用户选择安装常驻版时启用，MVP 一次性版不持久化。
- **Windows**：签名 MSIX/MSI 或便携 exe；DPAPI；原生文件选择；受限 token、Job Object、ACL；不要要求管理员安装作为默认路径。
- **Linux**：x64/arm64 AppImage/静态包起步；Secret Service 或一次性身份；bubblewrap/Landlock 功能探测；明确支持的发行版和内核矩阵。

CI 在三套原生 runner 上构建和执行集成测试；每个平台包附 SBOM、签名和校验和。沙箱探测结果是运行时权威，OS 版本号只用于诊断。

## 15. MVP 分阶段计划

### Phase 0：明天可演示（1 天）

目标是验证“邀请—授权—可见执行—撤销—清理”的产品闭环，不验证生产安全。

- 单个临时 Relay（可用 WebSocket），会话保存在内存。
- Agent 侧 CLI 和 Host 侧本地 Web UI/CLI。
- 二维码/链接包含高熵邀请；Host 确认 Agent 名、目录和 15 分钟时限。
- 支持 macOS/Linux：`fs.list`、`fs.read`、`fs.write`；可选受限命令 allowlist（如 `pwd`、`ls`、`rg`、测试脚本）。
- 逐条显示活动和批准按钮；Stop 立即拒绝新请求并杀子进程。
- 使用专门创建的 demo 目录；退出删除 Molt 临时目录并输出 JSONL 审计日志。
- 明示限制：Relay 可见明文（若尚未做 E2EE）、没有生产级沙箱、不可用于真实敏感机器。

演示脚本：发起方生成二维码 → 目标机加入并选择 demo 目录 → Agent 读取 README → 请求创建 `result.txt`，Host 批准 → 请求一个被策略禁止的根目录读取并展示拒绝 → 运行测试命令 → Host 点击 Stop → 再次调用失败 → 展示审计和临时目录已清理。

### Phase 1：可信本地 MVP（1～2 周）

- 完整状态机、短期 token、policy version、幂等与断线语义。
- 原生目录选择器、handle-relative 路径防护、原子写和回收站删除。
- 终端进程树、timeout/资源限额、三平台 sandbox probe；不满足即关闭终端。
- 追加式本地审计、敏感字段脱敏、崩溃 journal 和启动清理。
- macOS/Linux/Windows CI 和最小签名安装包。
- 浏览器仍可不进此阶段，以降低攻击面。

### Phase 2：可邀请测试（2～4 周）

- 设备密钥、短语核对、X25519 E2EE、PoP token、撤销和密钥轮换。
- 多租户控制面、持久化会话元数据、限速、监控和滥用处理。
- Playwright 临时浏览器 profile、导航/上传/提交审批和 SSRF 防护。
- 权限模板（只读文件、代码协作、浏览器调研）和差异 review。
- 签名更新、SBOM、依赖/协议模糊测试、渗透测试修复。

### Phase 3：公开 MVP（4～8 周）

- P2P/TURN 优化但保留 Relay 回退。
- 更强的 Windows AppContainer、Linux seccomp/cgroups、macOS helper 隔离。
- 组织策略、设备管理、审计导出与留存设置。
- 可恢复的文件变更集：staging、diff review、apply/rollback。
- 明确支持矩阵、SLO、事件响应和安全披露流程。

## 16. 明天演示版的具体切法

为保证一天内完成，应刻意少做：

### 16.1 组件

- `relay`: 约百行的 WebSocket 房间转发服务，只允许两个参与者和 15 分钟 TTL。
- `host`: CLI 或 localhost UI，生成/消费会话，选择固定 demo 根，执行结构化文件 API。
- `agent-provider`: 把三到四个远端工具暴露给现有 Agent；无 Agent 框架时可用脚本顺序调用模拟。
- `audit.jsonl`: Host 本地逐事件 append，最后打印摘要和链头。

### 16.2 强制护栏

- Host 只能在命令行显式传入的 demo 根下工作；启动时拒绝 `/`、用户主目录、系统盘根等宽泛目录。
- 不提供任意 shell；如必须演示终端，只允许固定命令 ID 映射到固定 argv。
- 单文件上限 1 MiB，输出 256 KiB，命令 30 秒，会话 15 分钟，最多一个活动任务。
- 所有写操作 ask；路径校验和调用策略都在 Host 执行。
- Relay 断开立即冻结；Host 退出通过进程组清理子进程和临时目录。
- 界面常驻红色 Stop，活动日志同时显示给 Host Owner。

### 16.3 明日验收清单

- 邀请只能使用一次，过期后失败。
- 未经 Host 确认，Agent 看不到任何能力。
- `../`、绝对路径和 symlink 逃逸测试均被拒绝。
- 未批准写入不会发生；批准参数被修改后需重新批准。
- Stop 后 1 秒内新调用失败，活动子进程被终止。
- demo 根外没有新增/修改文件；临时目录被删除或明确报告残留。
- `audit.jsonl` 能串起请求、决策、结果、撤销和清理。

## 17. 建议的数据与 API 边界

控制面 API 最少包括：

- `POST /v1/invitations`
- `POST /v1/invitations/{id}/claim`
- `POST /v1/sessions/{id}/consent`
- `POST /v1/sessions/{id}/revoke`
- `GET /v1/sessions/{id}`（只返回调用方可见元数据）
- `WS /v1/relay`（鉴权后升级）

会话通道消息最少包括：

- `session.hello / session.ready / session.pause / session.revoke`
- `policy.propose / policy.accept / policy.replace`
- `capability.describe`
- `capability.request / approval.required / approval.decision`
- `capability.started / output / result / cancel`
- `audit.checkpoint / cleanup.result`

错误使用稳定机器码：`DENIED`、`APPROVAL_REQUIRED`、`POLICY_STALE`、`TOKEN_EXPIRED`、`SANDBOX_UNAVAILABLE`、`OUTCOME_UNKNOWN`、`LIMIT_EXCEEDED`、`SESSION_REVOKED`。不要让 Agent 通过解析自然语言错误决定安全行为。

## 18. 关键取舍与待验证问题

- **远端能力代理，而非迁移完整 Agent**：显著减少 Host 上的代码、密钥和持久化面；代价是依赖网络，且“部署”更准确地说是临时附着一个身体。
- **Relay 优先，而非先做 P2P**：最快跨 NAT 落地；代价是运营成本和流量元数据暴露，靠 E2EE 降低内容风险。
- **临时浏览器 profile，而非复用登录态**：安全边界清楚；代价是部分任务需要重新登录，且 Host Owner 需本地输入秘密。
- **结构化文件 API 优先于 shell**：更容易授权和审计；代价是工具覆盖较窄，但非常适合 MVP。
- **跨平台产品、分级能力**：三平台都能配对和做文件操作，不强求首日三平台终端隔离“完全等价”。UI 必须展示实际 enforcement，而不是制造虚假一致性。

需通过原型/用户测试回答：Host Owner 是否理解权限卡片；逐操作审批的可接受频率；Agent 遇到 `outcome_unknown` 的恢复行为；浏览器本地密码输入的体验；Windows 沙箱能否在非管理员安装下达到可接受边界；审计摘要应为谁保留多久。

## 19. 成功指标

MVP 的首要指标不是调用量，而是可控性与信任：

- 配对到首次成功操作的中位时间低于 2 分钟。
- 100% 能力调用有对应策略决策与审计事件。
- Stop 到拒绝新调用低于 1 秒；活动任务终止低于 3 秒（不可中断 OS 调用除外并明确报告）。
- 自动化路径逃逸、token 重放、断连重放、清理测试零通过漏洞。
- Host Owner 在可用性测试中能准确回答“Agent 能看什么、能改什么、何时结束”。
- 会话结束后无 Molt 进程、临时 profile、token 或未报告临时目录残留。

## 20. 最终建议

先把 Agent Drop 做成一个“临时、结构化、用户在场”的远端能力会话，而不是通用远控或远端代码执行平台。第一条纵向切片只需文件能力、显式批准、实时活动、Stop 和清理；随后按顺序补齐 E2EE/设备身份、平台沙箱、浏览器和生产控制面。任何时候，如果权限边界无法被系统实际强制，就关闭该能力并明确原因。

这条路径既能在明天演示产品魔法——Agent 确实到了另一台电脑做事——又不会让演示实现反过来定义一个危险的长期架构。
