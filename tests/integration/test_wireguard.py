"""Integration tests against the Docker image and real WireGuard.

They run through tests/integration/run.sh, which starts the image with uvicorn (and so
uvloop) and these config files in /etc/wireguard:
- wgtest: a plain interface
- wgnat: an interface whose PostUp/PostDown use iptables
- wglink: a symlink to a config file in a subdirectory
- wghook: an interface whose PostUp dumps its environment to /etc/wireguard/wghook-env
"""

import base64
import os
import subprocess

import httpx2
import pytest

pytestmark = pytest.mark.skipif("WG_API_URL" not in os.environ, reason="needs tests/integration/run.sh")


def new_key() -> str:
    return base64.b64encode(os.urandom(32)).decode()


def key_with_slash() -> str:
    while "/" not in (key := new_key()):
        pass
    return key


def in_container(*args: str) -> str:
    return subprocess.check_output(["docker", "exec", os.environ["WG_TEST_CONTAINER"], *args], text=True)


def container_file(path: str) -> str:
    # Files written by wg-quick belong to root inside the container, so read them from there.
    return in_container("cat", path)


def preshared_key(iface: str, public_key: str) -> str:
    # The API never returns preshared keys, so ask wg directly.
    lines = in_container("wg", "show", iface, "preshared-keys").splitlines()
    return dict(line.split("\t") for line in lines)[public_key]


def saved_conf(name: str) -> str:
    return container_file(f"/etc/wireguard/{name}.conf")


@pytest.fixture(scope="module")
def api():
    headers = {"X-API-Key": os.environ["WG_INTEGRATION_API_KEY"]}
    with httpx2.Client(base_url=os.environ["WG_API_URL"], headers=headers, timeout=40) as client:
        yield client


@pytest.fixture
def wgtest(api):
    """wgtest is up during the test and down afterwards."""
    assert api.post("/interfaces/wgtest/up").status_code == 200
    yield "wgtest"
    api.post("/interfaces/wgtest/down")


def add_peer(api, iface: str, **fields) -> httpx2.Response:
    body = {"public_key": new_key(), "allowed_ips": "10.66.0.2/32", **fields}
    return api.post(f"/interfaces/{iface}/peers", json=body)


# ---------------------------------------------------------------------------
# System
# ---------------------------------------------------------------------------


def test_health(api):
    r = api.get("/health")
    assert r.json() == {
        "status": "ok",
        "checks": {"wg_access": "ok"},
    }


def test_auth_is_required(api):
    r = httpx2.get(os.environ["WG_API_URL"] + "/interfaces")
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# Interfaces
# ---------------------------------------------------------------------------


def test_lifecycle(api):
    assert api.get("/interfaces/wgtest").json()["status"] == "down"
    assert api.post("/interfaces/wgtest/up").status_code == 200
    assert api.post("/interfaces/wgtest/up").status_code == 409
    up = api.get("/interfaces/wgtest").json()
    assert (up["status"], up["listen_port"]) == ("up", 51820)
    assert api.post("/interfaces/wgtest/down").status_code == 200
    assert api.post("/interfaces/wgtest/down").status_code == 409
    assert api.get("/interfaces/wgtest").json()["status"] == "down"


def test_list_shows_up_and_down_interfaces(api, wgtest):
    statuses = {i["name"]: i["status"] for i in api.get("/interfaces").json()}
    assert statuses == {"wgtest": "up", "wgnat": "down", "wglink": "down", "wghook": "down"}


def test_patch_runtime_settings(api, wgtest):
    before = api.get("/interfaces/wgtest").json()
    r = api.patch("/interfaces/wgtest", json={"listen_port": 51999, "fwmark": "0x10", "private_key": new_key()})
    assert r.status_code == 200
    after = r.json()
    assert (after["listen_port"], after["fwmark"]) == (51999, "0x10")
    assert after["public_key"] != before["public_key"]
    assert "private_key" not in after


def test_patch_listen_port_zero_picks_a_random_port(api, wgtest):
    r = api.patch("/interfaces/wgtest", json={"listen_port": 0})
    assert r.status_code == 200
    assert r.json()["listen_port"] not in (None, 0)  # the port the kernel picked


def test_down_interface_is_a_conflict(api):
    assert api.get("/interfaces/wgtest/peers").status_code == 409
    assert api.patch("/interfaces/wgtest", json={"listen_port": 51000}).status_code == 409
    assert add_peer(api, "wgtest").status_code == 409
    assert api.post("/interfaces/wgtest/save").status_code == 409


def test_unknown_interface_is_not_found(api):
    assert api.get("/interfaces/nope").status_code == 404
    assert api.post("/interfaces/nope/up").status_code == 404
    assert api.get("/interfaces/nope/peers").status_code == 404


def test_symlinked_config_file(api):
    assert api.post("/interfaces/wglink/up").status_code == 200
    assert api.post("/interfaces/wglink/down").status_code == 200


def test_postup_with_iptables(api):
    assert api.post("/interfaces/wgnat/up").status_code == 200
    assert api.post("/interfaces/wgnat/down").status_code == 200


