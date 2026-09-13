# Debian 13 Mesa/Panfrost 无显示探针

> **历史冻结文档：**本文件保留 v0.1/v0.2 探针的精确证据，所有卡片和版本描述均限定在
> 2026-08-07 的实验状态，不代表当前产品，也不授权重新构建或侧载。现状以
> [项目上下文](../../docs/PROJECT-CONTEXT.md)和
> [R46H 实验账本](../board/r46h/EXPERIMENT-STATUS.md)为准。

这个探针用于回答一个狭窄问题：当时已启动的
`6.12.99-r46h-mainline-v0.8-bootloader-handoff` 能否由 Debian 13 的发行版 Mesa 通过
Panfrost render node 完成真实 shader 提交和像素回读。

它不是 Debian 13 完整固件，也不执行 KMS、page flip 或面板重初始化。它不重写或替换旧
p2 rootfs，也不改 BOOT、U-Boot 和分区表；设备正常运行仍可能在可写 p2 产生日志或元数据，
因此探针另行检查 ext4 错误计数。

## 实机结果：v0.1 A/B 与 v0.2 canonical PASS

已侧装的 v0.1 运行器让隔离根中的 `/sys` 保持为空；同一份 v0.1 SquashFS（SHA-256
`e027a0fdd59a4b767b09fe67b2a74b19330daacb5b14d75e2852f8c41c549778`）在
`eglInitialize()` 返回 `EGL_NOT_INITIALIZED`，没有进入 shader/FBO 阶段。静态复核确认镜像
包含 Debian 13 的 Mesa 25.0.7、libdrm 2.4.124、GLVND vendor JSON、
`panfrost_dri.so`/`libgallium` 及其全部动态依赖；Mesa 和 libdrm 二进制也明确通过
`/sys/dev/char/<major>:<minor>/device` 查询 DRM 设备拓扑。因此“空 `/sys`”本身就是 loader
发现链缺失，第一次失败不能解释为 Panfrost kernel UAPI 不兼容。

随后针对这个已侧装 v0.1 做的实机单变量 A/B 保持 kernel、SquashFS、`renderD128`、
UID/GID、capability、Mesa 环境和超时均不变，只在私有 mount namespace 内新挂载一份
**fresh、read-only sysfs**。它不是把 host 现有的可写 `/sys` 树 bind 进 chroot；挂载点以
`findmnt` 再次证明含 `ro`。私有 `/dev` 仍只绑定 `renderD128`，`card0` 和 `card1` 均不可见。
该变体完成 EGL 初始化、真实
Panfrost shader/FBO 提交、`glFinish` 和像素回读，最终 `probe_status=0`；同时保持 p2 ext4
错误计数为零、没有新增 GPU/存储 fault、可信镜像摘要不变，临时 loop 与 tmpfs 完整清理，
并发布 `R46H_EGL_SYSFS_DIAG result=pass`。

这个 A/B 通过确认了该次 Debian 13 Mesa 到主线 Panfrost render node 的无显示渲染链路，
也确认修正后的 canonical runner 必须提供只读 sysfs 设备拓扑。它不授权暴露 KMS 节点，
也不把 sysfs 改成可写或复用 host 的 rw bind mount。

已侧装的 v0.1 bootstrap 是构建时固定的旧运行器，A/B 诊断没有也不能原地修改它；它仍会
使用空 `/sys` 并失败。修正后的 **v0.2** 已于 2026-08-07 完成 canonical 构建、仅 p3
侧装和正式实机复测。正式 artifact 来自 clean Git commit
`90c939550a0fdb5ed67307210e103f146af3da25`（`90c9395`），`BUILD-INFO` 同时记录
`source_git_dirty=false` 与 `source_snapshot_method=git-archive-exact-commit`。v0.1 A/B 只保留
为缺失 sysfs 拓扑的根因证据；该探针正式 PASS 只归属于下列 v0.2 artifact、收据和串口日志：

| 证据 | 路径或摘要 |
| --- | --- |
| v0.2 SquashFS | `mainline/out/r46h-easyroms-debian13-mesa-probe-v0.2/payload/r46h-userspace-probe-debian13-mesa-v0.2.squashfs`；SHA-256 `e027a0fdd59a4b767b09fe67b2a74b19330daacb5b14d75e2852f8c41c549778` |
| v0.2 bootstrap | `mainline/out/r46h-easyroms-debian13-mesa-probe-v0.2/payload/bootstrap-target.sh`；SHA-256 `5488239a7c7f6f0c99866e13a85483452f089e583a96d9d2bf6910b034daf1ac` |
| stage source list | `mainline/out/r46h-easyroms-debian13-mesa-probe-v0.2/STAGE-SOURCES.sha256`；SHA-256 `b0aa793ce221d28b322e280daeb39b81f3153ed8982a3ec2a8ca1bf27dc6b49b` |
| 最终外部收据 | `mainline/out/r46h-debian13-mesa-probe-v0.2-card-receipts/.r46h-r46h-debian13-mesa-probe-v0.2-final.YTUYVk/TARGET-TRUST-RECEIPT`；SHA-256 `b96bb2ac5efc03c037baa6541b2efd6f935160562817635dd540c086db70c18f` |
| 本轮串口日志（从 U-Boot 起） | `mainline/out/r46h-debian13-mesa-probe-v02-current-20260807T090217Z.bin`；43,390 bytes；SHA-256 `4a0225c8e34ebf5eceaac945cba8efaa321613d114a1fb5068578bc40dda8886` |

