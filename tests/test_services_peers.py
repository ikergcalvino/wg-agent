from unittest.mock import AsyncMock, patch

import pytest

from api.models.peers import PeerCreate, PeerUpdate
from api.services.wireguard import (
    InterfaceNotFound,
    InterfaceNotRunning,
    WireGuardError,
    delete_peer,
    get_peer,
    list_peers,
    set_peer,
)
from tests.conftest import NOT_RUNNING, VALID_KEY

# ---------------------------------------------------------------------------
# list_peers
# ---------------------------------------------------------------------------


class TestListPeers:
    async def test_returns_peers(self):
        dump = f"PRIVATE\tPUBLIC\t51820\toff\n{VALID_KEY}\t(none)\t1.2.3.4:51820\t10.0.0.2/32\t0\t0\t0\toff"
        with patch("api.services.wireguard._run", new_callable=AsyncMock, return_value=(dump, "", 0)):
            peers = await list_peers("wg0")
            assert peers is not None
            assert len(peers) == 1

    async def test_down_interface_with_conf(self, tmp_path):
        (tmp_path / "wg0.conf").write_text(f"[Interface]\n\n[Peer]\nPublicKey = {VALID_KEY}\n")
        with (
            patch("api.services.wireguard._run", new_callable=AsyncMock, return_value=("", NOT_RUNNING, 1)),
            pytest.raises(InterfaceNotRunning),
        ):
            await list_peers("wg0")

    async def test_unknown_interface(self):
        with (
            patch("api.services.wireguard._run", new_callable=AsyncMock, return_value=("", NOT_RUNNING, 1)),
            pytest.raises(InterfaceNotFound),
        ):
            await list_peers("wg0")


# ---------------------------------------------------------------------------
# get_peer
# ---------------------------------------------------------------------------


class TestGetPeer:
    async def test_returns_peer(self):
        dump = f"PRIVATE\tPUBLIC\t51820\toff\n{VALID_KEY}\t(none)\t1.2.3.4:51820\t10.0.0.2/32\t0\t0\t0\toff"
        with patch("api.services.wireguard._run", new_callable=AsyncMock, return_value=(dump, "", 0)):
            peer = await get_peer("wg0", VALID_KEY)
            assert peer is not None
            assert peer.public_key == VALID_KEY

    async def test_returns_none_when_not_found(self):
        dump = "PRIVATE\tPUBLIC\t51820\toff"
        with patch("api.services.wireguard._run", new_callable=AsyncMock, return_value=(dump, "", 0)):
            assert await get_peer("wg0", VALID_KEY) is None

    async def test_unknown_interface_raises(self):
        with (
            patch("api.services.wireguard._run", new_callable=AsyncMock, return_value=("", NOT_RUNNING, 1)),
            pytest.raises(InterfaceNotFound),
        ):
            await get_peer("wg0", VALID_KEY)


# ---------------------------------------------------------------------------
# set_peer
# ---------------------------------------------------------------------------


class TestSetPeer:
    async def test_success(self):
        with patch("api.services.wireguard._run", new_callable=AsyncMock, return_value=("", "", 0)) as mock_run:
            assert await set_peer("wg0", VALID_KEY, PeerUpdate(allowed_ips="10.0.0.2/32")) is None
            mock_run.assert_awaited_once_with(
                ["wg", "set", "wg0", "peer", VALID_KEY, "allowed-ips", "10.0.0.2/32"], secret=None
            )

    async def test_with_all_options(self):
        with patch("api.services.wireguard._run", new_callable=AsyncMock, return_value=("", "", 0)) as mock_run:
            await set_peer(
                "wg0",
                VALID_KEY,
                PeerCreate(
                    public_key=VALID_KEY,
                    allowed_ips="10.0.0.2/32",
                    endpoint="1.2.3.4:51820",
                    preshared_key=VALID_KEY,
                    persistent_keepalive=25,
                ),
            )
            args = mock_run.call_args_list[0][0][0]
            assert "allowed-ips" in args
            assert "endpoint" in args
            assert "preshared-key" in args
            assert "persistent-keepalive" in args
            assert mock_run.call_args_list[0][1]["secret"] == VALID_KEY

    async def test_null_preshared_key_removes_it(self):
        with patch("api.services.wireguard._run", new_callable=AsyncMock, return_value=("", "", 0)) as mock_run:
            await set_peer("wg0", VALID_KEY, PeerUpdate(preshared_key=None))
            mock_run.assert_awaited_once_with(
                ["wg", "set", "wg0", "peer", VALID_KEY, "preshared-key", "/dev/null"], secret=None
            )

    async def test_omitted_preshared_key_is_left_unchanged(self):
        with patch("api.services.wireguard._run", new_callable=AsyncMock, return_value=("", "", 0)) as mock_run:
            await set_peer("wg0", VALID_KEY, PeerUpdate(persistent_keepalive=0))
            assert "preshared-key" not in mock_run.call_args[0][0]

    async def test_returns_wg_error(self):
        with (
            patch("api.services.wireguard._run", new_callable=AsyncMock, return_value=("", "error", 1)),
            pytest.raises(WireGuardError, match="error"),
        ):
            await set_peer("wg0", VALID_KEY, PeerUpdate(allowed_ips="10.0.0.2/32"))


# ---------------------------------------------------------------------------
# delete_peer
# ---------------------------------------------------------------------------


class TestDeletePeer:
    async def test_success(self):
        with patch("api.services.wireguard._run", new_callable=AsyncMock, return_value=("", "", 0)) as mock_run:
            assert await delete_peer("wg0", VALID_KEY) is None
            mock_run.assert_awaited_once_with(["wg", "set", "wg0", "peer", VALID_KEY, "remove"], secret=None)

    async def test_returns_wg_error(self):
        with (
            patch("api.services.wireguard._run", new_callable=AsyncMock, return_value=("", "error", 1)),
            pytest.raises(WireGuardError, match="error"),
        ):
            await delete_peer("wg0", VALID_KEY)
