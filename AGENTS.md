# Repository instructions

These instructions apply to JumeOS. Active R46H work belongs in `mainline/`.

## Start here

1. Read [`docs/README.md`](docs/README.md), then
   [`docs/PROJECT-CONTEXT.md`](docs/PROJECT-CONTEXT.md).
2. Read the [R46H ledger](mainline/board/r46h/EXPERIMENT-STATUS.md) before
   planning hardware work. It owns physical evidence and limitations.
3. Follow [Development](docs/DEVELOPMENT.md), [Testing](docs/TESTING.md) and the
   smallest relevant feature runbook. Do not infer current state from Git
   history or old logs.

Keep changing baselines and the next gate in Project Context, not this file.

## Development loop

1. Run `git status --short --branch`; preserve unrelated user changes and stage
   only intended paths.
2. Identify the owning code, focused test and canonical document. Reuse existing
   tools and make the smallest direct change that tests the current hypothesis.
3. Run targeted tests and syntax checks with `PYTHONDONTWRITEBYTECODE=1`, then
   run `git diff --check`. Provenance-bound builders require clean committed
   inputs.
4. Update the owning documentation in the same change; replace stale prose and
   link instead of copying status, hashes or procedures. Keep project details in
   `docs/` and executable contracts beside their code.
5. Distinguish host artifact, media write/readback and physical R46H proof.
   Update physical results only after the corresponding observation; automated
   frames/PCM do not prove LCD motion, audible output, controls or saves.
6. Remove task-created staging, mounts, servers and superseded disposable output
   after its replacement is verified. Keep named evidence and receipts.

## Workspace and hardware safety

- Put large builds, caches and temporary files on the external workspace,
  normally `mainline/out/.cache/` or `mainline/.cache/`. Never delete unfamiliar
  `.tmp-r46h-*` trees or receipts without inventorying them and asking.
- Treat `/dev/diskN`, serial paths, IPs and attachment IDs as dynamic. Rediscover
  identity and verify the fixed device, geometry and profile every session.
- The user grants standing authority for in-scope R46H device and identified
  R46H-media operations. Verify identity and exact scope, but do not ask again
  for target writes, service control, reboot or poweroff. Ask before accessing
  host-sensitive files/credentials or affecting unrelated host data.
- Never use the Codex bottom/in-app terminal for R46H work. Use an agent-only
  background PTY, or real macOS Terminal when operator input is required. For
  cold power-on, listen at 1500000 before power, then switch to 115200 only after
  `I/TC: OP-TEE version`. Warm reboot may start at 115200; check ground/TX/RX
  before diagnosing silence, and never use `saveenv` in one-shot tests.
- End unattended hardware work with health checks, `sync`, controlled poweroff
  and serial confirmation. Never put credentials/private keys in Git or captured
  logs, and keep SSH host-key checking enabled.
- R46H Wi-Fi credentials live only in ignored `mainline/out/private/r46h-wifi.json`.
  Read them without echoing values; never include that file in Git or evidence.