侧装收据记录 `only_written_partition=3`、`root_partition=never-mounted`，且 g92 前缀、分区表
和完整 BOOT p1 的写前/完成后摘要不变。目标端先分别复算 bootstrap 与外部收据，再由外部
收据、卡上 completion commitment 和可信副本摘要共同放行运行。该日志从 115200 baud 的
U-Boot 开始；开头 119 bytes 是错过切速点后的乱码，不能据此补写 1500000 baud 的
DDR/Boot1/BL31 证据。其 canonical markers 为：

```text
R46H_MESA_RUNTIME stage=preflight probe=debian13-mesa-v0.2 kernel=6.12.99-r46h-mainline-v0.8-bootloader-handoff image_sha256=e027a0fdd59a4b767b09fe67b2a74b19330daacb5b14d75e2852f8c41c549778
R46H_MESA_RUNTIME isolation=mount-pid-net-namespace uid=65534 gid=109 exposed_node=renderD128 hidden_nodes=card0,card1 sysfs=readonly probe_timeout=30s session_timeout=45s
R46H_MESA_PROBE egl=1.5 vendor=Mesa renderer=Mali-G31 (Panfrost) version=OpenGL ES 3.1 Mesa 25.0.7-2+deb13u1
R46H_MESA_PROBE pixel=51,102,153,255 expected=51,102,153,255
R46H_MESA_PROBE result=pass
R46H_MESA_RUNTIME ext4_errors_before=0 ext4_errors_after=0
R46H_MESA_RUNTIME probe_exit_status=0 dmesg_ring_wrapped=0 ext4_changed=0 fault_detected=0
R46H_MESA_RUNTIME result=pass
```

## 构建边界

> 2026-08-11 起，v0.2 身份与 packager 均已冻结，下面的构建命令只保留为历史记录，当前
> `build-userspace-probe.sh` 会在 Docker 或输出创建前 fail closed。原因不是 Mesa 探针本身，
> 而是物理 p3 的 macOS 文件级 hash 与 raw exFAT 内容不一致；原身份不能悄悄重发，未来若
> 恢复必须使用新 probe ID 和 raw-media-verified 部署路径。见
> [`../deploy/EXFAT-FSKIT-POSTMORTEM.md`](../deploy/EXFAT-FSKIT-POSTMORTEM.md)。

`build-userspace-probe.sh` 使用按 digest 固定的 `debian:trixie-slim` 基础镜像，生成 gzip
SquashFS。运行时只包含发行版 Mesa/DRM/EGL/GLES、`setpriv` 和自带 GLES2 探针；构建会拒绝
缺失 `panfrost_dri.so`、出现 `libMali` 依赖、未提交的探针输入或未解析的镜像哈希。Docker
context、目标 bootstrap、packager 和源码摘要全部来自同一个精确提交的私有 `git archive`
快照；正式目录只会在构建结束再次确认 HEAD 和相关工作区未变化后原子发布。

```bash
mainline/scripts/build-userspace-probe.sh
```

输出目录为：

```text
mainline/out/r46h-easyroms-debian13-mesa-probe-v0.2/
├── payload/
├── STAGE-SOURCES.sha256
└── stage-on-macos.sh
```

APT 包索引没有固定到 Debian snapshot，因此 BUILD-INFO、PACKAGES.tsv、容器 image ID 和源码
摘要属于本次构建收据，不承诺未来重新下载后逐字节复现同一 SquashFS。

## 侧载边界

侧载脚本复用经过故障注入测试的 EASYROMS 事务流程。它要求当时的目标卡精确匹配 v0.8 BOOT 与
EASYROMS 基线，只向 p3 新建 `r46h-debian13-mesa-probe-v0.2`，最后才发布
`STAGE-COMPLETE`。写前、正文写后和完成门写后都会证明 g92 前缀、分区表与完整 p1 未变；
p2 从不挂载。

```bash
mkdir -p mainline/out/r46h-debian13-mesa-probe-v0.2-card-receipts
chmod 700 mainline/out/r46h-debian13-mesa-probe-v0.2-card-receipts

mainline/out/r46h-easyroms-debian13-mesa-probe-v0.2/stage-on-macos.sh \
  --device /dev/disk4 \
  --confirm-device /dev/disk4 \
  --receipt-parent "$PWD/mainline/out/r46h-debian13-mesa-probe-v0.2-card-receipts"
```

