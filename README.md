# wg-agent

[![CI](https://github.com/ikergcalvino/wg-agent/actions/workflows/ci.yml/badge.svg)](https://github.com/ikergcalvino/wg-agent/actions/workflows/ci.yml)
[![License](https://img.shields.io/github/license/ikergcalvino/wg-agent)](https://github.com/ikergcalvino/wg-agent/blob/main/LICENSE)

An agent that runs on a host and exposes its [WireGuard](https://www.wireguard.com/) interfaces and peers through
a REST API, built with [FastAPI](https://fastapi.tiangolo.com/). A separate interface, or any other client, manages
the host through it.

The API is a thin layer over WireGuard's own tools: `wg-quick` brings interfaces up and down and saves them, and
everything else runs against the live kernel state with `wg show` and `wg set`. It never writes or parses config
files itself: the `.conf` files in `/etc/wireguard` are yours to manage.

## Features

- **Runtime management** — inspect interfaces and add, update or remove peers on running interfaces
- **Lifecycle actions** — bring interfaces up and down and save their runtime state with `wg-quick`
- **Explicit persistence** — runtime changes are written to the `.conf` file only when you call `save`
- **Offline visibility** — interfaces with a `.conf` file are listed even when they are down
- **Input validation** — interface names, WireGuard keys, CIDRs and fwmarks are validated before reaching `wg`
- **No shell** — every command runs with an argument list; secrets are passed through stdin
- **API key auth** — every endpoint except the health check requires the `X-API-Key` header
- **Docker image** — `python:3.15-alpine` with `wireguard-tools`, `iptables` and `nftables` (for `PostUp` rules
  and full-tunnel configs), for `linux/amd64` and `linux/arm64`

## Prerequisites

The **host** must have:

- The WireGuard kernel module (`sudo modprobe wireguard`)
- IP forwarding enabled if the host routes traffic for peers (`sysctl net.ipv4.ip_forward=1`)
- For full-tunnel configs (`AllowedIPs = 0.0.0.0/0`): `sysctl net.ipv4.conf.all.src_valid_mark=1`. `wg-quick`
  sets it itself, but it cannot from inside the container, so set it on the host (e.g. in `/etc/sysctl.d/`)
- One `.conf` file per interface in `/etc/wireguard` (see `wg-quick(8)`)

## Installation

```bash
git clone https://github.com/ikergcalvino/wg-agent.git
cd wg-agent
```

The API runs in Docker. It requires Docker and Docker Compose; the container uses the host network and the
`NET_ADMIN` capability, so it manages the host's WireGuard interfaces directly, and listens on port `8000` of the
host.

```bash
echo "WG_API_KEY=$(openssl rand -hex 32)" > .env   # required; .env can also set the other variables below
make up        # or: docker compose up -d --build
make down      # stop
make logs      # follow logs
```

Each [release](https://github.com/ikergcalvino/wg-agent/releases) also publishes the image to
`ghcr.io/ikergcalvino/wg-agent`.

## API Reference

Everything is served under `/api/v1`, including the interactive docs: `/api/v1/docs` (Swagger UI) and
`/api/v1/redoc` (ReDoc). Every endpoint requires the `X-API-Key: <key>` header, except the health check.

### Interfaces

| Method  | Path                             | Description                                                 |
|---------|----------------------------------|-------------------------------------------------------------|
| `GET`   | `/api/v1/interfaces`             | List running interfaces and those with a `.conf` file       |
| `GET`   | `/api/v1/interfaces/{name}`      | Get an interface                                            |
| `PATCH` | `/api/v1/interfaces/{name}`      | Update `private_key`, `listen_port` or `fw_mark` at runtime |
| `POST`  | `/api/v1/interfaces/{name}/up`   | Bring the interface up (`wg-quick up`)                      |
| `POST`  | `/api/v1/interfaces/{name}/down` | Bring the interface down (`wg-quick down`)                  |
| `POST`  | `/api/v1/interfaces/{name}/save` | Save the runtime state to its `.conf` (`wg-quick save`)     |

An interface has a `status` of `"up"` or `"down"`. Running interfaces also report `public_key`, `listen_port`,
`fw_mark` and `num_peers`; an interface that only has a `.conf` file is reported by name. `PATCH` changes only the
fields you send, and the interface must be up.

Interfaces are not created or deleted through the API: add or remove their `.conf` files in `/etc/wireguard`.

### Peers

| Method   | Path                                            | Description |
|----------|-------------------------------------------------|-------------|
| `GET`    | `/api/v1/interfaces/{iface}/peers`              | List peers  |
| `POST`   | `/api/v1/interfaces/{iface}/peers`              | Add peer    |
| `GET`    | `/api/v1/interfaces/{iface}/peers/{public_key}` | Get peer    |
| `PATCH`  | `/api/v1/interfaces/{iface}/peers/{public_key}` | Update peer |
| `DELETE` | `/api/v1/interfaces/{iface}/peers/{public_key}` | Remove peer |

Peers are managed on running interfaces only. `POST` requires `public_key` and `allowed_ips`; `PATCH` changes only
the fields you send, on an existing peer. `preshared_key` is write-only: it is accepted but never returned. Public
keys can be used in the path as they are, even when they contain `/`.

> [!NOTE]
> Peer and interface changes apply to the running interface only. Call `POST /api/v1/interfaces/{name}/save` to
> persist them, or they are lost when the interface goes down.

### Other

| Method | Path             | Description               |
|--------|------------------|---------------------------|
| `GET`  | `/api/v1`        | API info                  |
| `GET`  | `/api/v1/health` | Health check (no API key) |

Errors:

| Status | When                                                                                          |
|--------|-----------------------------------------------------------------------------------------------|
| `400`  | `wg` or `wg-quick` failed; `detail` is its error message                                      |
| `404`  | The interface is not running and has no `.conf` file, or the peer does not exist              |
| `409`  | The interface is in the wrong state: down for runtime and peer changes or `save`, already up for `up`, already down for `down` |
| `422`  | Invalid input                                                                                 |
| `503`  | `wg` or `wg-quick` cannot be used: not installed, or the API lacks `CAP_NET_ADMIN`            |
| `504`  | A command did not finish within 30 seconds                                                    |

The health check reports `degraded` when the config directory or the tools are missing, or when `wg` cannot query
the kernel (`wg_access`).

## Examples

```bash
# Bring up an interface defined in /etc/wireguard/wg0.conf
curl -X POST http://localhost:8000/api/v1/interfaces/wg0/up \
  -H "X-API-Key: your-secret-api-key"

# Add a peer
curl -X POST http://localhost:8000/api/v1/interfaces/wg0/peers \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-secret-api-key" \
  -d '{
    "public_key": "<peer-public-key>",
    "allowed_ips": "10.0.0.2/32"
  }'

# Change the listen port of the running interface
curl -X PATCH http://localhost:8000/api/v1/interfaces/wg0 \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-secret-api-key" \
  -d '{"listen_port": 51821}'

# Persist the runtime state to /etc/wireguard/wg0.conf
curl -X POST http://localhost:8000/api/v1/interfaces/wg0/save \
  -H "X-API-Key: your-secret-api-key"
```

## Configuration

| Variable          | Default          | Description                                        |
|-------------------|------------------|----------------------------------------------------|
| `WG_API_KEY`      | (required)       | API key for authentication, at least 16 characters |
| `WG_LOG_LEVEL`    | `INFO`           | Log level: DEBUG, INFO, WARNING, ERROR, CRITICAL   |
| `WG_CORS_ORIGINS` | `*`              | Comma-separated allowed CORS origins               |
| `WG_CONFIG_DIR`   | `/etc/wireguard` | Directory with the WireGuard `.conf` files         |

### Behind a reverse proxy

Since everything lives under `/api/v1`, a reverse proxy only has to forward that path as is, next to whatever else
it serves. With nginx:

```nginx
location /api/v1/ {
    proxy_pass http://127.0.0.1:8000;   # no trailing slash: keep /api/v1 in the path
}
```

## Project Structure

```
wg-agent/
├── api/
│   ├── __init__.py        # Package version
│   ├── config.py          # Settings (pydantic-settings, WG_ prefix)
│   ├── dependencies.py    # API key authentication
│   ├── exceptions.py      # Global exception handlers
│   ├── logging.py         # Logging configuration (dictConfig)
│   ├── main.py            # FastAPI app: middleware, exception handlers and routers
│   ├── models/
│   │   ├── __init__.py    # Shared validation patterns and the WireGuardKey type
│   │   ├── interfaces.py  # Interface, InterfaceUpdate and InterfaceAction models
│   │   ├── peers.py       # Peer, PeerCreate and PeerUpdate models
│   │   └── system.py      # Info and Health models
│   ├── routers/
│   │   ├── __init__.py    # Shared path parameter types
│   │   ├── interfaces.py  # Interface endpoints
│   │   ├── peers.py       # Peer endpoints
│   │   └── system.py      # API info and health check
│   └── services/
│       └── wireguard.py   # wg / wg-quick subprocess wrappers
├── tests/                 # pytest test suite
├── .github/               # CI and publish workflows, issue and PR templates
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml         # Project metadata, dependencies and tool config
└── Makefile               # Dev shortcuts
```

## Development

See [CONTRIBUTING.md](CONTRIBUTING.md). In short:

```bash
python3.15 -m venv .venv && source .venv/bin/activate   # Python 3.15, as in the Docker image
make install-dev   # pip install -e . --group dev (needs pip 25.1+)
make dev           # run with hot reload on localhost
make check         # ruff, ty and pytest
```

## How It Works

- **Lifecycle** — `up`, `down` and `save` run `wg-quick`, which reads `/etc/wireguard/<name>.conf`, including its
  `Address`, `DNS`, routes and `PreUp`/`PostUp` hooks
- **Runtime** — interface details and peers come from `wg show <name> dump`; changes are applied with `wg set`
- **Persistence** — `wg-quick save` rewrites the `.conf` file from the running interface, keeping its `wg-quick`
  settings; nothing is saved automatically
- **Down interfaces** — any `<name>.conf` in the config directory is listed as `down` without reading its contents
- **Concurrency** — `up`, `down` and `save` on the same interface run one at a time. The locks live in the
  process, so run the API with a single uvicorn worker (the default)

## Security

Read [SECURITY.md](SECURITY.md) before exposing the API. In short:

- Use a long random `WG_API_KEY`: anyone who has it controls the host's WireGuard interfaces and peers. The API
  refuses to start without one
- Keep the API off untrusted networks and terminate TLS in a reverse proxy in front of it
- Interface names, keys, CIDRs and fwmarks are validated, and commands never go through a shell
- Private and preshared keys are never returned by the API, and are passed to `wg` through stdin

## License

[MIT](LICENSE)
