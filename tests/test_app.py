from unittest.mock import AsyncMock, patch

import pytest
from httpx2 import ASGITransport, AsyncClient

from api.exceptions import AgentError, WireGuardTimeout
from api.main import app
from tests import TEST_API_KEY
from tests.conftest import VALID_KEY

# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


class TestAuth:
    @pytest.fixture
    async def anonymous(self):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            yield ac

    async def test_rejects_missing_key(self, anonymous):
        r = await anonymous.get("/api/v1/interfaces")
        assert r.status_code == 403

    @pytest.mark.parametrize("key", ["wrong", "", "test-api-key-012345678", "séc".encode("latin-1")])
    async def test_rejects_wrong_key(self, anonymous, key):
        r = await anonymous.get("/api/v1/interfaces", headers={"X-API-Key": key})
        assert r.status_code == 403

    async def test_accepts_valid_key(self, client):
        with patch("api.services.wireguard._run", new_callable=AsyncMock, return_value=("", "", 0)):
            r = await client.get("/api/v1/interfaces")
            assert r.status_code == 200

    async def test_health_does_not_need_a_key(self, anonymous, healthy_host):
        r = await anonymous.get("/api/v1/health")
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# Exception Handlers
# ---------------------------------------------------------------------------


class TestExceptionHandlers:
    async def test_missing_wg_binary_returns_503(self, client):
        with patch("asyncio.create_subprocess_exec", side_effect=FileNotFoundError(2, "No such file or directory")):
            r = await client.get("/api/v1/interfaces/wg0")
            assert r.status_code == 503
            assert r.json()["detail"] == "Cannot execute wg: No such file or directory"

    async def test_wg_failure_returns_400_with_its_message(self, client):
        with patch("api.services.wireguard._run", new_callable=AsyncMock, return_value=("", "Line unrecognized", 1)):
            r = await client.delete(f"/api/v1/interfaces/wg0/peers/{VALID_KEY}")
            assert r.status_code == 400
            assert r.json()["detail"] == "Line unrecognized"

    async def test_missing_capability_returns_503(self, client):
        with patch(
            "api.services.wireguard._run",
            new_callable=AsyncMock,
            return_value=("", "Unable to access interface: Operation not permitted", 1),
        ):
            r = await client.get("/api/v1/interfaces")
            assert r.status_code == 503
            assert "CAP_NET_ADMIN" in r.json()["detail"]

    @pytest.mark.parametrize("cls", AgentError.__subclasses__(), ids=lambda cls: cls.__name__)
    async def test_every_agent_error_answers_its_status_code(self, client, cls):
        # A new error needs no registration: the handler reads status_code from the class.
        exc = cls.__new__(cls)
        Exception.__init__(exc, "message")
        with patch("api.services.wireguard._run", new_callable=AsyncMock, side_effect=exc):
            r = await client.get("/api/v1/interfaces")
        assert (r.status_code, r.json()["detail"]) == (cls.status_code, "message")

    async def test_timeout_returns_504(self, client):
        with patch("api.services.wireguard._run", new_callable=AsyncMock, side_effect=WireGuardTimeout("slow")):
            r = await client.get("/api/v1/interfaces")
            assert r.status_code == 504

    async def test_wg_failure_without_output_has_a_message(self, client):
        with patch("api.services.wireguard._run", new_callable=AsyncMock, return_value=("", "", 3)):
            r = await client.delete(f"/api/v1/interfaces/wg0/peers/{VALID_KEY}")
            assert r.json()["detail"] == "wg exited with status 3"

    async def test_internal_value_error_is_not_a_client_error(self):
        transport = ASGITransport(app=app, raise_app_exceptions=False)
        async with AsyncClient(transport=transport, base_url="http://test", headers={"X-API-Key": TEST_API_KEY}) as c:
            with patch("api.services.wireguard._run", new_callable=AsyncMock, side_effect=ValueError("bug")):
                r = await c.get("/api/v1/interfaces/wg0")
                assert r.status_code == 500
                assert r.json()["detail"] == "Internal server error"

    async def test_unhandled_exception_returns_500_and_logs_the_traceback(self, caplog):
        transport = ASGITransport(app=app, raise_app_exceptions=False)
        async with AsyncClient(transport=transport, base_url="http://test", headers={"X-API-Key": TEST_API_KEY}) as c:
            with patch("api.services.wireguard._run", new_callable=AsyncMock, side_effect=RuntimeError("boom")):
                r = await c.get("/api/v1/interfaces")
                assert r.status_code == 500
        [record] = [r for r in caplog.records if r.getMessage() == "unhandled exception on GET /api/v1/interfaces"]
        assert record.exc_info is not None
        assert str(record.exc_info[1]) == "boom"


# ---------------------------------------------------------------------------
# Prefix
# ---------------------------------------------------------------------------


class TestPrefix:
    @pytest.mark.parametrize("path", ["/api/v1/docs", "/api/v1/redoc", "/api/v1/openapi.json"])
    async def test_docs_are_under_the_prefix(self, client, path):
        r = await client.get(path)
        assert r.status_code == 200

    @pytest.mark.parametrize("path", ["/", "/docs", "/redoc", "/openapi.json", "/health", "/interfaces"])
    async def test_nothing_is_served_outside_the_prefix(self, client, path):
        r = await client.get(path)
        assert r.status_code == 404

    async def test_openapi_paths_are_all_prefixed(self, client):
        paths = (await client.get("/api/v1/openapi.json")).json()["paths"]
        assert paths
        assert all(path.startswith("/api/v1") for path in paths)


async def test_sends_no_cors_headers(client):
    # Browsers must not call the agent directly: a backend or proxy holds the API key and calls it.
    r = await client.options(
        "/api/v1/interfaces", headers={"Origin": "https://ui.example", "Access-Control-Request-Method": "GET"}
    )
    assert "access-control-allow-origin" not in r.headers
