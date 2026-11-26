# Generating and updating projects with fastro

fastro is the tool that reads this repository's `blueprint.toml`. The root dev group installs it,
so after `uv sync --all-packages --all-extras` every command below runs from the repository root
through `uv run --no-sync`. Every command has `--help`.

## Writing the compose files: `fastro make deploy`

```bash
uv run --no-sync fastro make deploy local
```

`fastro make deploy` renders `[generators.deploy]` from `blueprint.toml`: `docker-compose.yml` for
the mode it is given, and for `nginx` also `nginx/default.conf`, at the repository root unless
`--output-dir` says otherwise. Each file starts with a header naming the command that wrote it,
and a compose file's opening comment goes on to name the services that project's file runs. The
compose project is named after the project's slug, `fastapi-boilerplate` here. Apart from that
opening comment, the header line, the project name and the `redis` service of the `prod` and
`nginx` stacks, which requires a password, the files are byte for byte what the legacy deploy
command wrote.

It runs in the blueprint repository. In a project fastro created it exits 2 for now.
`bp deploy generate` exits 2 too, in a project made before fastro.

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
| `--force`, `-f` | | Replace a file that differs without asking |
| `--yes`, `-y` | | The same as `--force` |
| `--dry-run` | | Name each file it would write, and write nothing |

```bash
uv run --no-sync fastro make deploy prod --workers 8 --api-port 9000
uv run --no-sync fastro make deploy nginx --output-dir /tmp/scratch --dry-run
uv run --no-sync fastro make deploy nginx --internal-subnet 10.89.0.0/24
```

It prints one line per file: `wrote X`, `unchanged X` when the file already holds what it would
write, or `kept X` when you decline to replace it. With `--dry-run` it prints `would write X (N
bytes)` for each file it would write, and writes nothing. A file that differs is replaced only once you confirm, or with `--force` or
`--yes`; with no terminal to ask on, it is kept and named, and the exit is still 0.

`--internal-subnet` has to name a network of `/8` or smaller for IPv4, and `/48` or smaller for
IPv6. For `nginx` it is written as the compose network's subnet and as `FORWARDED_ALLOW_IPS` for
the API container. Every value is checked in every mode, so a value with host bits set
(`172.31.240.1/24`), a wildcard, or a wider range exits 2 before any file is written. `local` and
`prod` always use the default network.

## Preparing the environment: `fastro env`

### `fastro env secret`

```bash
uv run --no-sync fastro env secret
uv run --no-sync fastro env secret --bytes 16
uv run --no-sync fastro env secret | gh secret set SECRET_KEY --repo my-org/my-app
```

Prints a hex key for `SECRET_KEY`: `--bytes` random bytes, from `16` to `128`, `32` by default,
so 64 hex characters. It is built in, so it prints a token anywhere. In this repository it runs
`scripts.gen_secret` instead, which draws again while the app's secret-key rules would refuse the
key.

### `fastro env validate`

```bash
uv run --no-sync fastro env validate
```

In this repository it runs `scripts.validate_env`: the production security validator the app runs
at startup, against your settings as if `ENVIRONMENT` were `production`, whatever it is set to. It
prints what it finds, critical findings first, and exits 1 when anything is critical and 0
otherwise, so a deploy job can run it as a gate. The checks themselves are in
[The Production Validator](production.md#the-production-validator).

Anywhere else it exits 2 and says why: outside a project, and in a project fastro created, for now,
or in a blueprint repository whose selection declares no `env validate`.

## In the blueprint repository: `fastro sync` and `fastro blueprint`

`fastro sync` regenerates the wiring files that `blueprint.toml`'s `[[wiring]]` tables list, most
of them under `backend/src/wiring/`, from `blueprint.toml` and `fastro.toml`, and
`fastro sync --check` fails when the two have drifted. `fastro blueprint lint`
checks the catalog, and `fastro blueprint verify` builds projects from it and runs their checks.
These are for working on FastAPI-boilerplate itself.
