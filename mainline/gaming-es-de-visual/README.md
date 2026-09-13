# R46H ES-DE visual profile v0.1

This p2-only overlay replaces the diagnostic text theme with the bundled
`linear-es-de` theme's original console art and game-list variants. It selects
the theme's native OLED palette, bounds both carousels and enables slide
transitions. No new asset, daemon, listener, emulator or p3 write is involved.

This is a current-card migration overlay for the earlier text-profile install.
The current `gaming-es-de` payload already includes the final theme/settings;
do not apply this overlay after a fresh base install.

Build from the repository root:

```sh
mainline/gaming-es-de-visual/build-payload.sh
```

Stage the five payload files at `/run/r46h-gaming-es-de-visual-v0.1` as
root-owned mode 0600 inside a root-owned mode 0700 directory, then run
`install.sh --installer-sha256 HEX` as root. The installer requires the exact
accepted ES-DE text theme, saves rollback state, restarts only the frontend and
verifies one ES-DE process, read-only `/roms` and zero target errors.

The unmodified theme measured 15.0 FPS; the bounded three-item original-art
profile settles at 60 FPS. Theme A/B measured 21.3 FPS for the tiled full-screen
fill, 21.4 FPS when stretched once and 29.9 FPS at quarter-screen area. AFBC and
VSync changes had no effect, and ES-DE emits one quad rather than expanding tiles.

A corrected one-submit-per-draw GLES probe then measured the exact premultiplied
`core.glsl` image path at 21.7 ms full-screen and 6.2 ms quarter-screen. The
equivalent minimal shader takes 3.3 ms full-screen. A safe early-return branch
reduced the isolated core draw to 6.2 ms but reached only 30 FPS in live ES-DE;
the no-background view measured 57.9 FPS with VSync off and 60 FPS normally.
The initial invalid 180-draw batch formed a roughly 0.5-second GPU job and caused
12 recoverable scheduler timeouts. The corrected per-frame probe and later UI
runs produced no new timeout. This is probe-induced evidence, not a product load.

The accepted fix remains omission of the redundant solid-black image so the
existing framebuffer clear supplies the background. Panfrost's minimal path is
healthy; do not replace the kernel or driver for this result. Upstream `master`
`e98e767e` still carries a byte-identical `core.glsl`, so an ES-DE upgrade alone
is not a demonstrated fix. Large CJK lists remain content-bound at roughly
20--42 FPS, and removing useful art did not fix that cost. The guarded install,
rollback/reinstall and settings restoration pass. Run
`sudo /usr/local/sbin/r46h-es-de-visual-rollback` before the base ES-DE rollback.
