# R46H full FBNeo core v0.1

Status: **HOST CORE + CONTENT + P2 IMAGE PASS / MEDIA + PHYSICAL OPEN**

This is the smallest next content-runtime step after the accepted Neo-Geo
subset. It builds the full FBNeo libretro core from the same pinned upstream
source and builder, without changing the accepted frontend, p2 or p3.

`source-lock.json` owns the source, flags and exact stripped AArch64 artifact.
The existing Ozone/FBNeo builder accepts this alternate lock, so there is no
second build implementation:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -B \
  mainline/gaming-ozone-fbneo/build-core.py build \
  --lock mainline/gaming-fbneo-full/source-lock.json \
  --output mainline/out/r46h-gaming-fbneo-full-v0.1/fbneo_libretro.so

PYTHONDONTWRITEBYTECODE=1 python3 -B \
  mainline/gaming-ozone-fbneo/build-core.py validate \
  --lock mainline/gaming-fbneo-full/source-lock.json \
  --output mainline/out/r46h-gaming-fbneo-full-v0.1/fbneo_libretro.so
```

On 2026-09-04 clean committed builder
`5beb82d58fbf7756df62cc5cb1760a48a0a41d3b` produced two byte-identical
79,683,320-byte outputs with SHA-256
`d63bc891a85599949b99748aa5dcd79aed86c29dc859739a9bfe4e1361c02956`;
both passed the independent artifact validator.

## Content boundary

Exact Debian RetroArch 1.20 loaded these retained original-card files with null
video/audio and reached `Driver successfully started` without a libretro error:

- `arcade/1941.zip` — `8e562cacceea51597e1e05eb5af4abdd75c880ce1b171b0f61180b673d2f52cc`
- `arcade/1944.zip` — `9186f400aa9cfcdf2720c16bf9801da0e782c5ca6e4bfcdac70c3dc30bbe508d`
- Nine further arcade samples spanning Capcom, Cave, Konami and Taito also
  loaded: `avsp`, `dino`, `ddtod`, `sf2`, `mvsc`, `ddonpach`, `tmnt`,
  `bublbobl` and `xmen`.
- `cps3/sfiii3.zip` — `8b9a0002654f289e37f58c3e26bb4111fde105e75a0834c80fa2e660f4b116d8`
- `cps3/redearth.zip` — `26beb691702dc9b31303a9bc021dfe4421a064b4a15bf7a421c37459717856f4`

The exact full-directory startup audit in `content-audit.json` passed CPS1
48/48, CPS2 57/62 and CPS3 9/12. All eight failures reported missing required
ROM members. The first integration adds the sampled `arcade` directory; the
v0.10 successor also admits the fully passing CPS1 directory. CPS2/CPS3 remain
hidden as whole systems until their content is repaired or filtered.

`generate-filtered-gamelists.py` takes the filter path without touching ROMs.
It rechecks each complete directory against the audit hash, preserves original
metadata and marks only the eight exact failures hidden for the p2 v0.12 host
candidate.

No ROM is copied into source or generated output. Reproducible p2 v0.10 exposes
the tested `arcade` and CPS1 directories. Media write plus target launch, LCD,
audio, controls, pacing and broader compatibility remain open.
