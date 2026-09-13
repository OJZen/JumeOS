# R46H Debian 13 新卡初始化

这条流程只适用于已经只读核对为以下身份的可擦除 TF 卡：

- whole disk：`31,719,424,000` bytes，512-byte sector；
- macOS 报告为 external、removable、physical USB media；
- 初始布局只有一个 Linux 分区，offset `16,777,216`、size `31,373,393,920`；
- 不是保存工作区的 `/dev/disk6`。

它会永久替换目标卡的 MBR、g92 loader、BOOT、root 和 EASYROMS 文件系统。EASYROMS
在文件系统层面为空，但这里只重建其前 16 MiB 元数据区，不是安全擦除；原卡未分配区域中的
旧字节仍可能被取证恢复。

旧 `hl-r46h-v22-g92-v1` Card Agent profile 固定了另一张卡的总容量、p3 长度和 UUID，不能
为了让这张卡通过而放宽 profile。初始化仍使用专用的固定布局 helper；完成阶段二审计后，
后续 Card Agent/EASYROMS 工作流显式使用
`hl-r46h-v22-g92-31719424000-v1`。该 profile 固定本卡的完整几何、p3 UUID 和 g92 前缀，
不能用于其他“大小相近”的介质。

如果 p3 后续被 [`../p3-recovery/README.md`](../p3-recovery/README.md) 的完整 Linux
exFAT recovery-v1 镜像替换，macOS 会把该镜像的磁盘 GUID 显示为
`5C29F5E1-124B-4AA5-ACB7-317194240001`。此后只读 Card Agent 审计必须改用精确的
`hl-r46h-v22-g92-31719424000-p3-recovery-v1`；初始化后、恢复前的 profile 仍保持冻结，
不能通过放宽 UUID 校验来兼容两种状态。

## 阶段一：写入并完整回读

先用 `diskutil list external physical` 重新确认本次 whole-disk 名称。下面的 `disk12` 只是
本次审计时的示例；重新插拔后必须按实时结果替换，且不要同时插入其他存储设备。

```bash
mainline/scripts/build-r46h-card-layout-provision.sh
mainline/scripts/provision-debian13-new-card-layout.sh \
  --device /dev/disk12 \
  --confirm-device /dev/disk12
```

helper 的 raw 写入顺序固定为：p1/p2/p3 payload 并同步；g92 prefix 的 sector 1 以后并
同步；最后写含 MBR 的 sector 0 并再次同步。之后完整回读 prefix、p1 和 p2，复核 p3
元数据与源文件，最后才弹卡。

阶段一成功也只能接受：

```text
R46H_LAYOUT result=pass state=MEDIA_WRITE_COMPLETE safe_to_boot=no next=reinsert-and-audit
SAFE_TO_BOOT=no
```

此时不要启动。任何错误、读卡器掉线或缺少最终 marker 都按不可启动处理；保留收据，不要
盲目重跑。

## 阶段二：重插后的同介质审计

把同一张卡重新插回 Mac，再次从 `diskutil list external physical` 取得实时设备名，然后运行：

```bash
mainline/scripts/audit-debian13-new-card-after-reinsert.sh \
  --device /dev/disk12 \
  --confirm-device /dev/disk12
```

审计不以写模式打开卡，也不修复文件系统。一个 C 进程在整个事务中保持同一个 Disk
Arbitration whole-disk claim 和同一个只读 raw FD：

1. 核对精确 g92 prefix，完整读取 p1 和 p2，并读取 p3 前 16 MiB；
2. 从该固定 FD 生成 root-owned BOOT 快照和 sparse EASYROMS 快照；
3. 只对虚拟快照执行 `fsck -n`、只读挂载、BOOT 锚点与 EASYROMS 根目录白名单检查；
4. 仍从同一 FD 再次完整读取 p1、p2 和 p3 头，复核设备身份与未挂载状态；
5. 由同一 C 进程弹出所 claim 的介质，节点消失后才输出最终 raw marker。

p1 和 p3 允许 macOS automount 造成的合法 FAT/exFAT 元数据变化：p1 由只读 fsck、固定
v0.8 文件锚点和前后完整摘要稳定性约束；p3 由只读 fsck、根目录白名单和前后头部摘要稳定性
约束。p2 必须两次完整匹配 canonical Debian 13 SHA-256：
`6a4254a8e66c110405cf068317da5922bb5ddfe2a02535d1a381fe1303876c96`。

只有最终同时出现以下结果，才能把卡插回 R46H：

```text
R46H_MEDIA_AUDIT result=pass ... card_state=ejected
SAFE_TO_BOOT=yes
P2_SHA256=6a4254a8e66c110405cf068317da5922bb5ddfe2a02535d1a381fe1303876c96
CARD_STATE=ejected
```

随后按主文档的首次启动流程，在按电源前以 1500000 8N1 开串口，并在
`I/TC: OP-TEE version` 后切换到 115200。

## v0.9 单次启动准备

阶段二审计只证明 Debian 13 新卡基线可启动。v0.9 不覆盖该基线，而是按以下顺序推进：

1. 按 [`../deploy/NEW-CARD-V08-SEED.md`](../deploy/NEW-CARD-V08-SEED.md)
   向原本空白的 p3 写入精确 v0.8 baseline anchors。seed 必须绑定阶段二完整 p2 审计；
   本轮只做 p2 首尾抽样，不把它冒充第二次完整 p2 哈希。
2. 从最终 clean Git HEAD 重新 canonical build v0.9，然后用新卡 profile、v0.8 baseline 和
   `--action-policy install-modules-only` 生成并侧装 EASYROMS bundle。
3. 在仍运行 v0.8 时，只执行受外部收据授权的 `install-modules`。该 bundle 不含
   `switch-boot.sh`，任何 `switch-boot` 请求都必须在目标变化前失败。
4. 关机后完整克隆实时 p1，按
   [`../p1-candidate/README.md`](../p1-candidate/README.md) 离线构造并通过 Card Agent
   完整写回 p1 候选。活动 `boot.ini`、v0.8 Image/DTB 均保持逐字节不变。
5. 串口中断 U-Boot，只在 RAM 中执行哈希固定的 v0.9 加载命令，不执行 `saveenv`。
   普通重启继续自动进入 v0.8，直到 v0.9 输入修复和其余门禁全部有实机证据。

host 构建、模块安装、p1 写回和一次性启动各自有独立收据；任何一项失败都不能用后一项
掩盖，也不能把 v0.9 host artifact 证据写成实机通过。
