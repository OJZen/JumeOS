# Development guide

## Engineering style

Use the fastest path that remains clear, safe and testable:

- Keep changes small, direct and reviewable.
- Prefer existing scripts, payload formats and runbooks.
- Add an abstraction only when at least one current requirement needs it.
- Test one hypothesis at a time; do not bundle unrelated hardware variables.
- Preserve unrelated worktree changes and stage only intended paths.

For Qt tools, follow the [shared control defaults and layout contract](../mainline/gaming-shell/controls/README.md). Reuse the controls and semantic theme tokens before adding page-local styling.

KISS here means fewer moving parts and explicit state, not skipping validation
or recovery boundaries.

## Normal loop

1. Run `git status --short --branch`.
2. Read [Project Context](PROJECT-CONTEXT.md), the relevant ledger row and the
   smallest owning runbook.
3. Identify one owner each for code, test and documentation.
4. Make the narrowest change that can confirm or reject the hypothesis.
5. Run focused checks from [Testing](TESTING.md), then `git diff --check`.
6. For provenance-bound builders, commit clean inputs before producing the
   artifact; do not claim reproducibility from a dirty source tree.
7. Deploy only the required partition/payload and keep a rollback path.
8. Record exact evidence and limitations; update the ledger only after physical
   observation.
9. Remove task-created staging, mounts, servers and superseded disposable
   artifacts after the replacement is verified.

## Documentation practice

Documentation is part of implementation. Update it in the same change whenever
behavior, commands, interfaces, versions, evidence or safety boundaries change.

Use the [document ownership map](README.md#document-ownership). `AGENTS.md`
contains stable repository instructions and reading links, not a second current
checkpoint; keep it under 70 lines. Project Context owns the current baseline
and plan; the ledger owns physical results. Feature runbooks retain exact
commands, hashes, recovery and result contracts.

Before adding prose, ask whether an existing owner should be replaced instead.
Do not copy long command sequences, hashes or result tables into indexes.
Remove obsolete instructions once the replacement is accepted; Git preserves
the old narrative. If a document grows hard to scan, keep its current contract
and durable lessons, then retire chronology.

Versioned rootfs builders still import predecessors and pin their artifacts.
Their `PRODUCT.md` files and source manifests may be build inputs: inspect the
builder before deleting or rewriting them as redundant. Preserve published
hashes as evidence of the named source commit; documentation edits do not
revalidate or replace an existing image. Retire old deployment recommendations
by linking to Project Context instead of asking for each intermediate version
to be written and booted.

## Workspace and cleanup

- Put large builds and caches on the external volume, normally
  `mainline/out/.cache/` or `mainline/.cache/`.
- Set `PYTHONDONTWRITEBYTECODE=1` for Python checks.
- Use task-specific temporary directories. Do not repurpose `HOME`,
  `CODEX_HOME` or another broad system variable.
- Retain evidence explicitly named by a runbook/result record. Delete
  superseded disposable output only after the replacement is verified.
- Do not remove unfamiliar `.tmp-r46h-*` directories, receipts or ignored
  evidence trees merely because Git does not track them. Inventory first and
  ask if ownership is unclear.
- Unmount and stop task-created services/agents at the end of the operation.

## Deployment choices

The user currently grants standing authority for in-scope R46H target and
identified R46H-media operations. Do not request repeated approval for target
file writes, service control, reboot, poweroff or an exact-profile guarded media
plan. This authority does not extend to unrelated host data. Access to local
sensitive files or credentials still needs explicit permission; keep approved
secret values out of output/logs and remove temporary copies after use.

Choose the smallest deployment surface:

1. Config, service or userspace payload: SSH/Wi-Fi to p2.
2. Kernel/DTB candidate: inactive versioned p1 files, then guarded promotion.
3. p3 content: a p3-only plan with fixed image size and partition geometry.
4. Full-card write: only for provisioning or a release gate that genuinely
   requires it.

Never turn a p2 change into a full TF-card rewrite for convenience. macOS
file-level copying to exFAT is not an accepted substitute for the Linux
container image path because it previously produced unreliable metadata and
mount behavior.

## Privileged media operations

Device names are dynamic. At every attachment:

1. Rediscover the external physical device.
2. Match exact whole-device size, partition offsets/sizes, UUID/PARTUUID and
   fixed profile.
3. Freeze the exact source artifact and operation scope.
4. Confirm that the exact target/scope is covered by standing authorization;
   otherwise obtain authorization before writing.
5. Hold one visible persistent privileged session (Card Agent or a dedicated
   `sudo` terminal) through the operation.
6. Write only the authorized region, `sync`, perform the promised readback
   level and eject.

Do not repeatedly invoke macOS SecurityAgent for raw-device commands. That path
has failed with `Operation not permitted` even when it could inspect the
external image. A visible persistent session avoids repeated prompts and keeps
device identity/progress observable.

If the user explicitly skips checksums, still verify identity, geometry, exact
byte count, `sync` and eject, then report content equality as unverified. A
successful write never closes the physical boot/use gate.

## Serial and physical sessions

- Cold power-on: listen at 1,500,000 8N1 with no flow control before power.
  Switch to 115,200 only after the visible `I/TC: OP-TEE version` marker.
- Warm reboot may begin at U-Boot/115,200.
- Never use the Codex bottom/in-app terminal for R46H work. Use a background PTY
  for agent-only serial capture/control and SSH; do not open or activate
  Terminal.app when no operator input is required.
- The unchanged engineering image's documented serial fixture is `ark`/`ark`
  ([rootfs contract](../mainline/rootfs-debian13/README.md)); it may be used in
  the background and is not a private user credential. A replacement password
  or private key remains sensitive and must not enter logs or commands.
- If the operator must type a login or password, stop the background serial
  reader first and launch the interactive command in the real macOS
  Terminal.app. A Codex background PTY or in-app terminal tab cannot be handed
  to the operator. Use the previously verified launch form below, replacing
  `REPO`, `DEVICE`, `BAUD`, and `LOG`; for an already booted system use 115200
  and omit the two switch options.

  ```sh
  osascript \
    -e 'tell application "Terminal" to do script "cd REPO && PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -B mainline/scripts/r46h-serial-console-macos.py DEVICE BAUD LOG --switch-trigger '\''I/TC: OP-TEE version'\'' --switch-baud 115200 --interactive"' \
    -e 'tell application "Terminal" to activate'
  ```
  Confirm the Python process owns `DEVICE`. If a prior reader consumed the
  getty prompt, send one empty `do script` line to that same Terminal tab after
  it prints `ready`; this forwards one return and makes `login:` visible.
- Check common ground and TX/RX direction before interpreting an empty log.
- Never use `saveenv` in a one-shot boot experiment.
- Batch attended observations so the operator handles the device once.
- Prefer SSH, systemd status and receipts after Linux is healthy; use serial for
  boot-chain, power, early-mount and recovery evidence.
- Finish unattended work with health checks, `sync`, controlled poweroff and
  serial confirmation.

Never commit credentials or private keys, print secrets into captured logs, or
disable SSH host-key checking. Keep target commands bounded and reversible.
