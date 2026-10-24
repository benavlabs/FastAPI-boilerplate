# bp — the FastAPI-boilerplate CLI

`bp` is the developer/operator tool that ships alongside the boilerplate. It generates deployment artifacts, helps prepare the runtime environment, and serves as the host for plugin commands and feature generators.

It is **not** part of the deployable backend. The backend image stays lean — `bp` lives in its own workspace package (`cli/`) and is only present in development environments and on machines where you've installed it as a tool.

## What's in this section

- **[Commands](commands.md)** — complete reference for the in-tree `deploy` and `env` sub-apps
- **[Plugins](plugins.md)** — extension points (`bp.commands` and `bp.features`) and authoring guide

## Repository Layout

```text
fastapi-boilerplate/
├── pyproject.toml          # workspace root (uv workspace metadata)
├── backend/                # deployable application — never ships bp
│   └── src/...
├── cli/                    # the bp package
│   ├── pyproject.toml      # typer + jinja2 + workspace dep on backend
│   └── src/cli/
│       ├── app.py          # Typer root + plugin discovery
│       ├── commands/       # in-tree command sub-apps
│       ├── features/       # feature framework + in-tree features
│       └── plugins.py      # entry-point loaders
└── docs/
```

The two-package split is deliberate: `cli/` depends on `backend/` (for things like `bp env validate`), but `backend/` never depends on `cli/`. Production images ship `backend/` only.

## Install

### In-repo (most common)

```bash
git clone https://github.com/benavlabs/fastapi-boilerplate
cd fastapi-boilerplate
uv sync --all-packages --all-extras   # one venv with the backend, the cli and the dev tools
uv run --no-sync bp --help         # works from anywhere in the repo
```

The workspace shares a single `.venv/` at the repo root. You can run `uv run --no-sync bp` from any subdirectory — uv walks up to find the workspace root.

### Machine-wide (optional)

If you want `bp` on `PATH` outside the repo:

```bash
uv tool install --editable ./cli
bp --help
```

`--editable` means edits to `cli/src/cli/` show up immediately without reinstall. Re-run `uv tool install --editable ./cli` only when `cli/pyproject.toml` changes (deps, entry points). To uninstall:

```bash
uv tool uninstall fastapi-boilerplate-cli
```

## Quick Tour

### Generate a Compose File

```bash
uv run --no-sync bp deploy generate local                  # hot-reload dev stack
uv run --no-sync bp deploy generate prod --workers 8       # production stack
uv run --no-sync bp deploy generate nginx                  # production behind nginx
```

Each command writes `docker-compose.yml` (and `nginx/default.conf` for the nginx mode) to the repo root by default. Use `--output-dir` to target somewhere else.

### Generate a Secret

```bash
uv run --no-sync bp env gen-secret
# → 64-char hex suitable for SECRET_KEY
```

### Audit Production Settings

```bash
uv run --no-sync bp env validate
# Forces the production security validator regardless of ENVIRONMENT.
# Exits 1 if any critical issues are found.
```

## Command Tree

```text
bp
├── deploy
│   └── generate <mode> [options]    # mode ∈ {local, prod, nginx}
└── env
    ├── gen-secret [--bytes N]
    └── validate
```

Plugin sub-apps mount as siblings of `deploy` and `env`. See [Plugins](plugins.md) for details.

## Design Principles

- **No surprises in production.** `bp` never runs against production at runtime — it's a developer/operator tool. Production images don't even include the `cli` package.
- **Two extension points, kept separate.** Command plugins (Typer sub-apps) and feature plugins (code generators with manifests) have different lifecycles and shouldn't share machinery.
- **Templates as data.** Built-in features render Jinja templates. Plugin features do the same. The installer is the only thing that needs to know how to execute the plan.
- **Idempotent and dry-runnable.** Every operation that mutates the user's repo prompts before overwriting and supports `--dry-run`.

## Next Steps

- **[Commands](commands.md)** — full reference for the shipped commands
- **[Plugins](plugins.md)** — write your own commands or features
