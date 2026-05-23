# Repository Hygiene

This repository contains both public source code and local robot life. A public
release needs care because logs, memory, captures, diaries, model weights, and
machine-local files can appear next to source.

## Should Usually Be Tracked

- Runtime source in `src/`.
- Curated YAML configuration in `config/`.
- Logos-facing reference context in `.system/`.
- Curated Chora configuration under `hypomnemata/chora/`.
- Human-facing docs in `README.md` and `docs/`.

## Should Usually Stay Untracked

- `state/` runtime memory and I/O history.
- `ipc/` camera captures and sidecars.
- `hypomnemata/legacy_Logos_diaries/` unless a file has been intentionally
  reviewed for publication.
- Python caches and generated artifacts.
- Local editor files such as `.vscode/`.
- Local assistant files such as `.codex` and `.claude/`.
- Model weights and other large binaries.
- `.env` files, credentials, private keys, and local secrets.

## Image Policy

Do not ignore every `*.png` or `*.jpg` globally. Public docs may eventually need
curated images. Ignore generated capture directories such as `ipc/`, while
allowing explicitly reviewed documentation images to be committed later.

## Before Publishing

Run a current-tree scan for secrets and personal files. Also consider a Git
history scan before making the repository public, because removing a file from
the current tree does not remove it from old commits.

This repository intentionally preserves some weirdness and personal texture.
The goal is not to sand it flat; the goal is to avoid accidentally publishing
credentials, private memory, large generated files, or machine-local clutter.
