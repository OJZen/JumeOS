# R46H private Mesa runtime

Status 2026-09-15: **MESA 26.2.2 GTA III/VC SAME-BOOT PERFORMANCE PASS / FORMAL PAYLOAD OPEN**.

This feature pins the Panfrost/softpipe Mesa 26.2.2 EGL, GBM and Gallium ABI
closure used only by the shared Wayland game session. It does not replace Debian
packages or the normal ES-DE graphics stack. `source-lock.json` owns the upstream
archive, build configuration and every runtime member; `runtime.py` refuses a
different archive or an overwrite during assembly.

The source was built in the pinned ARM64 SDK with the recorded Meson options and
external LLVM 19 development inputs. The normalized runtime is expected at
`mainline/out/.cache/r46h-mesa-26.2.2/r60/mesa-26.2.2-r46h-runtime.tar.gz`.
Validate it directly or let `gaming-wayland/build-handheld.sh` validate and add it:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -B mainline/gaming-mesa/runtime.py \
  validate-runtime mainline/out/.cache/r46h-mesa-26.2.2/r60/mesa-26.2.2-r46h-runtime.tar.gz
```

The tested 816/300 MHz same-boot intro windows improved from 11.00 to 14.36
submissions/s in GTA III and from 14.67 to 17.15/s in Vice City. Both candidate
runs exited 0 below 81 C without cooling-state throttling or a new Panfrost fault;
the original Mesa GTA III comparison added one `DATA_INVALID_FAULT`. These are
compositor submissions, not proof of LCD motion, audible output, gameplay or saves.
A preceding Gallium-only frontend trial segfaulted without a GPU fault, so it is
rejected; the complete private ABI closure is the smallest supported deployment.
