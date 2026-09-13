# R46H Card Agent

这是 R46H 主线内核 bring-up 使用的、会话级 macOS 特权代理。它解决反复执行
`diskutil`、读取 raw 分区或定点写回时每条命令都需要重新输入管理员密码的问题，但不把
一个通用 root shell 留在后台。

## 使用

构建产物、Swift 缓存、会话日志和克隆文件全部位于外置工作区的 `mainline/out/`：

```bash
mainline/scripts/build-r46h-card-agent.sh
mainline/scripts/start-r46h-card-agent.sh --device /dev/disk4
```

默认固定使用原 31,914,983,424-byte g92 卡 profile。已经完成专用初始化和重插审计的
31,719,424,000-byte Debian 13 卡必须显式选择第二个受审计 ID：

```bash
mainline/scripts/start-r46h-card-agent.sh \
  --device /dev/diskN \
  --profile-id hl-r46h-v22-g92-31719424000-v1
```

完整 p3 recovery-v1 镜像由 Linux `mkfs.exfat -U` 构造。其磁盘 GUID 字节在 macOS
`diskutil` 中显示为 `5C29F5E1-124B-4AA5-ACB7-317194240001`，因此完整恢复后的同一张卡
必须使用单独的只读审计身份：

```bash
mainline/scripts/start-r46h-card-agent.sh \
  --device /dev/diskN \
  --profile-id hl-r46h-v22-g92-31719424000-p3-recovery-v1
```

包装器不接受自定义 profile 路径：三个 ID 分别映射到仓库内固定文件和固定 SHA-256，
Swift 核心也只接受这三个精确身份。未给 `--profile-id` 时仍保持旧 profile 行为。

第二条命令只在启动时请求一次管理员密码，并一直在前台显示：

- 当前连接客户端的 PID、UID 与可执行文件路径；
- 正在执行的固定命令、状态和进度；
- 最近事件，以及完整的 `events.jsonl` 会话日志路径。

在另一个终端执行命令，无需再输入管理员密码：

```bash
mainline/scripts/r46h-cardctl.sh status
mainline/scripts/r46h-cardctl.sh clients
mainline/scripts/r46h-cardctl.sh card-info
mainline/scripts/r46h-cardctl.sh unmount
mainline/scripts/r46h-cardctl.sh hash-raw prefix
mainline/scripts/r46h-cardctl.sh mount-readonly boot
mainline/scripts/r46h-cardctl.sh hash-file boot boot.ini
mainline/scripts/r46h-cardctl.sh list-dir boot .
mainline/scripts/r46h-cardctl.sh stop
```

文件路径参数必须是没有 `.`、`..` 或符号链接跳转的相对路径；`list-dir` 单独允许用 `.`
表示卷根目录。raw 哈希和克隆前要求三个分区全部卸载；克隆只会在本次会话目录创建新文件，
样本读取最多 64 MiB。

## 关闭语义

代理不是 daemon，也不会开机启动。关闭前台窗口、按 `Ctrl+C`，或执行 `r46h-cardctl.sh
stop` 都会请求停止：

- raw 只读操作会在下一个数据块边界取消，`diskutil`/`fsck` 子进程会被终止，未完成的克隆
  自动删除；
- 已开始的分区写入不会因信号、客户端断开或进度显示失败而中断；代理完成写入、同步和
  整分区读回校验后才退出；
- 退出不会再启动新的挂载或卸载命令，卡保持最后一个已完成命令留下的挂载状态；控制
  socket 和会话 token 随即删除。需要固定状态时应在关闭前显式执行 `unmount`。

若物理拔卡、读写器故障或底层 I/O 错误发生在写入中，软件无法保证完成剩余写入；这种卡
仍必须按失败卡处理。这里的“延迟关闭”只保证人为停止和通讯故障不会主动制造半写。

## 权限边界

默认 `audit` 模式不存在写分区命令。代理不解析 shell，不接受任意可执行文件，也不能将
输出写到会话目录之外。每次卡操作都会核对外置可移动 USB、容量、扇区、FDisk 几何、
分区 UUID 和 16 MiB g92 前缀 SHA-256。

本地控制 socket 只允许启动代理的 UID 连接；每个连接还要提供随机的 256-bit 会话 token，
服务端通过内核读取对端 PID/UID，并把实际进程路径显示在前台。root 所有的 `flock` 保证
同一用户同时只有一个代理实例。授权后，启动包装器先把 Agent 复制到 root 私有的 `0700`
临时目录，再由 root 复核副本的大小、权限和 SHA-256 后启动；该目录在 Agent 完全退出后
删除，避免管理员密码提示期间按用户可写路径执行被替换的二进制。

写卡必须另起一个 `deploy` 会话，并同时提供写计划和计划 SHA-256：

```bash
mainline/scripts/start-r46h-card-agent.sh \
  --device /dev/disk4 \
  --profile-id hl-r46h-v22-g92-v1 \
  --deploy \
  --write-plan /absolute/path/write-plan.json \
  --write-plan-sha256 <64-lowercase-hex>
```

计划只能引用仓库根目录内、大小恰好等于 p1/p2/p3 整分区的镜像；每项还必须提供来自独立
审计或候选基线收据的 `target_sha256_before`。代理从同一个 FD 读取并校验计划；执行时先
通过 Disk Arbitration 对 whole disk 取得独占 claim，再打开并持有 whole/p1/p2/p3 raw FD，
用 ioctl 证明 base/size，并在固定的目标分区 FD 上完整哈希。目标摘要不匹配时会在创建
`WRITE_IN_PROGRESS` 状态或写入任何字节前拒绝。随后代理把源镜像复制并哈希到已解除路径名
的 root 私有 staging FD。修改卡之前，代理还会在目标 `O_RDWR` raw FD 上执行一次无写入的
`DKIOCSYNCHRONIZECACHE` 兼容性预检；只有目标基线、预检和 staging 哈希都通过后，才 fsync
`SAFE_TO_BOOT=no` 状态文件并开始写卡。写完分区后先
`fsync` 目标 FD，再通过同一 ioctl 请求介质缓存落盘，随后用同一目标 FD 完整读回，并证明
g92 前缀与设备路径身份未变，才原子发布完成状态和 JSON 收据。每个计划操作在一个会话内
最多尝试一次。`F_FULLFSYNC` 只适用于 macOS 支持的文件系统 FD，不能代替 raw 设备的缓存
同步 ioctl。

这仍是开发期工具，不替代签名安装的 macOS `SMAppService`/XPC helper。威胁模型把启动
会话的 macOS 用户及其同 UID 进程视为受信任主体：token 的 `0600` 权限隔离其他用户，不能
隔离同 UID 恶意进程；TUI 中的 PID 和可执行路径用于审计，不是代码签名或客户端认证。
会话目录和收据也由该用户持有，是可核查的操作记录，不是防同 UID 篡改的取证日志。它的
安全目标是防误操作、限制命令与路径，并把当前 R46H 实验中的管理员授权缩成可见、可关闭、
白名单严格限定的一次前台会话。

`/Volumes/Ju` 当前启用了 macOS `MNT_IGNORE_OWNERSHIP`（磁盘工具显示 `Owners: Disabled`）。
代理会通过目录 FD 的 `fstatfs` 明确识别该标志，而不是把 root 视角下动态显示的 UID 0
误判为目录劫持。控制 socket、token 和实例锁仍位于启用所有权的系统卷；但外置卷上的会话
日志、收据和 clone 文件不具备不同本地用户之间的权限隔离，因此仍只属于操作记录。
