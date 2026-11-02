import shutil
from unittest.mock import AsyncMock, patch

import pytest

# ---------------------------------------------------------------------------
# Info & Health
# ---------------------------------------------------------------------------


class TestSystem:
    async def test_info(self, client):
        r = await client.get("/api/v1")
        assert r.status_code == 200
        data = r.json()
        assert data["name"] == "wg-agent"
        assert "version" in data

    async def test_health(self, client):
        r = await client.get("/api/v1/health")
        assert r.status_code == 200
        data = r.json()
        assert "status" in data
        assert "checks" in data

    async def test_health_degraded_missing_wg(self, client):
        with patch.object(shutil, "which", side_effect=lambda cmd: None if cmd == "wg" else "/usr/bin/" + cmd):
            r = await client.get("/api/v1/health")
            assert r.status_code == 200
            data = r.json()
            assert data["status"] == "degraded"
            assert data["checks"]["wg"] == "missing"

    async def test_health_degraded_missing_wg_quick(self, client):
        with patch.object(shutil, "which", side_effect=lambda cmd: None if cmd == "wg-quick" else "/usr/bin/" + cmd):
            r = await client.get("/api/v1/health")
            assert r.status_code == 200
            data = r.json()
            assert data["status"] == "degraded"
            assert data["checks"]["wg_quick"] == "missing"

    async def test_health_degraded_missing_config_dir(self, client, tmp_path):
        missing = tmp_path / "nonexistent"
        with patch("api.routers.system.settings") as mock_settings:
            mock_settings.config_dir = missing
            r = await client.get("/api/v1/health")
            assert r.status_code == 200
            data = r.json()
            assert data["status"] == "degraded"
            assert data["checks"]["config_dir"] == "missing"

    @pytest.mark.parametrize(
        ("probe", "expected"),
        [
            (("", "Unable to access interface: No such device", 1), "ok"),
            (("", "Unable to access interface: Operation not permitted", 1), "error"),
            (("", "Unable to access interface: Protocol not supported", 1), "error"),
        ],
    )
    async def test_health_checks_access_to_wireguard(self, client, probe, expected):
        with patch("api.services.wireguard._run", new_callable=AsyncMock, return_value=probe) as mock_run:
            r = await client.get("/api/v1/health")
        assert r.json()["checks"]["wg_access"] == expected
        mock_run.assert_awaited_once_with(["wg", "show", "wgapi-probe", "dump"])

    async def test_health_degraded_without_access(self, client):
        with (
            patch.object(shutil, "which", return_value="/usr/bin/wg"),
            patch(
                "api.services.wireguard._run", new_callable=AsyncMock, return_value=("", "Operation not permitted", 1)
            ),
        ):
            r = await client.get("/api/v1/health")
        assert r.json()["status"] == "degraded"