def test_hooks_do_not_see_the_api_key(api):
    assert api.post("/interfaces/wghook/up").status_code == 200
    hook_env = dict(
        line.split("=", 1) for line in container_file("/etc/wireguard/wghook-env").splitlines() if "=" in line
    )
    assert api.post("/interfaces/wghook/down").status_code == 200
    assert "PATH" in hook_env
    assert "API_KEY" not in hook_env
    assert os.environ["WG_INTEGRATION_API_KEY"] not in "\n".join(hook_env.values())


# ---------------------------------------------------------------------------
# Peers
# ---------------------------------------------------------------------------


def test_peer_with_every_field(api, wgtest):
    psk = new_key()
    r = add_peer(
        api,
        wgtest,
        allowed_ips="10.66.0.3/32, fd00::3/128",
        endpoint="198.51.100.7:51820",
        preshared_key=psk,
        persistent_keepalive=25,
    )
    assert r.status_code == 201
    peer = r.json()
    assert "preshared_key" not in peer
    assert psk not in r.text
    assert set(peer["allowed_ips"].split(",")) == {"10.66.0.3/32", "fd00::3/128"}
    assert (peer["endpoint"], peer["persistent_keepalive"]) == ("198.51.100.7:51820", 25)


def test_public_key_with_slash_in_the_path(api, wgtest):
    key = key_with_slash()
    assert add_peer(api, wgtest, public_key=key).status_code == 201
    assert api.get(f"/interfaces/{wgtest}/peers/{key}").json()["public_key"] == key
    assert api.get(f"/interfaces/{wgtest}/peers/{key.replace('/', '%2F')}").status_code == 200
    assert api.delete(f"/interfaces/{wgtest}/peers/{key}").status_code == 204
    assert api.get(f"/interfaces/{wgtest}/peers/{key}").status_code == 404


def test_patch_peer(api, wgtest):
    key = add_peer(api, wgtest).json()["public_key"]
    r = api.patch(f"/interfaces/{wgtest}/peers/{key}", json={"persistent_keepalive": 15, "preshared_key": new_key()})
    assert (r.status_code, r.json()["persistent_keepalive"]) == (200, 15)


def test_patch_allowed_ips_add_remove_and_clear(api, wgtest):
    key = add_peer(api, wgtest, allowed_ips="10.66.0.2/32, 10.66.0.3/32").json()["public_key"]
    url = f"/interfaces/{wgtest}/peers/{key}"
    r = api.patch(url, json={"allowed_ips": "+10.66.0.4/32, -10.66.0.2/32"})
    assert set(r.json()["allowed_ips"].split(",")) == {"10.66.0.3/32", "10.66.0.4/32"}
    r = api.patch(url, json={"allowed_ips": "10.66.0.5/32"})
    assert r.json()["allowed_ips"] == "10.66.0.5/32"
    r = api.patch(url, json={"allowed_ips": ""})
    assert (r.status_code, r.json()["allowed_ips"]) == (200, None)


def test_patch_null_preshared_key_removes_it(api, wgtest):
    psk = new_key()
    key = add_peer(api, wgtest, preshared_key=psk).json()["public_key"]
    assert preshared_key(wgtest, key) == psk
    assert api.patch(f"/interfaces/{wgtest}/peers/{key}", json={"persistent_keepalive": 5}).status_code == 200
    assert preshared_key(wgtest, key) == psk
    assert api.patch(f"/interfaces/{wgtest}/peers/{key}", json={"preshared_key": None}).status_code == 200
    assert preshared_key(wgtest, key) == "(none)"


def test_patch_never_creates_a_peer(api, wgtest):
    key = new_key()
    assert api.patch(f"/interfaces/{wgtest}/peers/{key}", json={"persistent_keepalive": 15}).status_code == 404
    assert api.get(f"/interfaces/{wgtest}/peers/{key}").status_code == 404


def test_save_persists_runtime_changes(api, wgtest):
    key = add_peer(api, wgtest, preshared_key=new_key()).json()["public_key"]
    assert api.post(f"/interfaces/{wgtest}/save").status_code == 200
    conf = saved_conf(wgtest)
    assert f"PublicKey = {key}" in conf
    assert "PresharedKey = " in conf
    assert "Address = 10.66.0.1/24" in conf

    assert api.post(f"/interfaces/{wgtest}/down").status_code == 200
    assert api.post(f"/interfaces/{wgtest}/up").status_code == 200
    assert api.get(f"/interfaces/{wgtest}/peers/{key}").status_code == 200


def test_create_and_delete_interface(api):
    key = new_key()
    body = {"name": "wgnew", "address": "10.70.0.1/24", "private_key": key, "listen_port": 51830}
    r = api.post("/interfaces", json=body)
    assert r.status_code == 201
    assert (r.json()["status"], r.json()["listen_port"]) == ("up", 51830)
    assert api.post("/interfaces", json=body).status_code == 409

    conf = container_file("/etc/wireguard/wgnew.conf")
    assert f"PrivateKey = {key}" in conf
    mode = subprocess.check_output(
        ["docker", "exec", os.environ["WG_TEST_CONTAINER"], "stat", "-c", "%a", "/etc/wireguard/wgnew.conf"], text=True
    )
    assert mode.strip() == "600"

    assert api.delete("/interfaces/wgnew").status_code == 204
    assert api.get("/interfaces/wgnew").status_code == 404
