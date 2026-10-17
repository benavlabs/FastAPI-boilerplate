# bp — FastAPI-boilerplate CLI

`bp` is the developer/operator command-line tool for projects built on the
FastAPI boilerplate. It generates deployment artifacts, helps prepare the
runtime environment, and serves as the host for plugin commands and feature
generators.

## Install

This package is part of the workspace. From the repo root:

```bash
uv sync --all-packages --all-extras   # bp is then available via `uv run bp`
uv run bp --help
```

To install `bp` machine-wide so it works outside this repo:

```bash
uv tool install --editable ./cli
bp --help
```

## What's here

```
cli/src/cli/
├── app.py                 root Typer app + plugin discovery
├── plugins.py             entry-point loaders for bp.commands and bp.features
├── commands/              in-tree command sub-apps
│   ├── deploy.py          bp deploy generate <mode>
│   └── env.py             bp env gen-secret / bp env validate
├── features/              feature framework (manifest, plan, installer)
│   └── _builtins/         in-tree features
│       └── deploy/        compose/Dockerfile templates for local/prod/nginx
└── lib/                   shared helpers (project discovery, prompts, render)
```

## Plugin extension points

Two kinds of plugins, kept deliberately separate:

- `bp.commands` entry-point group — third-party Typer sub-apps mounted under
  `bp <name>` (e.g. `bp aws deploy`).
- `bp.features` entry-point group — code generators with a manifest that
  `bp feature` can list, install, and remove.

See `cli/src/cli/plugins.py` for the discovery contracts.
