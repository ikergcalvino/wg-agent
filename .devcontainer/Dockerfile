# Development image: Debian, as the Dev Container tooling expects. Production stays on Alpine
# (../Dockerfile), and the integration tests run against that image.
FROM mcr.microsoft.com/devcontainers/python:3.15-trixie

COPY --from=ghcr.io/astral-sh/uv:0.13.6 /uv /uvx /usr/local/bin/

# The same WireGuard tools as the production image.
RUN apt-get update \
    && apt-get install -y --no-install-recommends wireguard-tools iproute2 iptables nftables \
    && rm -rf /var/lib/apt/lists/*
