# R46H Debian 13 p2 MVP

> **历史冻结文档：**本文件只描述 v0.1/v0.8 阶段的 p2 构建与实机证据，不描述当前
> R46H 卡或当前产品。现状以[项目上下文](../../docs/PROJECT-CONTEXT.md)和
> [R46H 实验账本](../board/r46h/EXPERIMENT-STATUS.md)为准；下面的旧写卡命令不构成再次执行授权。

这里构建的是与当时 R46H 测试卡 **p2 分区精确等长** 的 Debian 13 arm64 ext4
根文件系统。它复用已经在实机验证过的 g92 U-Boot、v0.8 主线内核和 DTB；首版不修改
MBR、引导器、BOOT(p1) 或 EASYROMS(p3)。

首版发布门禁只包括：

- Debian GNU/Linux 13、systemd multi-user 和 `ttyS2` 串口登录；
- 测试用户 `ark`（UID 1000，串口初始密码 `ark`）、锁定 root 登录、仅密钥认证的 OpenSSH；
- `6.12.99-r46h-mainline-v0.8-bootloader-handoff` 的完整模块树；
- Debian snapshot 中固定版本的 Mesa/libdrm 与 Panfrost 无显示 shader/FBO/readback；
- Realtek 固件、`rtl8xxxu`、NetworkManager 及可审计的 USB 序列号到 MAC 修复；
- ext4 离线检查、精确分区长度、完整镜像 SHA-256，以及后置生成的 Card Agent 会话写计划。

它不自动启动 GUI，不执行 KMS page flip，不自动播放声音，也不声称内屏、音频、输入、
Wi-Fi 关联、充电、电池标定、休眠或完整 ArkOS/EmulationStation UI 已经可用。这些外设必须
在 Debian 13 成功启动后分别验收。

## 构建

构建输入必须先提交，且相关 Git 路径必须与 `HEAD` 一致。主机侧的导出 tar、临时收据、
缓存和最终大镜像均位于外置工作区的 `mainline/out/`。为保持 Linux UID、mode 和 setuid
语义，ext4 组装期间会短暂使用 Docker Engine 管理的 named volume；它与 Docker image/
BuildKit cache 不属于 `mainline/out/`，构建退出时会精确删除临时 volume，不执行宽泛 prune：

```bash
mainline/scripts/build-debian13-rootfs.sh
```

默认输出目录为：

```text
mainline/out/r46h-debian13-p2-mvp-v0.1/
```

其中 `r46h-debian13-p2-mvp-v0.1.ext4` 必须恰好为 `10,716,877,312` bytes。
ext4 使用 4 KiB block，只覆盖前 `2,616,425` 个完整 block；分区末尾额外的 512 bytes
显式保持为零并纳入镜像 SHA-256。canonical 产物不固定 `/dev/diskN`；写计划只在 TF 卡
重新接到 Mac、核对实时设备路径以后单独生成，并且只允许 Card Agent 写 `root` 分区。

APT 使用 Debian 官方 snapshot `20260713T000000Z`。snapshot 通过 HTTP 传输，但 apt
仍严格校验 Debian archive key 签名；关闭 `Valid-Until` 只为允许冻结快照，不关闭签名或
包哈希校验。构建收据记录 InRelease、所有已安装包、Git 快照、内核包和最终镜像摘要。

## 写入测试卡

本节适用于已经匹配 `hl-r46h-v22-g92-v1` profile 的三分区测试卡。对于总容量
`31,719,424,000` bytes、当前只有一个 Linux 分区的可擦除新卡，不要复用该 profile 或下面
的 p2-only 计划；使用 [`NEW-CARD.md`](NEW-CARD.md) 的两阶段全盘初始化与重插审计流程。

先关闭 R46H，取出要写入的测试卡并接到 Mac。不要假设它仍是上一次的 `disk4`；先用
`diskutil list external physical` 找出本次实际的 whole-disk 路径。下面的 `disk4` 只是
示例，只有容量、三分区布局、UUID 和 g92 前缀均由 Card Agent 实时核对通过时才能继续：

