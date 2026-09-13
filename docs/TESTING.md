# Testing and evidence

Tests answer different questions. Always name the level that passed and the
next level that remains open.

## Evidence levels

| Level | What it can prove | What it cannot prove |
| --- | --- | --- |
| Static/host | Source contracts, syntax, deterministic build structure, artifact hashes | Bytes on a TF card or any R46H behavior |
| Media | Exact device/geometry, bounded write, optional readback/content equality | Boot, drivers, frontend or game behavior |
| Physical R46H | Observed behavior on the exact booted system and test path | Untested hardware, content, duration or environmental conditions |

Within media proof, keep “write completed” and “readback matched” separate.
Within physical proof, keep machine-observed state and operator-observed
audio/display/control behavior separate.

## Focused host checks

Run the smallest owning check, usually by direct path:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 mainline/tests/test-project-docs.py
PYTHONDONTWRITEBYTECODE=1 python3 mainline/tests/test-r46h-charge-term-policy.py
bash -n mainline/scripts/stage-test-to-sd.sh
git diff --check
```

The test index at [mainline/tests/README.md](../mainline/tests/README.md)
documents fixture boundaries. Many files are standalone `unittest` programs
with hyphens in their names, so direct execution is clearer than assuming one
monolithic discovery command.

For a change:

- Run the owning regression/static-contract test.
- Run syntax checks for every changed shell/Python/Swift/Rust entry point using
  its established build/test driver.
- Run adjacent tests only where the interface or shared input changed.
- Run `git diff --check` after generated or documentation edits.
- Do not run expensive builders merely to claim broader coverage. If a builder
  is provenance-bound, use clean committed input.

## Deterministic build proof

A reproducible builder should pin source identity, declared inputs, output size
and cryptographic hashes, and fail closed on missing inputs. Two isolated builds
can prove deterministic host artifacts. They still do not prove that the media
was written or that the board booted.

Generated packages and large fixtures live under ignored `mainline/out/`.
Only consume a fixture when its owning test pins its closure. Missing local
fixtures should produce a clear skipped/open boundary, not an invented pass.

## Media proof

Before any destructive write, capture:

- rediscovered whole-device identity and attachment;
- fixed profile, total size and partition geometry;
- exact source artifact identity and intended byte range;
- authorization matching the exact target and scope.

Afterward, report exact bytes written, `sync`, promised verification level and
eject. Quick/Balanced/Full verification are not interchangeable. If readback or
checksums are skipped, state content equality as unverified and keep the
physical gate open.

Do not use a historical `/dev/diskN` name or infer unchanged p1/p2 bytes from
an operation that merely avoided opening them for write.

## Physical experiment design

Before power:

1. Read the current ledger row and owning runbook.
2. Freeze exact kernel/rootfs/payload identity and expected markers.
3. Decide whether serial is required and open it before a cold power-on.
4. Define one bounded operator action set, machine pass markers, abort
   conditions, cleanup and final power state.

During the run, change one variable and preserve raw machine evidence. Do not
repeat accepted audio, input, charging or media stress tests without a relevant
implementation change. Batch remaining attended observations when that reduces
operator handling without obscuring which step produced each result.

After the run:

- compare pre/post health: kernel log, filesystem state, failed units and
  unexpected mounts/processes;
- restore temporary mixer, service, mount and staging state;
- `sync` and perform controlled poweroff when the runbook requires it;
- record operator observations separately from machine markers;
- update the ledger only when the intended physical gate actually passed.

## Result language

Use exact labels such as:

- `PASS (host only)`
- `WRITE PASS / READBACK SKIPPED`
- `MACHINE PASS / OPERATOR OBSERVATION OPEN`
- `PHYSICAL PASS FOR EXACT PATH / BROADER COVERAGE OPEN`

Every result should include exact tested identity, accepted observation,
cleanup/final state and remaining limitation. Avoid “works”, “done” or
“verified” without saying what evidence supports the claim.

## Documentation regression

`mainline/tests/test-project-docs.py` enforces the short onboarding map,
selected line budgets, the ledger's source readability, synchronized Context/
ledger checkpoint dates and key identities, frozen-history banners, rootfs and
bring-up indexing and local links across source Markdown. It is structural: content
accuracy still requires reviewing Project Context and the ledger whenever
project state changes. AGENTS.md links to those owners instead of repeating a
checkpoint. Known feature-test failures belong in the
[test index](../mainline/tests/README.md), not an invented whole-suite pass.
