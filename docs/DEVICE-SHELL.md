# Jume 桌面需求与接手入口

本页负责 Jume Launcher 的产品约定、工作范围和代码入口；最后整理于 2026-10-23。
当前进度、未提交工作和下一步只维护在 [Project Context](PROJECT-CONTEXT.md)；
完整需求编号与验收条件在 [Product Roadmap](PRODUCT-ROADMAP.md)，实机结果在
[R46H ledger](../mainline/board/r46h/EXPERIMENT-STATUS.md)。不要用旧实验编号推断当前状态。

## 用户已确认的方向

- Jume 是手柄优先的掌机桌面：Switch 风格首页、游戏库和设置，Steam Deck 风格快捷面板。
- 近期交付是**开机进入 Jume，启动失败或崩溃后退回 ES-DE，下次开机仍尝试 Jume**。
  ES-DE 保留为恢复入口；设置默认桌面与完整替换 ES-DE 是两个独立交付。
- 用户最近选择“暂时无法连接，先准备配置”。继续主机准备；设备接入后再部署和记录实机结果。
  配置文件存在、主机测试通过，都不表示默认启动已经改变。
- 保留游戏资源、原有存档、设置及回退版本；已有数据不能因安装、导入、升级或卸载而被静默覆盖。
- 优先完成启动与恢复、实际游戏流程和存档；浏览器、zram、USB gadget 等不能阻塞首次桌面试用。

## 需求范围与负责人入口

“负责人”指负责该行为的代码与文档，不依赖某个 agent 的聊天记录。验收细节复用路线图的相同编号。

| 需求编号 / 工作面 | 桌面需要提供什么 | 代码与权威文档 |
| --- | --- | --- |
| Q1：默认启动与恢复 | 启动 Jume；失败后完成资源清理再进入 ES-DE；保留下一次启动选择及手动回滚 | [Wayland PRODUCT](../mainline/gaming-wayland/PRODUCT.md)、`product-install.py`、`product-fallback.py` |
| L1、Q2：完整游戏库与替换 | 盘点现有 ES-DE 系统/ROM，明确核心、BIOS、配置和存档映射；接管入口后才评估移除 ES-DE | [Applications](../mainline/gaming-shell/APPLICATIONS.md)、[ES-DE](../mainline/gaming-es-de/README.md)、[文件布局](FILESYSTEM-LAYOUT.md) |
| G1/G2、P2–P4：本地游戏 | Metal Slug、GTA III/VC、Stardew 等逐游戏验证启动、操作、保存、退出、重进读档；SA 单独适配 | [Tools](../mainline/gaming-shell/TOOLS.md)、[Ports](../mainline/gaming-ports/README.md)、`tools.cpp`、`applications.cpp` |
| P1：PortMaster | 目录/搜索、安装、升级、回滚、卸载和运行库管理；进度、取消、错误恢复与用户数据保留 | [Ports](../mainline/gaming-ports/README.md)、`PortCatalog.qml`、`tools.cpp` |
| U1：桌面交互 | 首页/库/收藏/设置、两级导航、明确焦点和按键提示；90–130% 字号、夜间模式、减少动态效果、流畅输入 | [Jume UI v1 规范](JUME-UI.md)、[Shell](../mainline/gaming-shell/README.md)、[共享控件](../mainline/gaming-shell/controls/README.md)、`ShellView.qml`、`preferences.cpp` |
| W1/W2、R1：显示与输入 | 全屏共享显示；快捷面板拿走游戏输入，关闭时释放按键并恢复；远程控制遵守隐私与会话校验 | [Handheld](../mainline/gaming-wayland/HANDHELD.md)、[Remote Control](REMOTE-CONTROL.md)、`handheld.cpp` |
| T1：后台任务 | 预览、切换、恢复、正常关闭与强制结束；后台游戏与传输按各自策略保留状态 | [Applications](../mainline/gaming-shell/APPLICATIONS.md)、`applications.cpp`、`TaskView.qml` |
| S1–S3、H1：设置/电源/HUD | 真实 Wi-Fi、电量、音量、亮度、存储和系统信息；重启/关机、息屏唤醒、CPU/内存与性能显示 | [Device](../mainline/gaming-shell/DEVICE.md)、[Performance and Power](PERFORMANCE-POWER.md)、`device.cpp`、`network.cpp`、`telemetry.cpp` |
| F1/F2：文件、终端与传输 | Files/Text/Terminal 与 Wi-Fi 传输进入同一应用生命周期；取消不损坏原文件，私密页面不被远程截屏 | [Files](../mainline/gaming-files/README.md)、[Transfer](../mainline/gaming-files/TRANSFER.md)、[Terminal/USB 输入](../mainline/gaming-wayland/PERIPHERALS.md) |
| M1/M2、B1、I1：独立能力 | Moonlight 配对/主机/串流，浏览器和 USB 手柄输出各有运行时及硬件验收；按 Context 的暂停项执行 | [Streaming](../mainline/gaming-shell/STREAMING.md)、[Browser](../mainline/gaming-browser/README.md)、[USB gadget](../mainline/gaming-usb-gamepad/README.md) |