```bash
mainline/scripts/start-r46h-card-agent.sh --device /dev/disk4
```

保持这个前台窗口开启，在另一个终端只读核对并停止 audit 会话：

```bash
mainline/scripts/r46h-cardctl.sh card-info
mainline/scripts/r46h-cardctl.sh stop
```

只在 `card-info` 精确匹配 `hl-r46h-v22-g92-v1` 后，按本次设备路径生成候选计划：

计划还必须绑定一份此前独立保存的完整 p2 审计摘要。该摘要不能取自本次现场读取后再自我授权，
也不能用“当前读到什么就写什么”代替；下面的占位值必须换成保留收据中已审核的完整分区 SHA-256：

```bash
mainline/scripts/generate-debian13-write-plan.py \
  --device /dev/disk4 \
  --target-sha256-before 64-lowercase-hex-from-retained-full-p2-audit
```

生成器不访问卡，也不把候选计划称为实时设备证据。记下它打印的绝对 `WRITE_PLAN` 和
`WRITE_PLAN_SHA256`，再开启一个新的 deploy 前台会话：

这个命令默认保持原始 v0.1/31.9 GB 行为。后续产品 p2 必须同时显式指定其
`--artifact-id` 和已现场核对的 `--profile-id`；当前 gaming v0.4 的唯一命令见
[`../rootfs-debian13-gaming/README.md`](../rootfs-debian13-gaming/README.md)。

```bash
mainline/scripts/start-r46h-card-agent.sh \
  --device /dev/disk4 \
  --deploy \
  --write-plan /absolute/path/from/WRITE_PLAN \
  --write-plan-sha256 64-lowercase-hex-from-WRITE_PLAN_SHA256
```

另一个终端再次核对，并在任何写入前只读挂载 BOOT，核对活动 v0.8 三个锚点：

```bash
mainline/scripts/r46h-cardctl.sh card-info
mainline/scripts/r46h-cardctl.sh mount-readonly boot
mainline/scripts/r46h-cardctl.sh hash-file boot boot.ini
mainline/scripts/r46h-cardctl.sh hash-file boot Image.mainline-v0.8-bootloader-handoff.gz
mainline/scripts/r46h-cardctl.sh hash-file boot rk3326-r46h-mainline-v0.8-bootloader-handoff.dtb
```

三个结果必须分别为：

```text
boot.ini: bytes=1427 sha256=cead3fbee0d5c42fddcd6f6d83839b82af791e1abf1dd0252d9850fb47dd33fb
Image.mainline-v0.8-bootloader-handoff.gz: bytes=14920864 sha256=d7c7796c097fbe692412fb63d19c1f97c4b21f55ae2c3b1e8df324a739f166fa
rk3326-r46h-mainline-v0.8-bootloader-handoff.dtb: bytes=49481 sha256=7259bac7bdd063fbaed987a0d5d2bf7066e02beaacc4440849b93d5f048e3dbc
```

随后卸载整卡，完整读取一次 p1 作为本次事务的写前基线，再执行计划中唯一的 p2 写入：

```bash
mainline/scripts/r46h-cardctl.sh unmount
mainline/scripts/r46h-cardctl.sh hash-raw boot
mainline/scripts/r46h-cardctl.sh --json execute-write write-debian13-p2-mvp-v0.1
```

Card Agent 会先在独占并固定的目标 raw FD 上完整读取 p2，且只在它逐字匹配计划中的
`target_sha256_before` 后才允许发布 `WRITE_IN_PROGRESS` 或写入；随后完整哈希源镜像，写完后
完整读回 p2，同时证明 g92 前缀和设备身份未变。写入返回后，再次从新打开的 raw FD完整
读取 p1 和 p2：

```bash
mainline/scripts/r46h-cardctl.sh unmount
mainline/scripts/r46h-cardctl.sh hash-raw boot
mainline/scripts/r46h-cardctl.sh hash-raw root
```