设备名必须以当次 `diskutil list` 为准。该版本 Card Agent 只支持整分区镜像写入，不能替代这个
文件级 p3 事务；不要为本次约 92 MiB 的增量测试生成或覆盖完整 21 GiB p3 镜像。

## 目标运行边界

不要从可写的 EASYROMS 目录直接以 root 执行脚本。侧装成功后，先在 Mac 保存脚本打印的
`TARGET_TRUST_RECEIPT_SHA256`，并从最终收据提取 bootstrap 摘要：

```bash
RECEIPT_DIR='/absolute/path/printed/as/RECEIPT_DIR'
RECEIPT_SHA256='<literal TARGET_TRUST_RECEIPT_SHA256 printed by the stager>'
RECEIPT_FILE_SHA256=$(awk '{print $1}' "$RECEIPT_DIR/TARGET-TRUST-RECEIPT.sha256")
[[ "$RECEIPT_FILE_SHA256" == "$RECEIPT_SHA256" ]] || {
  echo 'receipt hash does not match the stager output' >&2
  exit 1
}
BOOTSTRAP_SHA256=$(sed -n 's/^bootstrap_target_sha256=//p' \
  "$RECEIPT_DIR/TARGET-TRUST-RECEIPT")
printf 'receipt=%s\nbootstrap=%s\n' "$RECEIPT_SHA256" "$BOOTSTRAP_SHA256"
```

启动 v0.8 后，通过 SSH、串口 Base64 或其他只传数据的方式把最终
`TARGET-TRUST-RECEIPT` 放到设备的临时路径。然后只创建并执行 root-owned 副本；下面两个
SHA-256 必须替换为 Mac 上刚刚得到的字面值：

```bash
sudo install -d -o root -g root -m 0700 /run/r46h-deploy
sudo install -o root -g root -m 0700 \
  /roms/r46h-debian13-mesa-probe-v0.2/bootstrap-target.sh \
  /run/r46h-deploy/bootstrap-target.sh
sudo install -o root -g root -m 0600 /tmp/TARGET-TRUST-RECEIPT \
  /run/r46h-deploy/TARGET-TRUST-RECEIPT

printf '%s  %s\n' '<BOOTSTRAP_SHA256-FROM-MAC>' \
  /run/r46h-deploy/bootstrap-target.sh | sudo sha256sum -c -
printf '%s  %s\n' '<RECEIPT_SHA256-FROM-MAC>' \
  /run/r46h-deploy/TARGET-TRUST-RECEIPT | sudo sha256sum -c -

sudo /bin/bash /run/r46h-deploy/bootstrap-target.sh \
  --external-receipt /run/r46h-deploy/TARGET-TRUST-RECEIPT \
  --external-receipt-sha256 '<RECEIPT_SHA256-FROM-MAC>'
```

bootstrap 会要求外部收据字段集合和顺序精确匹配，校验 payload、kernel、card profile、
g92、source-list、bootstrap 与 gate 摘要，并用只在安全弹出后公布的 completion secret 核对
卡上的 `FINAL-RECEIPT-COMMITMENT`。只有这些门禁全部通过，才会复制和执行探针。

修正后的 canonical 运行脚本必须：

- 要求精确 v0.8 kernel、`renderD128`、`card0` 和 p2 ext4 零错误基线；
- 将完整 source-list、gate、manifest、commitment 与 SquashFS 复制到上限 128 MiB 的
  root-only tmpfs，对所有可信副本做 SHA-256 并只读 loop mount 镜像，避免可写 EASYROMS
  上的原文件在校验后被原地修改；
- 新建 mount/PID/network namespace，私有 `/dev` 只绑定 `renderD128`，明确不暴露 `card0`
  或 `card1`；
- 在 namespace 内新挂载 fresh sysfs，并在进入 chroot 前证明其为只读；禁止把 host 的 rw
  `/sys` 树 bind 进来；随后以 UID 65534、render node GID、`no_new_privs` 和空 capability
  集运行；
- 强制 surfaceless EGL 与 Panfrost，拒绝 llvmpipe/softpipe/swrast；
- 在 30 秒硬超时内完成 shader 编译、FBO 绘制、`glFinish` 和 RGBA 像素回读；
- 无论探针成功或失败都采集 ext4 与 `dmesg` 后验，并额外等待 3 秒观察延迟 fault。

本次 v0.2 canonical `R46H_MESA_RUNTIME result=pass` 只证明 Debian 13 Mesa 到 Panfrost
render node 的无显示渲染链路成立；v0.1 fresh read-only sysfs A/B 是此前的根因诊断，不再
代替正式判定。v0.2 没有暴露 `card0`/`card1`，也不执行 KMS、page flip 或面板重初始化；
它不证明 KMS scanout、内屏显示或长期稳定、音频、输入、网络、UI，也不构成 Debian 13
完整 rootfs/镜像，不能把当前 SquashFS 探针称为 Debian 13 固件。后续可以开始独立 Debian
13 p2，但仍需为完整系统重新验收这些边界。
