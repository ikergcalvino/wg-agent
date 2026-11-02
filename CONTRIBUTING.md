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
├── main.py           # FastAPI app: middleware, exception handlers and routers
├── routers/          # HTTP layer: one module per resource (interfaces, peers, system)
├── models/           # Pydantic models and validation patterns
└── services/
    └── wireguard.py  # Every call to wg and wg-quick
```

- **Routers** translate HTTP requests into service calls and service results into responses. They never run
  commands themselves.
- **`services/wireguard.py`** is the only module that runs `wg` or `wg-quick`, always through `_run()`, with an
  argument list and never a shell. Secrets such as private and preshared keys go through stdin, never as
  arguments.
- **The API does not write or parse config files.** `wg-quick` owns the interface lifecycle and the `.conf`
  files; everything else runs against the live kernel state with `wg show` and `wg set`. Please keep it that way.
- **Validate input in the models.** Anything that reaches `wg` must first be checked by a Pydantic validator or a
  path parameter pattern.

## Development setup

Development uses [uv](https://docs.astral.sh/uv/getting-started/installation/), which installs Python 3.15 and the
locked dependencies for you:

```bash
git clone https://github.com/ikergcalvino/wg-agent.git
cd wg-agent

make setup   # uv sync: creates .venv with Python 3.15 and everything in uv.lock
```

- **Python 3.15**, the version in the Docker image, pinned in `.python-version`. uv downloads it if it is missing.
- **`uv.lock`** pins every dependency, direct and indirect. After changing dependencies in `pyproject.toml`, run
  `uv lock` and commit the updated lockfile; CI fails if it is out of date.
- The development tools are [dependency groups](https://packaging.python.org/en/latest/specifications/dependency-groups/)
  in `pyproject.toml` (`lint`, `test`, `type`, and `dev` with all of them), so they are not published with the
  package. `make` targets run them through `uv run`, so there is no virtualenv to activate.

## Running the API

```bash
make dev
```

`make dev` runs the API in Docker with hot reload, at <http://127.0.0.1:8000/api/v1/docs> with the API key
`dev-api-key-0123456789`. It uses real WireGuard, so you can bring interfaces up and manage peers, but the
container has its own network namespace: nothing it does touches the host's WireGuard. It mounts `api/`, so
changes reload in place, and keeps its config files in `.dev/wireguard`, where it creates a sample `wg0.conf`
the first time. Files that the API saves there belong to root. Rebuild with `make dev` after changing
dependencies. It needs Docker and the `wireguard` kernel module (`sudo modprobe wireguard`).

## Quality checks

CI runs these checks on every push and pull request to `main` and `develop`, with the tests on every supported
Python version, and runs the integration tests against the Docker image. Run them locally before pushing:

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