写后 `boot` SHA-256 必须与写前逐字相同；写后 `root` 必须为
`6a4254a8e66c110405cf068317da5922bb5ddfe2a02535d1a381fe1303876c96`、
`bytes=10716877312`。这两次后置读取不是 `execute-write` 内部 FD 的重复输出，而是独立的
重新打开证明。`execute-write` 的最后一条 JSON 会在 `details.write_status` 给出状态文件
路径；必须打开该文件并确认同时含有 `state=WRITE_COMPLETE` 与 `safe_to_boot=yes`。只有
BOOT 三个文件锚点正确、p1 前后相等、重开 p2 摘要正确以及状态文件门禁四者同时成立，
才能关闭代理、弹出卡并启动。普通 `receipt` 只保存证明，不替代状态门禁；任何失败都保持
不可启动，不要盲目重试。

## 首次启动

当前活动 v0.8 `boot.ini` 已经以 `PARTUUID=c9f931c9-02` 直接启动 p2，首版无需改 BOOT。
写卡成功必须同时满足 Card Agent 的 `WRITE_COMPLETE`、`safe_to_boot=yes` 和完整 p2 回读
摘要相等。首次启动仍先于开机键打开串口：DDR/Boot1/BL31 为 1500000 8N1，在精确
`I/TC: OP-TEE version` 后切换为 115200。

v0.8 当前直接以 `rootwait rw` 挂载 p2，且首版没有 initramfs，因此不把 fstab 的 pass 字段
解释为“根分区挂载前 fsck”证据。首次启动安全性依赖构建时离线 `e2fsck -f -n`、Card Agent
完整分区写入与完整回读一致；非正常断电后的自动修复策略留到独立 initramfs/BOOT 版本。

串口登录后先核对内核、首启 marker 和 failed units，并发布一个可从串口日志直接判定的
终态：

```bash
firstboot_gate=0
kernel_release=$(uname -r 2>&1) || firstboot_gate=1
firstboot_marker=$(sudo cat /var/lib/r46h/firstboot-complete 2>&1) || firstboot_gate=1
failed_units=$(systemctl --failed --no-legend --plain 2>&1) || firstboot_gate=1
printf 'R46H_FIRSTBOOT kernel=%s\n' "$kernel_release"
printf 'R46H_FIRSTBOOT marker=%s\n' "$firstboot_marker"
printf '%s\n' "$failed_units"
[[ "$kernel_release" == '6.12.99-r46h-mainline-v0.8-bootloader-handoff' ]] || firstboot_gate=1
[[ "$firstboot_marker" == 'release=debian13-p2-mvp-v0.1' ]] || firstboot_gate=1
[[ -z "$failed_units" ]] || firstboot_gate=1
if (( firstboot_gate == 0 )); then
  printf 'R46H_FIRSTBOOT_GATE result=pass status=0\n'
else
  printf 'R46H_FIRSTBOOT_GATE result=fail status=1\n'
fi
test "$firstboot_gate" -eq 0
```

只有最后一行是 `R46H_FIRSTBOOT_GATE result=pass status=0` 才接受；内核必须逐字匹配，
marker 必须存在且逐字匹配，并且不得有 failed unit。随后按
[`../bringup-tests/ADAPTATION-READONLY.md`](../bringup-tests/ADAPTATION-READONLY.md)
先运行不提交 GPU 作业、不改变
设备状态的适配审计。它 PASS 后，才运行主动 Panfrost 基线：

```bash
sudo /usr/local/sbin/r46h-rootfs-smoke --base
```

它以 surfaceless 模式运行 Panfrost，不发起 KMS page flip，预期 Mesa 使用 render node；
完整 rootfs 的 `card0`/`card1` 仍然可见，因此这里不声称做了设备节点隔离。网络单独用
`--network` 验收；没有 Wi-Fi 凭据不会阻止基本系统 PASS。

自定义内核启用了 `CONFIG_CFG80211_USE_KERNEL_REGDB_KEYS=y`，因此 rootfs 必须将
`wireless-regdb` alternatives 固定到 upstream 数据库签名。Debian 签名只适用于包含
Debian regulatory key 的发行版内核；若启动日志出现
`regulatory.db is malformed or signature is missing/invalid`，该构建不得通过无线验收。

