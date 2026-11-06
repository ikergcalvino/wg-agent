from unittest.mock import AsyncMock, patch

import pytest

from tests.conftest import NOT_RUNNING, RUNNING_DUMP, VALID_KEY

# ---------------------------------------------------------------------------
# List Interfaces
# ---------------------------------------------------------------------------


class TestListInterfaces:
    async def test_empty(self, client, tmp_path):
        with (
            patch("api.services.wireguard._run", new_callable=AsyncMock, return_value=("", "", 0)),
            patch("api.services.wireguard.CONFIG_DIR", tmp_path),
        ):
            r = await client.get("/api/v1/interfaces")
            assert r.status_code == 200
            assert r.json() == []

    async def test_with_interfaces(self, client, tmp_path):
        (tmp_path / "wg1.conf").write_text("")
        dump = f"wg0\tPRIVATE\t{VALID_KEY}\t51820\toff"
        with (
            patch("api.services.wireguard._run", new_callable=AsyncMock, return_value=(dump, "", 0)),
            patch("api.services.wireguard.CONFIG_DIR", tmp_path),
        ):
            r = await client.get("/api/v1/interfaces")
            assert r.status_code == 200
            data = r.json()
            assert [(i["name"], i["status"]) for i in data] == [("wg0", "up"), ("wg1", "down")]
            assert data[0]["listen_port"] == 51820


# ---------------------------------------------------------------------------
# Get Interface
# ---------------------------------------------------------------------------


class TestGetInterface:
    async def test_found(self, client, tmp_path):
        dump = f"PRIVATE\t{VALID_KEY}\t51820\toff"
        with (
            patch("api.services.wireguard._run", new_callable=AsyncMock, return_value=(dump, "", 0)),
            patch("api.services.wireguard.CONFIG_DIR", tmp_path),
        ):
            r = await client.get("/api/v1/interfaces/wg0")
            assert r.status_code == 200
            assert r.json()["name"] == "wg0"
            assert r.json()["status"] == "up"
            assert "private_key" not in r.json()

    async def test_down(self, client, tmp_path):
        (tmp_path / "wg0.conf").write_text("")
        with (
            patch("api.services.wireguard._run", new_callable=AsyncMock, return_value=("", NOT_RUNNING, 1)),
            patch("api.services.wireguard.CONFIG_DIR", tmp_path),
        ):
            r = await client.get("/api/v1/interfaces/wg0")
            assert r.status_code == 200
            assert r.json()["status"] == "down"

    async def test_not_found(self, client, tmp_path):
        with (
            patch("api.services.wireguard._run", new_callable=AsyncMock, return_value=("", NOT_RUNNING, 1)),
            patch("api.services.wireguard.CONFIG_DIR", tmp_path),
        ):
            r = await client.get("/api/v1/interfaces/wg0")
            assert r.status_code == 404

    async def test_invalid_name(self, client):
        r = await client.get("/api/v1/interfaces/invalid@name")
        assert r.status_code == 422


# ---------------------------------------------------------------------------
# Update Interface
# ---------------------------------------------------------------------------


class TestUpdateInterface:
    async def test_success(self, client):
        dump = f"PRIVATE\t{VALID_KEY}\t51821\toff"
        with patch("api.services.wireguard._run", new_callable=AsyncMock) as mock_run:
            mock_run.side_effect = [
                ("", "", 0),  # wg set
                (dump, "", 0),  # wg show dump (get_interface)
            ]
            r = await client.patch("/api/v1/interfaces/wg0", json={"listen_port": 51821})
            assert r.status_code == 200
            assert r.json()["listen_port"] == 51821

    async def test_empty_body_changes_nothing(self, client):
        dump = f"PRIVATE\t{VALID_KEY}\t51820\toff"
        with patch("api.services.wireguard._run", new_callable=AsyncMock, return_value=(dump, "", 0)) as mock_run:
            r = await client.patch("/api/v1/interfaces/wg0", json={})
            assert r.status_code == 200
            assert all(c.args[0][:2] == ["wg", "show"] for c in mock_run.await_args_list)

    @pytest.mark.parametrize(("has_conf", "status"), [(True, 409), (False, 404)])
    async def test_empty_body_on_a_stopped_interface(self, client, tmp_path, has_conf, status):
        if has_conf:
            (tmp_path / "wg0.conf").write_text("")
        with patch("api.services.wireguard._run", new_callable=AsyncMock, return_value=("", NOT_RUNNING, 1)):
            r = await client.patch("/api/v1/interfaces/wg0", json={})
            assert r.status_code == status

    async def test_wg_failure(self, client):
        with patch("api.services.wireguard._run", new_callable=AsyncMock, return_value=("", "Invalid fwmark", 1)):
            r = await client.patch("/api/v1/interfaces/wg0", json={"listen_port": 51821})
            assert r.status_code == 400
            assert r.json()["detail"] == "Invalid fwmark"

    async def test_down_interface_is_a_conflict(self, client, tmp_path):
        (tmp_path / "wg0.conf").write_text("")
        with patch("api.services.wireguard._run", new_callable=AsyncMock, return_value=("", NOT_RUNNING, 1)):
            r = await client.patch("/api/v1/interfaces/wg0", json={"listen_port": 51821})
            assert r.status_code == 409
            assert r.json()["detail"] == "Interface 'wg0' is not running"

    async def test_unknown_interface_is_not_found(self, client):
        with patch("api.services.wireguard._run", new_callable=AsyncMock, return_value=("", NOT_RUNNING, 1)):
            r = await client.patch("/api/v1/interfaces/wg0", json={"listen_port": 51821})
            assert r.status_code == 404

    @pytest.mark.parametrize(
        "body",
        [
            {"private_key": "bad"},
            {"listen_port": 70000},
            {"fw_mark": "0x1\nPostUp = id"},
            {"address": "10.0.0.1/24"},
        ],
    )
    async def test_invalid_body(self, client, body):
        r = await client.patch("/api/v1/interfaces/wg0", json=body)
        assert r.status_code == 422

    async def test_put_not_allowed(self, client):
        r = await client.put("/api/v1/interfaces/wg0", json={"listen_port": 51821})
        assert r.status_code == 405

    async def test_success_but_get_returns_none(self, client):
        with (
            patch("api.routers.interfaces.wg.update_interface", new_callable=AsyncMock, return_value=("", 0)),
            patch("api.routers.interfaces.wg.get_interface", new_callable=AsyncMock, return_value=None),
        ):
            r = await client.patch("/api/v1/interfaces/wg0", json={"listen_port": 51821})
            assert r.status_code == 500
            assert "could not be retrieved" in r.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Create & Delete