源码短名默认位于 `mainline/gaming-shell/`；Q1 的脚本位于 `mainline/gaming-wayland/`。
当前固定 Neo/native 入口与手工应用清单不等于 ROM 扫描器；不能把 PortMaster 目录数量当成已可玩的游戏数量。

## 不重新设计的基础约定

- 使用 Qt 6 Quick/QML 与小型 C++ 状态/设备适配器；沿用现有启动、网络、音频和输入服务。
  产品名是 Jume Launcher，内部 `r46h-shell` 名称保留兼容；版本与项目地址在 About 展示。
- 1024×768、4:3 逻辑画布；只缩放文字，不能通过缩放整页实现大字体。
  颜色、间距、字号、焦点和动效复用 [controls](../mainline/gaming-shell/controls/README.md)，不用页面私有样式重造控件。
- 分类列表移动焦点时不加载详情；确认后异步进入，返回时保存并卸载详情，保持原选中项。
  输入立即响应，不为动画防抖；减少动态效果关闭空间运动。USB 工具保留已选定的单级列表。
- 收藏使用稳定 ID；设置原子保存，失败保留草稿并阻止误退出，损坏的旧文件不能被覆盖。
  无效功能显示不可用；板载蓝牙已确认不存在，不恢复占位入口。
- 以实际交互的 60 Hz 为目标，优先缓存、惰性加载、事件驱动和轻量透明度/位移动画。
  HUD 的提交率不等于 LCD FPS；测量前不虚构性能预算，不增加实时全屏模糊。

## Display and input decision

产品路径采用 [Weston handheld shell 与 input router](../mainline/gaming-wayland/HANDHELD.md)。
EGLFS 是单应用预览/专用直接显示路径；不能通过再开一个 EGLFS 窗口实现全局浮层，也不能直接复用 KMS 启动配置到 Wayland。
移植串流显示路径必须重新验证硬件帧导入、颜色、帧间隔和音画同步，保留既有回退。

窗口焦点不阻止游戏直接读取手柄；全局面板必须经过 broker 分配输入，并在切换、退出、故障时发送释放/中立状态。
游戏内快捷面板使用 L3+R3；桌面预览用 Select，串流退出用 L1+R1。任务组合键以
[Applications](../mainline/gaming-shell/APPLICATIONS.md#lifecycle-and-limits) 为准，不把旧 ES-DE 快捷键直接搬到共享会话。

## 接手步骤

1. 先读 [AGENTS](../AGENTS.md)、[文档索引](README.md)、[Context](PROJECT-CONTEXT.md) 和本页；执行 `git status --short --branch`，核对已有改动。
2. 以 Context 的第一项为当前任务；读该行负责文档、源码、最近证据和 [测试索引](../mainline/tests/README.md)。不要把路线图全部当成本轮任务。
3. 默认/回退工作从 [r9 overlay](../mainline/gaming-wayland/PRODUCT.md#optional-r9-es-de-fallback-overlay) 继续，复用封存的 r9；无需重建 Qt 或重写 TF 卡。
   没有设备时可审查补丁、运行主机测试、检查部署与撤销步骤；真实 systemd/冷启动/回退结果保持待验收。
4. 设备接入后按 [Development](DEVELOPMENT.md) 重新识别卡、串口、地址和版本，再执行 runbook 的有界验证。
   既有授权无需重复确认；仍需设备实际接入及对应的人眼、音频、按键观察，不能把“先准备”当作“已部署”。
5. 只改当前需求覆盖的代码/测试/负责文档，运行最小检查；记录证据层级、清理状态、最终电源状态和下一个未通过项。
   主机结果不推进实机 checkpoint；更新 Context 和负责 runbook，只有实际观察后才更新 ledger。

文档检查：`PYTHONDONTWRITEBYTECODE=1 python3 -B mainline/tests/test-project-docs.py`，然后 `git diff --check`。
回退代码检查分别是 `mainline/tests/test-jume-fallback.py`、`mainline/tests/test-jume-product.py`；同样禁用 Python 字节码。
UI 构建、Qt 测试及目标证据使用 [Shell runbook](../mainline/gaming-shell/README.md#checks-and-evidence)，不重复抄写构建命令。

## ES-DE removal gate

默认启动交付只处理 Jume 可进入、异常能退回和可撤销配置；完整替换还需 ROM 入口覆盖、真实存读档、
反复启动/退出、持续运行、升级/回滚及独立恢复，并分别验收 LCD、音频和实体操作。
未覆盖的系统入口继续保留。两小时运行、GUI 关机、清理中断等的具体未通过项以 [PRODUCT](../mainline/gaming-wayland/PRODUCT.md) 为准。
当前回退补丁不检测“进程仍在但界面卡死”；不要把异常退出处理称为卡死 watchdog。

串流暂停、Stardew 共享显示停滞、GPU-min/SGSR 已失败路径等“不重跑”边界只维护在
[Context 的下一步](PROJECT-CONTEXT.md#immediate-next-work)。完整库、浏览器安全基线、zram 与硬件阻塞分别推进，不以一项的通过替另一项验收。