已发布的 canonical v0.1 镜像保持不可变，不在同一 artifact ID 下重建另一份内容。v0.1
默认选择 Debian 签名，现有卡必须在串口控制面执行版本化 hotfix；先把仓库中的脚本传到
目标 `/dev/shm/r46h-regdb-hotfix.incoming`，再执行：

```bash
sudo install -o root -g root -m 0700 \
  /dev/shm/r46h-regdb-hotfix.incoming /run/r46h-regdb-hotfix
printf '%s  %s\n' \
  'd8dc5b5ba20a4e1c3872cde139bc819bc23e2f29405e2c9381817b1ad3ef69e0' \
  /run/r46h-regdb-hotfix | sudo sha256sum -c -
sudo /bin/bash /run/r46h-regdb-hotfix
```

脚本同时固定 v0.1 marker、内核、p2 身份、`wireless-regdb` 版本和 upstream 文件摘要；唯一
持久改动是切换 alternatives，成功标记必须为：

```text
R46H_REGDB_HOTFIX id=debian13-p2-mvp-v0.1-regdb-upstream-v1 result=pass reboot_required=yes config=/proc/config.gz
```

重启后还必须证明 `regulatory.db.p7s` 指向 `regulatory.db.p7s-upstream`，且 dmesg 不再含
`regulatory.db is malformed or signature is missing/invalid`。未来将该修复内建到 rootfs 时，
必须整体升为 v0.2（artifact/output/image/firstboot marker/收据身份一起升），不得覆盖 v0.1。
独立的整合游戏镜像 v0.2 构建与 host-only 边界见
[`../rootfs-debian13-gaming/README.md`](../rootfs-debian13-gaming/README.md)；它不改变这里的
canonical v0.1，也不授权写卡。

## 2026-08-10 实机结果

31,719,424,000-byte 新卡在完整写入和重插审计后启动了 canonical v0.1。首个串口证据同时
捕获 1500000 baud 的 DDR/Boot1/BL31/OP-TEE 和切换到 115200 后的 U-Boot、Linux、systemd；
内核逐字为 `6.12.99-r46h-mainline-v0.8-bootloader-handoff`，Debian 13 到达
`multi-user.target`。首启 marker 为 root:root 0600，因此门禁必须用上文的 `sudo cat`；修正
门禁后 marker、failed units 和内核均 PASS。后续重启中 firstboot unit 为
`ConditionResult=no`，证明 marker 生效且没有重复初始化。

只读适配审计 v0.1 因 libdrm `modetest -D /dev/dri/card0` 把路径当 busid 而产生三个假失败；
v0.2 改用 `modetest -M rockchip -c -e -p` 后以 `failures=0 skips=0` 通过。它只查询到：

- `DSI-1` connected/enabled、1024x768@60，fb0 为 1024x768x32；
- Mali-G31/Panfrost、CPU/GPU OPP、Hantro encoder/decoder；
- 游戏输入、RK817 playback/capture/mixer、背光、热区、电池与充电器；
- RTL8188EU USB serial `00E04C8188FF`、稳定 MAC `00:e0:4c:81:88:ff`、模块与固件。

Panfrost surfaceless shader/FBO/readback 在四个启动周期累计运行五次，五次均得到预期像素，
且每次 `ext4_changed=0`、`dmesg_ring_wrapped=0`、`fault_detected=0`。切换 upstream regdb
签名后再次启动，签名错误消失，`iw reg get` 返回完整 global 域，稳定 MAC、failed units、
ext4 errors_count 和 Panfrost 回归继续 PASS。最终关机前 failed units=0、ext4 errors_count=0、
电量 98%；systemd 将 p2 remount 为只读并报告 `All filesystems unmounted`、`Powering off`，
此后串口静默。

同日的正式分组门禁继续得到以下结果：