# ---------------------------------------------------------------------------

NEW_IFACE = {"name": "wg0", "address": "10.0.0.1/24, fd00::1/64", "private_key": VALID_KEY, "listen_port": 51820}


class TestCreateInterface:
    async def test_success(self, client, tmp_path):
        with patch("api.services.wireguard._run", new_callable=AsyncMock) as mock_run:
            mock_run.side_effect = [("", NOT_RUNNING, 1), ("", "", 0), (RUNNING_DUMP, "", 0)]
            r = await client.post("/api/v1/interfaces", json=NEW_IFACE)
        assert r.status_code == 201
        assert r.json()["status"] == "up"
        assert "private_key" not in r.json()
        assert (tmp_path / "wg0.conf").exists()

    async def test_existing_interface_is_a_conflict(self, client, tmp_path):
        (tmp_path / "wg0.conf").write_text("")
        with patch("api.services.wireguard._run", new_callable=AsyncMock, return_value=("", NOT_RUNNING, 1)):
            r = await client.post("/api/v1/interfaces", json=NEW_IFACE)
        assert r.status_code == 409

    @pytest.mark.parametrize(
        "change",
        [
            {"name": "wg@0"},
            {"address": "not-an-ip"},
            {"address": "10.0.0.1/24\nPostUp = id"},
            {"private_key": "bad"},
            {"listen_port": 0},
            {"post_up": "id"},
            {"dns": "1.1.1.1"},
        ],
    )
    async def test_invalid_body(self, client, change):
        r = await client.post("/api/v1/interfaces", json=NEW_IFACE | change)
        assert r.status_code == 422


class TestDeleteInterface:
    async def test_success(self, client, tmp_path):
        (tmp_path / "wg0.conf").write_text("")
        with patch("api.services.wireguard._run", new_callable=AsyncMock, return_value=("", NOT_RUNNING, 1)):
            r = await client.delete("/api/v1/interfaces/wg0")
        assert r.status_code == 204
        assert not (tmp_path / "wg0.conf").exists()

    async def test_unknown_interface(self, client):
        r = await client.delete("/api/v1/interfaces/wg0")
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# Interface Actions (up / down / save)
# ---------------------------------------------------------------------------


class TestInterfaceActions:
    @pytest.mark.parametrize(
        ("action", "status", "show"),
        [
            ("up", "up", ("", NOT_RUNNING, 1)),
            ("down", "down", (RUNNING_DUMP, "", 0)),
            ("save", "saved", (RUNNING_DUMP, "", 0)),
        ],
    )
    async def test_success(self, client, tmp_path, action, status, show):
        (tmp_path / "wg0.conf").write_text("")
        with patch("api.services.wireguard._run", new_callable=AsyncMock) as mock_run:
            mock_run.side_effect = [show, ("", "", 0)]
            r = await client.post(f"/api/v1/interfaces/wg0/{action}")
            assert r.status_code == 200
            assert r.json() == {"status": status, "interface": "wg0"}

    @pytest.mark.parametrize(
        ("action", "show", "detail"),
        [
            ("up", (RUNNING_DUMP, "", 0), "Interface 'wg0' is already running"),
            ("down", ("", NOT_RUNNING, 1), "Interface 'wg0' is not running"),
            ("save", ("", NOT_RUNNING, 1), "Interface 'wg0' is not running"),
        ],
    )
    async def test_wrong_state_is_a_conflict(self, client, tmp_path, action, show, detail):
        (tmp_path / "wg0.conf").write_text("")
        with patch("api.services.wireguard._run", new_callable=AsyncMock, return_value=show) as mock_run:
            r = await client.post(f"/api/v1/interfaces/wg0/{action}")
            assert r.status_code == 409
            assert r.json()["detail"] == detail
            assert mock_run.await_count == 1  # wg-quick never ran

    @pytest.mark.parametrize("action", ["up", "down", "save"])
    async def test_failure(self, client, tmp_path, action):
        (tmp_path / "wg0.conf").write_text("")
        with (
            patch("api.services.wireguard._run", new_callable=AsyncMock, return_value=("", "fail", 1)),
            patch("api.services.wireguard.CONFIG_DIR", tmp_path),
        ):
            r = await client.post(f"/api/v1/interfaces/wg0/{action}")
            assert r.status_code == 400

    @pytest.mark.parametrize("action", ["up", "down", "save"])
    async def test_not_found(self, client, tmp_path, action):
        with patch("api.services.wireguard.CONFIG_DIR", tmp_path):
            r = await client.post(f"/api/v1/interfaces/wg0/{action}")
            assert r.status_code == 404
