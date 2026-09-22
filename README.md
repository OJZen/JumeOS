# JumeOS

JumeOS is an experimental Linux handheld system for the R46H (RK3326). It
combines a mainline Linux graphics stack with a small, controller-first gaming
environment. The project is under active development and does not provide a
stable image or upgrade path yet.

## What works today

- Linux 6.12, Debian 13, Mesa/Panfrost graphics, ALSA audio, and unified gamepad input.
- ES-DE with RetroArch/Ozone as the current gaming frontend and fallback.
- Jume Launcher, an experimental Qt Quick home screen with battery, charging, Wi-Fi signal,
  temperature, frequency, and basic settings status.
- Neo Geo, a PortMaster catalog, isolated local saves, and source-built GTA III
  and Vice City reaching their target frontends.
- Bounded serial and SSH diagnostics, remote input, screenshots, and shared
  Wayland display experiments.

## Still in development

Jume Browser, Files/Text, Wi-Fi Transfer and the USB-keyboard terminal are experimental apps;
Target smoke checks pass for Files/Text/Transfer; physical UX acceptance remains open.

Moonlight streaming on the R46H, Stardew Valley, USB gamepad mode,
suspend/resume, attended GTA gameplay, and a supported installation image are
not complete.

## Repository

Active source lives in [`mainline/`](mainline/). Contributors should start with
the [project context](docs/PROJECT-CONTEXT.md) and the
[R46H evidence ledger](mainline/board/r46h/EXPERIMENT-STATUS.md). Generated
images, device captures, and private test material are intentionally excluded
from Git.

## 中文简介

JumeOS 是面向 R46H 的实验性 Linux 掌机系统，目前已有主线内核、Debian、
Panfrost、ES-DE/RetroArch 和实验性的 Jume Launcher。项目仍在开发中，暂不提供稳定
镜像或升级承诺。

Licensed under the [MIT License](LICENSE).