- passive Wi-Fi gate 保持未关联状态，只执行 `iw ... scan passive`，发现 11 个 BSS；接口、
  `00:e0:4c:81:88:ff` 稳定 MAC、ext4 error counter、failed units 和 dmesg 后验均未漂移；
- query-only Hantro/USB preflight 正确结束为 `SKIP_TOOLING`、进程状态 77；Hantro 节点身份和
  两次 USB inventory/mount snapshot 通过，但镜像没有 `v4l2-ctl`、FFmpeg 或 GStreamer，
  因而这不是 codec 数据路径或外置 USB 端口证据；
- read-only adaptation v0.2 最终为 `failures=0 skips=0`；同一日志中更早的媒体脚本开发失败
  不属于接受结果，只有最后一个 `result=skip ... worker_status=0` marker 可采信；
- 最后一次健康检查为 systemd `running`、failed units 为空、ext4 errors_count=0，完整故障
  正则匹配为 0。外接电源仍被 RK817 报告为 `ONLINE=0`、电池 `Not charging`，因此充电路径
  继续保持未通过。正常关机再次完成 root 只读 remount、全部文件系统卸载和 `Powering off`。

输入事件采样还定位到一个内核问题：`ABS_Y` 实际约为 `-517`，但广告范围为 `180..800`。
原因是 Linux 6.12 的 `adc-joystick` 反向轴路径把 IIO channel index 传给
`input_abs_get_min()`/`input_abs_get_max()`，而不是对应的 ABS event code。补丁
`0006-input-joystick-adc-use-axis-code-for-inversion.patch` 已纳入独立版本
`6.12.99-r46h-mainline-v0.9-adc-joystick-fix`。

v0.9 canonical host artifact 的每次 clean-HEAD 构建都必须从 ignored 输出中的
`BUILD-INFO` 读取并独立复核 `package_tar_sha256`；该 README 本身参与 source snapshot，
因此不能在这里自引用钉死“当前” tar 摘要。稳定的语义锚点中，Image 为
`f5b85919d5536b7fad61f7ec4e17bc1f8edb97ad1ada0b9fa2f3d77a8a1ab48d`，DTB 为
`7259bac7bdd063fbaed987a0d5d2bf7066e02beaacc4440849b93d5f048e3dbc`，1276 个模块的
tree hash 为 `958594b4343bb72f995e0d5232c9885e3f99d9e2930a615941ceb6792c78e378`。
全部 payload checksum、tar/目录身份、source snapshot 和模块 vermagic 已闭合；这是主机侧
编译/包装证据。随后已在新卡上先侧装匹配的 v0.9 modules，再从完整 p1 clone 中只删除旧
v0.2 candidate、加入 v0.9 gzip Image 和 one-shot boot script；活动 v0.8 `boot.ini`、Image
与 DTB 均保持逐字不变。串口中只在 RAM 执行 v0.9 boot script，没有 `saveenv` 或替换活动项。
v0.9 已精确启动，Panfrost base、passive Wi-Fi、readonly adaptation 均通过；媒体仍因工具
缺失明确 `SKIP_TOOLING`。正常重启后 U-Boot 自动读取原 `boot.ini` 和 v0.8 Image，v0.8
Panfrost base 再次通过，证明 one-shot 回退成立。

这里“删除旧 v0.2 candidate”也意味着后续 modules-only 侧装不能再把未使用的 v0.2 BOOT
四件套当作前置条件。modules-only 仍须验证活动 v0.8、版本化 v0.8 Image/DTB/candidate、
U-Boot DTB、当前 EASYROMS anchors，以及侧装前后三次完整 p1 raw hash 不变；只有真正授权
`switch-boot` 的 full policy 才要求 v0.2 fallback 文件。该区别由可执行 action-policy fixture
同时覆盖正向和负向路径，避免再次在任何写入前被过时 fallback 门禁阻断。

