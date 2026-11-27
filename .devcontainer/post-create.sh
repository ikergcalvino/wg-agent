#!/usr/bin/env bash

set -euo pipefail

uv sync

if ! sudo test -e /etc/wireguard/wg0.conf; then
    sudo install -d -m 700 /etc/wireguard
    sudo install -m 600 /dev/stdin /etc/wireguard/wg0.conf <<EOF
[Interface]
Address = 10.99.0.1/24
ListenPort = 51820
PrivateKey = $(wg genkey)
EOF
fi
