# Generating and updating projects with fastro

fastro is the tool that reads this repository's `blueprint.toml`. The root dev group installs it,
so after `uv sync --all-packages --all-extras` every command below runs from the repository root
through `uv run --no-sync`. Every command has `--help`.

## Writing the compose files: `fastro make deploy`

```bash
uv run --no-sync fastro make deploy local
```

`fastro make deploy` writes `docker-compose.yml` for the mode it is given, and for `nginx` also
`nginx/default.conf`, at the repository root unless `--output-dir` says otherwise.

| Mode | Stack | Files |
|---|---|---|
| `local` | The API from the `dev` stage, source mounted, hot reload, with Postgres and Redis | `docker-compose.yml` |
| `prod` | The API from the `prod` stage with `WORKERS` workers, with Postgres and Redis and a `migrate` one-shot | `docker-compose.yml` |
| `nginx` | The API from the `prod` stage, with Postgres and Redis and a `migrate` one-shot, behind an nginx reverse proxy on port 80 | `docker-compose.yml`, `nginx/default.conf` |

A project with the taskiq feature also gets a `worker` and one `scheduler` in every mode.
[Docker Setup](configuration/docker-setup.md) walks through what `local` writes, and
[Migrations](database/migrations.md) how a deploy runs the `migrate` service.

| Option | Default | What it sets |
|---|---|---|
| `--output-dir`, `-o` | the repository root | Where the files are written |
| `--api-port` | `8000` | The host port the API is published on, for `local` and `prod` |
| `--workers` | `4` | API workers, for `prod` and `nginx` |
| `--internal-subnet` | `172.31.240.0/24` | The compose network, and the only peers uvicorn takes forwarded headers from, for `nginx` |
| `--force`, `-f` | | Overwrite existing files without asking |
| `--yes`, `-y` | | Assume yes for every prompt |
| `--dry-run` | | Show what would be written, and write nothing |

```bash
uv run --no-sync fastro make deploy prod --workers 8 --api-port 9000
uv run --no-sync fastro make deploy nginx --output-dir /tmp/scratch --dry-run
uv run --no-sync fastro make deploy nginx --internal-subnet 10.89.0.0/24
```

For `nginx`, `--internal-subnet` has to name a network of `/8` or smaller for IPv4, and `/48` or
smaller for IPv6. It is written as the compose network's subnet and as `FORWARDED_ALLOW_IPS` for
the API container, so a value with host bits set (`172.31.240.1/24`), a wildcard, or a wider
range is refused before any file is written. `local` and `prod` always use the default network.

## Preparing the environment: `fastro env`

### `fastro env secret`

```bash
uv run --no-sync fastro env secret
uv run --no-sync fastro env secret --bytes 16
uv run --no-sync fastro env secret | gh secret set SECRET_KEY --repo my-org/my-app
```

Prints a hex key for `SECRET_KEY`: `--bytes` random bytes, from `16` to `128`, `32` by default,
so 64 hex characters. In a project it runs the project's own `scripts.gen_secret`, which draws
again while the app's secret-key rules would refuse the key.

### `fastro env validate`

```bash
uv run --no-sync fastro env validate
```

Runs the project's `scripts.validate_env`: the production security validator the app runs at
startup, against your settings as if `ENVIRONMENT` were `production`, whatever it is set to. It
prints what it finds, critical findings first, and exits 1 when anything is critical and 0
otherwise, so a deploy job can run it as a gate. The checks themselves are in
[The Production Validator](production.md#the-production-validator).

## In the blueprint repository: `fastro sync` and `fastro blueprint`

`fastro sync` regenerates the wiring files that `blueprint.toml`'s `[[wiring]]` tables list, most
of them under `backend/src/wiring/`, from `blueprint.toml` and `fastro.toml`, and
`fastro sync --check` fails when the two have drifted. `fastro blueprint lint`
checks the catalog, and `fastro blueprint verify` builds projects from it and runs their checks.
These are for working on FastAPI-boilerplate itself.
