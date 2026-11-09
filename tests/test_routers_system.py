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
        with patch("api.services.wireguard._run", new_callable=AsyncMock, return_value=("", "No such device", 1)):
            r = await client.get("/api/v1/health")
        assert r.status_code == 200
        assert r.json() == {"status": "ok", "error": None}

    @pytest.mark.parametrize(
        ("probe", "status", "error"),
        [
            (("", "Unable to access interface: No such device", 1), "ok", None),
            (("PRIVATE\tPUBLIC\t51820\toff", "", 0), "ok", None),
            (
                ("", "Unable to access interface: Operation not permitted", 1),
                "error",
                "Unable to access interface: Operation not permitted (the API needs CAP_NET_ADMIN)",
            ),
            (
                ("", "Unable to access interface: Protocol not supported", 1),
                "error",
                "Unable to access interface: Protocol not supported",
            ),
        ],
    )
    async def test_health_checks_access_to_wireguard(self, client, probe, status, error):
        with patch("api.services.wireguard._run", new_callable=AsyncMock, return_value=probe) as mock_run:
            r = await client.get("/api/v1/health")
        assert r.json() == {"status": status, "error": error}
        assert r.status_code == (200 if status == "ok" else 503)  # 503 marks the container unhealthy in Docker
        mock_run.assert_awaited_once_with(["wg", "show", "wg-agent-probe", "dump"])

    async def test_health_reports_a_missing_wg(self, client):
        with patch("asyncio.create_subprocess_exec", side_effect=FileNotFoundError(2, "No such file or directory")):
            r = await client.get("/api/v1/health")
        assert (r.status_code, r.json()["error"]) == (503, "Cannot execute wg: No such file or directory")

    async def test_health_probe_logs_no_warning(self, client, caplog):
        # Docker calls /health every 30 s, and the probe is expected to fail.
        with patch("api.services.wireguard._run", new_callable=AsyncMock, return_value=("", "No such device", 1)):
            await client.get("/api/v1/health")
        assert not [r for r in caplog.records if r.levelname == "WARNING"]

    async def test_real_failures_still_warn(self, client, caplog):
        with patch("api.services.wireguard._run", new_callable=AsyncMock, return_value=("", "boom", 1)):
            await client.get("/api/v1/interfaces")
        assert any(r.levelname == "WARNING" and "boom" in r.getMessage() for r in caplog.records)
