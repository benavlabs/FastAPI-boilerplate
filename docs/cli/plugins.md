# Plugins

`bp` has two extension points, kept deliberately separate. They have different lifecycles and shouldn't share machinery:

- **Command plugins** (`bp.commands`) — third-party Typer sub-apps mounted under the root, e.g. `bp aws deploy`. Pure CLI surface; the plugin doesn't touch the user's repo.
- **Feature plugins** (`bp.features`) — code generators with a manifest that `bp feature` can list, install, and remove. Plugins of this kind mutate the user's repo (write files, edit settings, run hooks).

Both are discovered via [Python entry points](https://packaging.python.org/en/latest/specifications/entry-points/), so a plugin is just a normal Python package on the user's machine.

## How Discovery Works

When `bp` starts, the root app:

1. Mounts in-tree command sub-apps (`deploy`, `env`)
2. Calls `discover_command_plugins()` (from `cli.plugins`) which walks `entry_points(group="bp.commands")` and mounts each healthy result
3. Builds the feature registry on demand: in-tree features merged with `discover_feature_plugins()` from `bp.features`

A broken plugin never breaks `bp`. Discovery wraps each load in `try/except`, surfaces a `RuntimeWarning`, and continues with the working subset.

```python
# cli/src/cli/plugins.py (abridged)
def _safe_load(ep: EntryPoint) -> object | None:
    try:
        return ep.load()
    except Exception as exc:
        warnings.warn(f"Failed to load plugin {ep.name!r}: {exc}", RuntimeWarning)
        return None
```

In-tree commands and features take precedence on name collisions — a plugin can't silently shadow a built-in.

## Command Plugins

Use a command plugin when you want to add new top-level verbs to `bp` without modifying the boilerplate. Examples: `bp fly deploy`, `bp pulumi up`, `bp lint custom-rules`.

### Authoring a Command Plugin

Create a Python package with a `typer.Typer` instance and register it under the `bp.commands` group.

#### 1. Package layout

```text
bp-deploy-fly/
├── pyproject.toml
└── src/
    └── bp_deploy_fly/
        ├── __init__.py
        └── cli.py
```

#### 2. `cli.py` — define the sub-app

```python
import typer

app = typer.Typer(
    name="fly",
    help="Deploy this app to Fly.io.",
    no_args_is_help=True,
)


@app.command("deploy")
def deploy(
    region: str = typer.Option("ord", help="Fly region to target."),
    yes: bool = typer.Option(False, "--yes", "-y"),
) -> None:
    """Build and deploy the current branch to Fly.io."""
    typer.echo(f"deploying to fly region={region}")
    # ... real work here ...
```

#### 3. `pyproject.toml` — declare the entry point

```toml
[project]
name = "bp-deploy-fly"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = ["typer>=0.12"]

[project.entry-points."bp.commands"]
fly = "bp_deploy_fly.cli:app"

[tool.setuptools.packages.find]
where = ["src"]
```

The entry-point key (`fly`) becomes the sub-command name. The value (`bp_deploy_fly.cli:app`) is the import path to your `Typer` instance.

#### 4. Install and use

```bash
uv pip install bp-deploy-fly
uv run bp --help
# ╭─ Commands ────────────────────────────────────────────────╮
# │ deploy  Generate deployment artifacts ...                 │
# │ env     Inspect and prepare the runtime environment.      │
# │ fly     Deploy this app to Fly.io.            ← new       │
# ╰───────────────────────────────────────────────────────────╯

uv run bp fly deploy --region ord --yes
```

### Best Practices for Command Plugins

- **Pick a unique name.** `bp` warns if you collide with a built-in (`deploy`, `env`, `feature`) and ignores you. Pick something specific (`fly`, `aws`, `pulumi`) rather than generic (`cloud`, `tools`).
- **Keep your sub-app self-contained.** Don't import from the host CLI's internals — use only the public Typer interface. The `cli.app` module is not a public API.
- **Honor the global UX patterns.** Support `--yes` for non-interactive runs and `--dry-run` where it makes sense. Match the style of the in-tree commands.
- **Don't block on broken external dependencies.** If your plugin needs `flyctl` or `kubectl`, check for it gracefully and surface a useful error — not a stack trace from `subprocess`.

## Feature Plugins

Use a feature plugin when you want to **mutate the user's repo** — drop in a new module, add OAuth providers, wire up a payments integration, write migrations. Features have a manifest, plan, and installer lifecycle so they can apply, list, and (eventually) revert cleanly.

!!! note "Feature plugins are designed for, but not yet wired to, `bp feature`"
    The feature framework (`Feature`, `FeatureManifest`, `FeaturePlan`, `FeatureInstaller`) is fully implemented and the registry already discovers plugin features. The user-facing `bp feature` sub-app is not yet shipped — features are reachable today only via in-tree commands like `bp deploy generate`. The contract below is stable; once `bp feature {list,add,remove,info}` lands, your plugins will work without changes.

### The Feature Contract

A feature is a class that subclasses `cli.features.base.Feature`:

```python
from cli.features.base import Feature, FeatureManifest, FeaturePlan, FileOp
from cli.lib.project import ProjectContext


class MyFeature(Feature):
    def manifest(self) -> FeatureManifest:
        return FeatureManifest(
            name="my-feature",
            version="1.0",
            summary="One-line description shown by `bp feature list`.",
        )

    def plan(self, params: dict, project: ProjectContext) -> FeaturePlan:
        return FeaturePlan(
            manifest=self.manifest(),
            templates_root=Path(__file__).parent / "templates",
            template_context={"project_name": project.repo_root.name, **params},
            files=(
                FileOp(template="my_module.py.j2",
                       target=project.backend_dir / "src/modules/my_feature/__init__.py"),
                # ... more files ...
            ),
        )
```

Two methods, both required:

- **`manifest()`** — static metadata. Called by registry / list operations without executing anything.
- **`plan(params, project)`** — given runtime parameters and a `ProjectContext`, return a concrete `FeaturePlan`.

### The Plan Schema

```python
@dataclass(frozen=True)
class FeaturePlan:
    manifest: FeatureManifest
    templates_root: Path | None
    template_context: dict[str, Any] = field(default_factory=dict)
    files: tuple[FileOp, ...] = ()
    codemods: tuple[Codemod, ...] = ()    # reserved for v2 — installer raises NotImplementedError
    hooks: tuple[Hook, ...] = ()          # reserved for v2 — installer raises NotImplementedError
```

The schema covers today's "render Jinja templates to disk" and tomorrow's "mutate code + run a migration". Defining `Codemod` and `Hook` types now means feature plugins can declare them without breaking the contract when the installer learns to execute them.

#### `FileOp`

```python
@dataclass(frozen=True)
class FileOp:
    template: str          # path relative to templates_root
    target: Path           # absolute path on disk
    overwrite: bool = False
    skip_if_exists: bool = False
    executable: bool = False
```

The installer renders `template` with the plan's `template_context` and writes the result to `target`. If the target exists:

| Flags                    | Behavior                                                    |
|--------------------------|-------------------------------------------------------------|
| Default                  | Prompt the user before overwriting                          |
| `overwrite=True`         | Overwrite without asking                                    |
| `skip_if_exists=True`    | Skip silently (preserves user customizations)               |

`executable=True` chmods the result with `+x` for owner/group/world.

### Authoring a Feature Plugin

#### 1. Package layout

```text
bp-feature-audit-log/
├── pyproject.toml
└── src/
    └── bp_feature_audit_log/
        ├── __init__.py
        ├── feature.py
        └── templates/
            └── audit_log_module.py.j2
```

#### 2. `feature.py` — define the feature

```python
from pathlib import Path

from cli.features.base import Feature, FeatureManifest, FeaturePlan, FileOp
from cli.lib.project import ProjectContext


class AuditLogFeature(Feature):
    def manifest(self) -> FeatureManifest:
        return FeatureManifest(
            name="audit-log",
            version="1.0",
            summary="Drop in an audit-log module that records mutating requests.",
        )

    def plan(self, params: dict, project: ProjectContext) -> FeaturePlan:
        templates_root = Path(__file__).parent / "templates"
        module_path = (
            project.backend_dir
            / "src/modules/audit_log/models.py"
        )
        return FeaturePlan(
            manifest=self.manifest(),
            templates_root=templates_root,
            template_context={
                "retention_days": params.get("retention_days", 90),
            },
            files=(
                FileOp(template="audit_log_module.py.j2", target=module_path),
            ),
        )


# Entry-point target — can be a Feature instance or a callable that returns one.
feature = AuditLogFeature()
```

A feature plugin writes into a directory that still exists in the layout — that's why this example targets `src/modules/<name>/` rather than the old `auth/oauth/providers/` path. OAuth providers are no longer separate files: they're registered with crudauth's `OAuthProviderFactory` in `infrastructure/auth/oauth.py`, so an "add an OAuth provider" plugin would edit that file (e.g. via an idempotent patch op) instead of dropping in a new module.

#### 3. `pyproject.toml` — declare the entry point

```toml
[project]
name = "bp-feature-audit-log"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = ["fastapi-boilerplate-cli"]

[project.entry-points."bp.features"]
audit-log = "bp_feature_audit_log.feature:feature"

[tool.setuptools]
include-package-data = true

[tool.setuptools.packages.find]
where = ["src"]

[tool.setuptools.package-data]
"*" = ["*.j2"]
```

Note `include-package-data = true` and the `package-data` glob — without these, your Jinja templates won't ship with the wheel.

#### 4. Install

```bash
uv pip install bp-feature-audit-log
# Once `bp feature` ships:
# uv run bp feature add audit-log --retention-days 90
```

### Best Practices for Feature Plugins

- **Be idempotent.** A user running your feature twice should be safe. Use `skip_if_exists=True` for files that the user might customize after first install.
- **Don't fight the user's structure.** Use `ProjectContext.backend_dir` and `ProjectContext.repo_root` rather than hardcoded paths — different projects may move things.
- **Declare every file.** Don't write files outside the plan. The installer's behavior (dry-run, idempotency, overwrite prompts) only works for files declared in the plan.
- **Put templates next to the feature.** `Path(__file__).parent / "templates"` is the canonical pattern. Keeps the plugin self-contained.
- **Use Jinja's `StrictUndefined`.** The bundled `Renderer` does this for you — missing context variables fail loudly rather than rendering empty strings.
- **Document required `params`.** Once `bp feature` lands, your manifest's `summary` is the first thing users see; document params clearly there.

## Discovery & Diagnosis

### Listing Plugins

```bash
# In-tree + plugin commands
uv run bp --help

# (Once shipped) — list features:
# uv run bp feature list
```

### Inspecting Entry Points

```bash
uv run python -c "
from importlib.metadata import entry_points
for ep in entry_points(group='bp.commands'):
    print(f'command  {ep.name:>15s}  ->  {ep.value}')
for ep in entry_points(group='bp.features'):
    print(f'feature  {ep.name:>15s}  ->  {ep.value}')
"
```

### Troubleshooting

#### My plugin doesn't appear in `bp --help`

1. **Confirm it's installed in the right venv.** Run the entry-point inspection script above. If your plugin isn't listed, the package isn't installed where `bp` runs.
2. **Check for load warnings.** `bp` prints `warning: Failed to load plugin ...` to stderr if your plugin's import fails. Run `bp --help 2>&1` to make sure stderr isn't being suppressed.
3. **Confirm your entry-point shape.** For commands, the value must resolve to a `typer.Typer` instance. For features, a `Feature` instance or a callable returning one.

#### My plugin shadows a built-in

`bp` warns and ignores plugins that try to register a name already in use by a built-in (`deploy`, `env`, `feature`). Rename your plugin to a unique key.

#### My templates aren't shipping in the wheel

Set `include-package-data = true` in `pyproject.toml` and add a `package-data` glob like `"*" = ["*.j2"]`. Without these, Jinja templates next to your code aren't included in the built wheel.

## Roadmap

- **`bp feature {list,add,remove,info}`** — user-facing surface for the feature framework. Currently the registry exists; the commands don't.
- **Codemod execution** — apply AST-aware edits declared in `FeaturePlan.codemods`. Useful for "drop a module + register its router in `interfaces/main.py`" kinds of features.
- **Post-install hooks** — execute commands declared in `FeaturePlan.hooks`. Useful for "after writing the migration, run `alembic upgrade head`" kinds of features.

The contracts (`Codemod`, `Hook`) are already in `cli.features.base` so plugin authors can declare them today without breaking the schema later.
