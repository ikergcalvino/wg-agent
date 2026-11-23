FROM ghcr.io/astral-sh/uv:0.13.6 AS uv

FROM python:3.15-alpine AS build

COPY --from=uv /uv /bin/uv

ENV UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never UV_COMPILE_BYTECODE=1

WORKDIR /opt/wg-agent

COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-project

COPY README.md LICENSE ./
COPY api/ api/

# No cache mount: uv only rebuilds a local package when pyproject.toml changes (stale code).
RUN uv sync --locked --no-dev --no-editable

FROM python:3.15-alpine

# uvicorn reads UVICORN_HOST itself. Loopback: the agent runs on the host network, where 0.0.0.0 would be every
# address of the host. Set it to reach the API without a reverse proxy, or with a bridge network and -p.
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PATH="/opt/wg-agent/.venv/bin:$PATH" UVICORN_HOST=127.0.0.1

RUN apk add --no-cache wireguard-tools iproute2 iptables nftables

WORKDIR /opt/wg-agent

COPY --from=build /opt/wg-agent/.venv /opt/wg-agent/.venv

EXPOSE 8000/tcp

# Call the API where it listens: UVICORN_HOST, or loopback when that is every address.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD host=$UVICORN_HOST; [ "$host" = 0.0.0.0 ] && host=127.0.0.1; \
        wget -q --spider "http://$host:8000/api/v1/health" || exit 1

CMD ["uvicorn", "api.main:app", "--port", "8000"]
