#!/usr/bin/env bash
# Runs once, when the Dev Container is created.
set -euo pipefail

uv sync

# A sample interface for `make dev`. It lives inside the container, in its own network
# namespace, so bringing it up never touches the host's WireGuard.
if ! sudo test -e /etc/wireguard/wg0.conf; then
    sudo install -d -m 700 /etc/wireguard
    printf '[Interface]\nAddress = 10.99.0.1/24\nListenPort = 51820\nPrivateKey = %s\n' "$(wg genkey)" \
        | sudo install -m 600 /dev/stdin /etc/wireguard/wg0.conf
fi
