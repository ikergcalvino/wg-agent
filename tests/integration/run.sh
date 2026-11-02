#!/usr/bin/env bash
# Run the integration tests against a Docker image of the API and real WireGuard.
#
# Usage: tests/integration/run.sh IMAGE [pytest args...]
#
# Needs Docker and the wireguard kernel module on the host. The container gets its
# own network namespace, so the host's interfaces are never touched.
set -euo pipefail

image=${1:?usage: $0 IMAGE [pytest args...]}
shift
api_key=integration-test-api-key
port=${WG_INTEGRATION_PORT:-18080}
container=wg-agent-integration-$$
dir=$(mktemp -d)

cleanup() {
    docker rm -f "$container" >/dev/null 2>&1 || true
    rm -rf "$dir" 2>/dev/null || true
}
trap cleanup EXIT

key() { python3 -c 'import base64, os; print(base64.b64encode(os.urandom(32)).decode())'; }

mkdir "$dir/elsewhere"
printf '[Interface]\nAddress = 10.66.0.1/24\nListenPort = 51820\nPrivateKey = %s\n' "$(key)" >"$dir/wgtest.conf"
printf '[Interface]\nAddress = 10.67.0.1/24\nPrivateKey = %s\nPostUp = iptables -t nat -A POSTROUTING -o eth0 -j MASQUERADE\nPostDown = iptables -t nat -D POSTROUTING -o eth0 -j MASQUERADE\n' "$(key)" >"$dir/wgnat.conf"
printf '[Interface]\nAddress = 10.68.0.1/24\nPrivateKey = %s\n' "$(key)" >"$dir/elsewhere/wglink.conf"
ln -s elsewhere/wglink.conf "$dir/wglink.conf"
chmod -R go-rwx "$dir"

docker run -d --name "$container" --cap-add NET_ADMIN -e WG_API_KEY="$api_key" \
    -v "$dir:/etc/wireguard" -p "127.0.0.1:$port:8000" "$image" >/dev/null
curl -fsS --retry 30 --retry-delay 1 --retry-all-errors -o /dev/null "http://127.0.0.1:$port/api/v1/health"

WG_API_URL="http://127.0.0.1:$port/api/v1" WG_INTEGRATION_API_KEY="$api_key" WG_TEST_CONTAINER="$container" \
    "${PYTHON:-python}" -m pytest tests/integration --no-cov "$@" || {
    echo "--- container logs:"
    docker logs "$container"
    exit 1
}
