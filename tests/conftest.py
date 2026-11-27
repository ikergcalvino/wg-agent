import os
from unittest.mock import AsyncMock, patch

import pytest
from httpx2 import ASGITransport, AsyncClient

from api.main import app
from tests import TEST_API_KEY

# The integration tests need a running API and real WireGuard: tests/integration/run.sh sets WG_API_URL.
collect_ignore = [] if "WG_API_URL" in os.environ else ["integration"]

VALID_KEY = "YWJjZGVmZ2hpamtsbW5vcHFyc3R1dnd4eXoxMjM0NTY="

# What wg prints for a name with no running WireGuard interface.
NOT_RUNNING = "Unable to access interface: No such device"
# First line of `wg show <name> dump` for a running interface.
RUNNING_DUMP = f"PRIVATE\t{VALID_KEY}\t51820\toff"


@pytest.fixture
async def client():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test", headers={"X-API-Key": TEST_API_KEY}
    ) as ac:
        yield ac


@pytest.fixture
def healthy_host(tmp_path):
    """A host with wg, wg-quick, CAP_NET_ADMIN and the WireGuard module; tests can take pieces away."""
    status, module = tmp_path / "status", tmp_path / "wireguard"
    status.write_text("Name:\tpython\nCapEff:\t0000000000001000\nCapBnd:\t0000000000000000\n")
    module.mkdir()
    with (
        patch("api.services.health.PROC_STATUS", status),
        patch("api.services.health.WIREGUARD_MODULE", module),
        patch("api.services.health.shutil.which", side_effect=lambda tool: f"/usr/bin/{tool}") as which,
    ):
        yield status, module, which


@pytest.fixture(autouse=True)
def no_addresses():
    """Interfaces have no addresses unless a test says otherwise, so mocks of _run need no ip call."""
    with patch("api.services.wireguard._addresses", new_callable=AsyncMock, return_value={}) as addresses:
        yield addresses


@pytest.fixture(autouse=True)
def isolated_config_dir(tmp_path):
    # Never look at the real /etc/wireguard; tests that need .conf files create them in tmp_path.
    with patch("api.services.wireguard.CONFIG_DIR", tmp_path):
        yield tmp_path
