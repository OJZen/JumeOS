# Built-in stick calibration

Open **设置 → 控制器 → 摇杆校准** on the R46H shared desktop:

1. Release both sticks; after a stable center sample, press A.
2. Push both sticks fully up/down/left/right, then circle their edges twice.
3. Press A to preview the result. Check all directions reach ±1.00, release
   both sticks, then press A to save. B cancels; X restarts collection.

**恢复默认校准** has a separate confirmation. Cancel, incomplete travel,
disconnect and write errors preserve the previous saved profile. Home and the
quick panel cancel an unfinished collection. The existing controller tester
shows the corrected readings after saving.

## Scope and storage

The four built-in axes are corrected in the shared input router, so Jume and
its launched games/streams receive the same correction. External USB pads,
the base Combined Gamepad bridge and ES-DE fallback input are unchanged.
This does not add a deadzone or change button bindings.

`stickcalibration.cpp` stores `stick-calibration.json` in Jume's existing private
state directory (installed: `/home/ark/.local/share/r46h-preview/`). Version 1
contains `enabled` and four `[minimum, center, maximum]` triples in normalized
−32767…32767 units. Each half is scaled independently and clamped to full range;
the center must be within ±8192 and each half must span at least 8192, limiting
gain to 4×. A 600 ms center window rejects movement before recording its mean.

The file is size/type/range checked, written atomically with owner-only access,
and symlinks are refused. A corrupt file is retained until the user explicitly
saves a new calibration or confirms reset. Missing/disabled data keeps the
original input path. Saving does not touch saves, ROMs or streaming profiles.

## Paired input contract

`stick-calibration.h` owns the math; `StickCalibrationView.qml` owns the wizard.
The existing 80-byte router packet gains a capability flag, raw-axis feedback
and calibration request/acknowledgement. Recalibration always observes original
values, including movement beyond a previously calibrated saturation point.
The router accepts updates only in UI ownership, validates all four axes,
releases controls and waits for neutral. Logical remote injections are already
normalized and are not corrected twice. Desktop readiness waits for the saved
profile acknowledgement at startup.

Ship `r46h-shell` and `input-router` together in a newly sealed release. Follow
[inactive version selection](../gaming-wayland/PRODUCT.md#inactive-version-selection)
and revalidate the fallback/splash pins; never edit the installed release in place.
Retain the concurrent Select short-tap fix when combining these changes.

## Focused checks and evidence

- `calibration-check`: asymmetric endpoints, monotonic/clamped mapping,
  incomplete/unstable collection, save/load/reset, cancellation/disconnection,
  write failure/corrupt-file preservation and the page at 130% text size.
- `shell-check stickCalibrationSettingsFlow`: settings navigation, cancellation
  and global Home/quick-panel handling.
- `check-input-router.sh`: actual Linux uinput UI/game routing, original-value
  feedback, invalid/game-owner refusal, reset and existing Select/ownership tests.
- `test-stick-calibration-desktop.py`: container-only Qt/Weston/synthetic-pad
  collection, live application and saved-profile restoration after session restart.

Host evidence is retained under
`mainline/out/.cache/jume-stick-calibration-20261031.dMCp5H/`.
Host/synthetic passes do not establish physical full travel, center feel,
LCD readability or game controls. The [installed-session record](../gaming-wayland/PRODUCT.md)
owns device acceptance; the operator must move the real sticks to calibrate them.
