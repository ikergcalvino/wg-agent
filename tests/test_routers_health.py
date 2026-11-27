from unittest.mock import AsyncMock, patch

import pytest

from api import __version__

# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

NO_CAPS = "CapEff:\t0000000000000000\n"


class TestHealth:
    async def test_ok(self, client, healthy_host):
        r = await client.get("/api/v1/health")
        assert (r.status_code, r.json()) == (200, {"version": __version__, "status": "ok", "errors": []})

    async def test_reports_every_problem_at_once(self, client, healthy_host):
        status, module, which = healthy_host
        status.write_text(NO_CAPS)
        module.rmdir()
        which.side_effect = lambda tool: None if tool == "wg-quick" else f"/usr/bin/{tool}"
        r = await client.get("/api/v1/health")
        # 503, so Docker's HEALTHCHECK marks the container unhealthy.
        assert r.status_code == 503
        assert r.json() == {
            "version": __version__,
            "status": "error",
            "errors": [
                "wg-quick is not installed",
                "the agent lacks CAP_NET_ADMIN",
                "the WireGuard kernel module is not loaded",
            ],
        }

    @pytest.mark.parametrize("caps", ["0000000000000000", "00000000a80425fb"])
    async def test_other_capabilities_are_not_enough(self, client, healthy_host, caps):
        # 00000000a80425fb is Docker's default set: everything but NET_ADMIN among the network ones.
        healthy_host[0].write_text(f"CapEff:\t{caps}\n")
        r = await client.get("/api/v1/health")
        assert r.json()["errors"] == ["the agent lacks CAP_NET_ADMIN"]

    async def test_unreadable_capabilities_count_as_missing(self, client, healthy_host):
        healthy_host[0].write_text("Name:\tpython\n")
        r = await client.get("/api/v1/health")
        assert r.json()["errors"] == ["the agent lacks CAP_NET_ADMIN"]

    async def test_runs_no_command(self, client, healthy_host):
        with patch("api.services.wireguard._run") as mock_run:
            await client.get("/api/v1/health")
        mock_run.assert_not_called()

    async def test_real_failures_still_warn(self, client, caplog):
        with patch("api.services.wireguard._run", new_callable=AsyncMock, return_value=("", "boom", 1)):
            await client.get("/api/v1/interfaces")
        assert any(r.levelname == "WARNING" and "boom" in r.getMessage() for r in caplog.records)