v0.9 输入实测证明反向轴不再出现负值，但同时发现第二个独立问题：四轴观测范围分别为
`82..946`、`31..874`、`51..891`、`70..927`，均越出 DTS 广告的 `180..800`，最终仍能回中且
无 `SYN_DROPPED`。因此 v0.9 只完成 driver event-code 修复，板级 ADC range 校准仍失败。当前
v0.10 保留反向方向，只把四轴声明为完整无符号 10-bit `0..1023` 域。2026-08-15 已以独立
v0.10 DTB one-shot 启动，并安装了完整匹配模块；后续有人值守的 60 秒采集实测四轴范围为
`ABS_X=137..984`、`ABS_Y=96..924`、`ABS_RX=62..885`、`ABS_RY=72..928`，分别覆盖完整
`0..1023` 域的 80.4%--83.7%，全部回中且无 `SYN_DROPPED`，因此 ADC full-range 门禁已
PASS。`BTN_NORTH` 也取得两组完整 press/release。唯一剩余的 `BTN_TRIGGER_HAPPY5` 虽由
内核作为 active-low GPIO2_A4 `F5` 暴露，但本机没有可识别的对应实体键，采集事件为零；
这应记录为 DT/硬件身份不一致，而不是让操作者猜键。在取得原理图或通断证据前，19-key
门禁继续 fail closed，也不能宣称完整按键矩阵 PASS。

v0.10 的物理 p3 侧装证据已撤销：Mac 侧曾两次读到 canonical Image SHA-256
`736549a919eee0342a2bae961a85b59337ad8de3c901c2e5f193aa15fdead954`，但 R46H 在 50 MHz
和 25 MHz 下都稳定读到
`982fe2b483220ef4515f75f729714782f1997dca55124430fe3243d1c7f593f5`。raw exFAT 重建还证明
v0.8/v0.9 DTB 分别变成 `86cdabbaccafdb470b69efb3645d6654154eae754bc2e0c3cb37488a36cdfad1`
和 `d9e99384b745468b2d91921eb3ef2961145e0adc5f7fdec079c281c69d988db6`，而两者 canonical
值都应为 `7259bac7bdd063fbaed987a0d5d2bf7066e02beaacc4440849b93d5f048e3dbc`。因此外部收据
`e46b2b0948d124e9e611520be5b0f66d45954dc5262fe0597f6e0bc1a98b3b8e` 不再具有授权效力；
独立证明过的 prefix、分区表、p1 与 p2 不受此结论牵连，但当前 p3 必须视为不可消费。
完整 raw mapping、证据哈希及恢复门禁见
[`../deploy/EXFAT-FSKIT-POSTMORTEM.md`](../deploy/EXFAT-FSKIT-POSTMORTEM.md)。

随后已经按 postmortem 的第一条恢复路径为 62.5 GB fast card 完整重建
Linux exFAT p3，并完成全分区写入/readback 与 post-reinsert quick
immutable-payload PASS。因此“p3 不可消费”只指旧卡/旧字节和已撤销收据；当前 fast-card
p3 的三棵 payload tree 是新的、独立绑定的来源。历史 macOS 文件级 stager 仍永久禁用，
也不能因为 fast-card 恢复成功就重新消费旧收据。当前状态与避免重复实验的门禁见
[`../board/r46h/EXPERIMENT-STATUS.md`](../board/r46h/EXPERIMENT-STATUS.md)。

显示的受控 helper 进入 `KD_GRAPHICS` 后显示 8 条等宽竖色条，并在 8 个检查点完整读回，用户
肉眼确认正确，退出时 framebuffer 和 VT 均恢复。此前 fbcon 仍在 `KD_TEXT` 时直接写 fb0 得到
半白并残留命令行文字，该结果受并发重绘污染并已拒绝。当前只证明 inherited-handoff 下的
受控 scanout 更新，不证明 page flip 或 full reset/DCS。音频两次 bounded 440 Hz PCM 均正常
完成，SPK mux、音量与 DAPM Speaker 均为 active，恢复也成功，但用户确认完全无声；该结果
现在只否定 RK817 内部 SPK/Class-D 路由。后续精确 v0.10 对比按 vendor
`use-ext-amplifier` 语义改用 HP DAC：保守的 scale 20 仍听不到，唯一一次 scale 40、原系统
音量 `201,201` 的 4 秒测试则听到了微弱但明确的 440 Hz `bu~~`。机器门禁、恢复、ext4、failed
units 和 dmesg 均通过。因此物理扬声器与 HP-fed 外置功放路径成立；正常增益、耳机切换和
upstreamable machine/amp 模型仍未完成，不再重复提高音量或重测 SPK。

