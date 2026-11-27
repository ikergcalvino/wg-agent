# Contributing to wg-agent

Thanks for your interest in improving wg-agent! Contributions, bug reports and feature requests are all
welcome. This guide covers how the project is organized, how to set up your environment and the conventions it
follows.

## Ways to contribute

- **Report a bug** or **request a feature** by opening an
  [issue](https://github.com/ikergcalvino/wg-agent/issues/new/choose).
- **Report a security vulnerability** privately, as described in the [security policy](SECURITY.md).
- **Open a pull request** to fix a bug, add a feature, or improve the documentation, the tests or the CI.

## How the code is organized

```
api/
├── main.py           # FastAPI app: logging (LOG_LEVEL), exception handlers and routers
├── auth.py           # The X-API-Key check (API_KEY)
├── exceptions.py     # Every error the API can answer, each with its status code
├── types.py          # The formats the API accepts: keys, names, addresses, ports...
├── routers/          # HTTP layer: one module per resource (interfaces, peers, health)
├── models/           # Pydantic models: the shape of requests and responses
└── services/
    ├── wireguard.py  # Every call to wg, wg-quick and ip
    └── health.py     # What the agent needs from the host, checked without running commands
```

- **Routers** only map each route to one service call. The service returns the resource as it is after the change
  and raises the errors in `exceptions.py`, each with its status code, so routers never build responses or errors.
- **`services/wireguard.py`** is the only module that runs `wg`, `wg-quick` or `ip`, always through `_run()`, with an
  argument list and never a shell. Private keys go through a pipe and are read from `/dev/stdin`, never from
  arguments or temporary files.
- **The API never parses config files**, and only writes one to create an interface (address, key and port,
  never hooks) and removes it to delete one. `wg-quick` owns the interface lifecycle; everything else runs against
  the live kernel state with `wg show` and `wg set`. Please keep it that way.
- **Validate input with the types in `types.py`.** Anything that reaches `wg` must first be checked by one of them,
  in request bodies and path parameters alike. A new format goes there; models only declare fields with them.

## Development setup

### Dev Container (recommended)

The repository ships a [Dev Container](https://containers.dev/): an isolated development environment with Python
3.15, uv, the WireGuard tools and Docker. You only need Docker and an editor that supports Dev Containers, such as
VS Code with the Dev Containers extension.

1. Clone the repository and open it in VS Code.
2. Run **Dev Containers: Reopen in Container**.

The first start builds the image and runs `uv sync`. The Python, Ruff and ty extensions come preinstalled, and
every `make` target works inside it. The container has its own network namespace, so `make dev` uses real
WireGuard without ever touching the host's. It runs privileged, as Docker-in-Docker requires. The host needs the `wireguard` kernel module
(`sudo modprobe wireguard`).

### Without the Dev Container

[uv](https://docs.astral.sh/uv/getting-started/installation/) installs Python 3.15 and the locked dependencies, and
covers everything except `make dev`:

```bash
make setup   # uv sync: creates .venv with Python 3.15 and everything in uv.lock
```

### Dependencies

- **Python 3.15**, the version in the Docker image, pinned in `.python-version`.
- **`uv.lock`** pins every dependency, direct and indirect. After changing dependencies in `pyproject.toml`, run
  `uv lock` and commit the updated lockfile; CI fails if it is out of date.
- The development tools are [dependency groups](https://packaging.python.org/en/latest/specifications/dependency-groups/)
  in `pyproject.toml` (`lint`, `test`, `type`, and `dev` with all of them), so they are not published with the
  package. `make` targets run them through `uv run`, so there is no virtualenv to activate.

## Running the API

```bash
make dev   # in the Dev Container
```

`make dev` runs the API with hot reload at <http://127.0.0.1:8000/api/v1/docs>, with the API key
`dev-api-key-0123456789`. It uses real WireGuard: a sample `wg0` is ready in `/etc/wireguard` inside the
container, so you can bring it up and manage peers. It runs as root, as wg-quick requires, which is why it refuses
to run outside the Dev Container: there, it would change the host's WireGuard.

## Quality checks

CI runs these checks on every push and pull request to `main` and `develop`, with the tests on every supported
Python version, runs the integration tests against the Docker image, and builds the Dev Container. Run them locally before pushing:

```bash
make check                # all of the below
make lint                 # ruff check and ruff format --check (use `make format` to fix)
make type                 # ty check
make test                 # unit tests, with a coverage threshold of 90%
make integration          # integration tests against the Docker image and real WireGuard
docker compose build      # build the Docker image
```

- Line length is 120 and imports are sorted by ruff.
- pytest turns warnings into errors.
- Unit tests mock `_run()`, so no WireGuard interface or root access is needed. Add tests for new features and bug
  fixes, at the service level and through the HTTP API.
- Integration tests (`tests/integration/`) run the Docker image against real WireGuard, in its own network
  namespace so the host's interfaces are never touched. They need Docker and the `wireguard` kernel module, and CI
  runs them on every push:

  ```bash
  make integration
  ```

## Branching and pull requests

- Branch off **`develop`** and target your pull request at **`develop`**. `main` is reserved for releases.
- Keep pull requests focused: one logical change per PR.
- Fill in the PR template and make sure the checks pass before requesting review. If your change modifies or
  removes public API (endpoints, request or response fields, status codes or configuration variables), mark it as
  a breaking change.
- Commit messages follow a [Conventional Commits](https://www.conventionalcommits.org/) style (`feat:`, `fix:`,
  `docs:`, `ci:`, `build:`, `deps:`, …).

## License

By contributing, you agree that your contributions will be licensed under the [MIT License](LICENSE).
