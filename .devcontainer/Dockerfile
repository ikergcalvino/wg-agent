FROM mcr.microsoft.com/devcontainers/python:3-3.15-trixie

COPY --from=ghcr.io/astral-sh/uv:0.13.6 /uv /usr/local/bin/

RUN apt-get update \
    && apt-get install -y --no-install-recommends wireguard-tools iproute2 iptables nftables \
    && rm -rf /var/lib/apt/lists/*
