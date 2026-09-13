# R46H Linux 6.12 board sources

This directory owns the reviewable R46H DTS/board sources. Read:

- [project-level board rationale](../../../docs/R46H-BOARD.md) for stable
  assumptions, design choices and unresolved hardware risks;
- [EXPERIMENT-STATUS.md](EXPERIMENT-STATUS.md) for accepted physical evidence,
  failures and “do not repeat” boundaries;
- [Project Context](../../../docs/PROJECT-CONTEXT.md) for the current baseline
  and immediate next gate.

## Source ownership

- `rk3326-r46h.dts`: current reviewable board description produced by the
  ordered mainline patch series.
- `panel-r46h.c`: provisional board-specific panel implementation.
- `EXPERIMENT-STATUS.md`: authoritative physical experiment ledger.

The kernel source base and ordered patch identity are pinned by
`mainline/manifest.env`, `mainline/config/r46h.fragment` and
`mainline/patches/`. Change those inputs rather than editing generated kernel
trees.

## Rules

- Keep board changes isolated to one measured hardware hypothesis.
- Preserve the exact R46H compatible boundary for provisional quirks.
- Pair a source change with its focused static test and feature runbook.
- A host artifact is not a boot result. Update the ledger only after the exact
  candidate is physically observed and cleanup/final state pass.
- Do not revive the retired v0.2–v0.16 chronology from this README. Durable
  conclusions are in the board notes; exact history remains in Git.
