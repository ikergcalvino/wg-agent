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
        assert r.json() == {"status": "ok", "checks": {"wg_access": "ok"}}

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
        mock_run.assert_awaited_once_with(["wg", "show", "wg-agent-probe", "dump"])

    async def test_health_degraded_without_access(self, client):
        # 503, so Docker's HEALTHCHECK marks the container unhealthy.
        with patch(
            "api.services.wireguard._run", new_callable=AsyncMock, return_value=("", "Operation not permitted", 1)
        ):
            r = await client.get("/api/v1/health")
        assert r.status_code == 503
        assert r.json() == {"status": "degraded", "checks": {"wg_access": "error"}}

    async def test_health_probe_logs_no_warning(self, client, caplog):
        # Docker calls /health every 30 s, and the probe is expected to fail.
        with patch("api.services.wireguard._run", new_callable=AsyncMock, return_value=("", "No such device", 1)):
            await client.get("/api/v1/health")
        assert not [r for r in caplog.records if r.levelname == "WARNING"]

    async def test_real_failures_still_warn(self, client, caplog):
        with patch("api.services.wireguard._run", new_callable=AsyncMock, return_value=("", "boom", 1)):
            await client.get("/api/v1/interfaces")
        assert any(r.levelname == "WARNING" and "boom" in r.getMessage() for r in caplog.records)
