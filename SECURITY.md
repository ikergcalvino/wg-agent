# Security Policy

wg-agent is an agent that manages the WireGuard interfaces and peers of the
host it runs on through a REST API. It needs `CAP_NET_ADMIN`, so anyone who can
use it can change the host's VPN configuration. This document explains which
versions receive security fixes, how to report a vulnerability, and where the
boundaries of the project lie.

## Supported versions

wg-agent is pre-1.0 and under active development. Security fixes are made
on the **latest commit of `main`** only. Please confirm that an issue
reproduces there before reporting it.

| Version          | Supported |
|------------------|-----------|
| Latest on `main` | ✅        |
| Anything older   | ❌        |

## Reporting a vulnerability

> [!IMPORTANT]
> Please **do not** report security vulnerabilities through public GitHub
> issues, discussions or pull requests.

Report vulnerabilities privately through GitHub's
[private vulnerability reporting](https://github.com/ikergcalvino/wg-agent/security/advisories/new).
If that is not possible, email the maintainer at **iker.gcalvino@udc.es**.

Please include:

- A description of the vulnerability and its potential impact.
- Steps to reproduce or a minimal proof of concept.
- The affected wg-agent commit and the `wireguard-tools` version.

### What to expect

- **Acknowledgement** within 5 business days.
- **Initial assessment** — whether the report is accepted, and its severity —
  within 10 business days.
- **Fix and disclosure** coordinated with you. Once a fix is released, a
  GitHub Security Advisory is published and the reporter is credited unless
  they prefer to remain anonymous.

Please allow a reasonable amount of time for a fix before disclosing the issue
publicly.

## Scope

### In scope

Vulnerabilities in wg-agent's own code, for example:

- Bypassing API key authentication.
- Leakage of secrets such as private keys, preshared keys or the API key
  (e.g. through responses, logs or error messages).
- Arguments reaching `wg` or `wg-quick` in a way that lets a client run
  commands or touch files or interfaces it should not.
- Insecure defaults in the application, the Docker image or
  `docker-compose.yml`.

### Out of scope

- **Vulnerabilities in WireGuard itself, the kernel module, `wg` or
  `wg-quick`.** Please report them to the
  [WireGuard project](https://www.wireguard.com/).
- Vulnerabilities in third-party dependencies such as FastAPI or uvicorn,
  which should be reported to their respective maintainers. Reports about
  wg-agent depending on a vulnerable version are welcome.
- Commands in `PreUp`, `PostUp`, `PreDown` and `PostDown` of the `.conf`
  files. The API does not write config files: whoever controls
  `/etc/wireguard` controls what `wg-quick` runs as root.
- Insecure setups that the operator explicitly opts into, such as a weak
  API key or exposing the API to untrusted networks.

## Running wg-agent securely

- **Use a strong `WG_API_KEY`.** It is required, and the API refuses to
  start without it, but anyone who has it controls the host's WireGuard
  interfaces and peers. Use a long random value (e.g.
  `openssl rand -hex 32`) and keep it out of version control.
- **Do not expose the API to untrusted networks.** With `network_mode: host`
  it listens on port 8000 of every interface of the host. Restrict it with a
  firewall, or put it behind a reverse proxy.
- **Use TLS.** The API serves plain HTTP, so the API key and the keys in
  request bodies travel in clear text. Terminate TLS in a reverse proxy in
  front of it.
- **Restrict CORS.** Set `WG_CORS_ORIGINS` to the origins of your frontend
  instead of `*`.
- **Protect `/etc/wireguard`.** Config files contain private keys and the
  commands `wg-quick` runs as root. Keep them owned by root with `0600`
  permissions.
