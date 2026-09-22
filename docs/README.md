# Project documentation

This directory contains the current design, development rules, and handoff
state. Feature-specific commands remain beside the code they operate on.

## Reading order

1. [Project Context](PROJECT-CONTEXT.md) — current baseline and next work.
2. [R46H evidence ledger](../mainline/board/r46h/EXPERIMENT-STATUS.md) — physical
   results and remaining limitations.
3. [Architecture](ARCHITECTURE.md) — system structure and technology choices.
4. [R46H board notes](R46H-BOARD.md) — stable board-level rationale.
5. [Development](DEVELOPMENT.md) and [Testing](TESTING.md) — workflow, safety,
   and evidence rules.

The root [README](../README.md) is the public project introduction.
[`mainline/README.md`](../mainline/README.md) maps the active source tree.

## Document ownership

| Question | Owner |
| --- | --- |
| Current state and next action | [Project Context](PROJECT-CONTEXT.md) |
| Planned features and acceptance gates | [Product Roadmap](PRODUCT-ROADMAP.md) |
| Physical R46H results | [Evidence ledger](../mainline/board/r46h/EXPERIMENT-STATUS.md) |
| System structure | [Architecture](ARCHITECTURE.md) |
| Board-source decisions | [R46H board notes](R46H-BOARD.md) |
| Development and media safety | [Development](DEVELOPMENT.md) |
| Test scope and evidence language | [Testing](TESTING.md) |
| EASYROMS migration | [P3 Content Migration](P3-CONTENT-MIGRATION.md) |
| Streaming | [Game Streaming](GAME-STREAMING.md) |
| Qt desktop | [Device Shell](DEVICE-SHELL.md) |
| Files, previews, editor and application data | [Jume Files/Text](../mainline/gaming-files/README.md), [File layout](FILESYSTEM-LAYOUT.md) |
| Wi-Fi file transfer | [Jume Transfer](../mainline/gaming-files/TRANSFER.md) |
| Performance and power | [Performance and Power](PERFORMANCE-POWER.md) |
| Remote UI control | [Remote Control](REMOTE-CONTROL.md) |

Exact commands, hashes, rollback steps, and feature receipts belong in the
nearest `mainline/**/README.md` or runbook rather than this index.
