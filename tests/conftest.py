import os
from unittest.mock import patch

import pytest
from httpx2 import ASGITransport, AsyncClient

from api.main import app
from api.services.wireguard import _lifecycle_locks
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


@pytest.fixture(autouse=True)
def isolated_config_dir(tmp_path):
    # Never look at the real /etc/wireguard; tests that need .conf files create them in tmp_path.
    with patch("api.services.wireguard.CONFIG_DIR", tmp_path):
        yield tmp_path


@pytest.fixture(autouse=True)
def reset_lifecycle_locks():
    # asyncio locks are bound to the event loop that first uses them, and every test runs its own loop.
    yield
    _lifecycle_locks.clear()
