#!/usr/bin/env bash

set -euo pipefail

uv sync

if ! sudo test -e /etc/wireguard/wg0.conf; then
    sudo install -d -m 700 /etc/wireguard
    printf '[Interface]\nAddress = 10.99.0.1/24\nListenPort = 51820\nPrivateKey = %s\n' "$(wg genkey)" \
        | sudo install -m 600 /dev/stdin /etc/wireguard/wg0.conf
fi