保留的证据文件（均位于 ignored `mainline/out`，不进入 Git）为：

- `r46h-debian13-firstboot-serial/debian13-firstboot-20260810-000603.bin`：129,534 bytes，
  SHA-256 `3d01687a239828c0539ef98c6bdac9ff813038956d4ab56303d0068d57ecb604`；
- `r46h-debian13-secondboot-serial/debian13-secondboot-postlogin-20260810-0027.bin`：17,032 bytes，
  SHA-256 `675118d6c6c1dc939dcce099f8fa73f2dbcb903d98a6fc92d1b6ed8d36923131`；
- `r46h-debian13-secondboot-serial/debian13-finalboot-20260810-0033.bin`：9,130 bytes，
  SHA-256 `bf4bce992c706da66dd53bfb31d0790cba5cd995c8db684a10e608eb87e73ca6`；
- `r46h-debian13-secondboot-serial/debian13-regdb-postboot-20260810-0048.bin`：14,249 bytes，
  SHA-256 `5b0eb9990252d6bc7ab4451513918e78b08bd1a4fcb89c4069048af6a9919e8d`。
- `r46h-active-gates-serial/active-gates-20260810-080725.bin`：171,450 bytes，
  SHA-256 `7231c4d0ad60782e0595f2b0487443c0628178078db4d766bcec61d62ce64510`；该日志包含
  passive Wi-Fi、媒体 preflight、read-only adaptation、最终健康检查和正常关机收据。
- `r46h-serial-logs/v09-one-shot-20260810T230435Z.log`：89,070 bytes，SHA-256
  `aec087f408d394ba992030813bf415eacfed3b6ae526dc7e7dad2d70c273d72e`；包含 v0.9 one-shot
  启动、Panfrost、输入、显示与两次受控音频动作；
- `r46h-serial-logs/v09-runtime-reconnect-20260810T154225Z.log`：73,838 bytes，SHA-256
  `b175f22a71a021718b3584b201c70e461f4f0b36c79611ac36f176db9df02874`；包含 v0.9 passive
  Wi-Fi、adaptation 与 media/USB 最终 marker；
- `r46h-serial-logs/v09-shoulder-reconnect-20260810T155312Z.log`：3,951 bytes，SHA-256
  `7acbc31abd35def8c9a4ea8d12ef0ef71485b5080501d27de636ac416d476b3a`；包含四个肩键成对
  press/release 与 v0.9 最终健康门；
- `r46h-serial-logs/v09-fallback-v08-20260810T155625Z.log`：86,206 bytes，SHA-256
  `02ba73a06a2dc927ed57c8fb9255e0aa1a567d5708a05e8ba2e2aa39c57cf84c`；包含自动回退 v0.8、
  Panfrost base PASS、最终只读 remount、完整卸载和 `Powering off`。

这些结果仍不证明 KMS page flip、panel full-init、录音/耳机、Hantro 编解码负载、Wi-Fi
关联/吞吐、外部 USB、充电、电池标定或 suspend/resume。扬声器已从“未测”升级为“受控 PCM
工作但物理无声”，按键/摇杆也已有实机事件但尚未完整通过。虽然接有外部电源，RK817 本轮
持续报告 `charger_online=0` 和 `Discharging`，因此充电路径仍是明确未通过项，不能用本轮
稳定运行替代。

镜像不预埋任何 SSH 公钥，也不允许用公开的测试密码远程登录。首次串口登录后，可把自己的
公钥写入 `/home/ark/.ssh/authorized_keys`（目录 `0700`、文件 `0600`、所有者均为 `ark`），
再单独验收 SSH。`ark` 的初始密码仅用于物理串口和 `sudo`，日用前必须更换。
