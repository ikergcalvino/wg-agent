from unittest.mock import AsyncMock, call, patch

import pytest

from api.exceptions import (
    InterfaceAlreadyExists,
    InterfaceAlreadyRunning,
    InterfaceNotFound,
    InterfaceNotRunning,
    WireGuardError,
    WireGuardUnavailable,
)
from api.models.interfaces import InterfaceCreate, InterfaceUpdate
from api.services.wireguard import (
    SECRET_ARG,
    create_interface,
    delete_interface,
    get_interface,
    interface_down,
    interface_save,
    interface_up,
    list_interfaces,
    update_interface,
)
from tests.conftest import NOT_RUNNING, RUNNING_DUMP, VALID_KEY

# ---------------------------------------------------------------------------
# list_interfaces (wg show all dump)
# ---------------------------------------------------------------------------


class TestListInterfaces:
    @pytest.fixture
    def mock_wg(self, tmp_path):
        with (
            patch("api.services.wireguard._run", new_callable=AsyncMock) as mock_run,
            patch("api.services.wireguard.CONFIG_DIR", tmp_path),
        ):
            yield mock_run, tmp_path

    async def test_single_interface_no_peers(self, mock_wg):
        mock_run, _ = mock_wg
        mock_run.return_value = (f"wg0\tPRIVATE\t{VALID_KEY}\t51820\toff", "", 0)

        result = await list_interfaces()
        assert len(result) == 1
        assert result[0].name == "wg0"
        assert result[0].public_key == VALID_KEY
        assert result[0].listen_port == 51820
        assert result[0].num_peers == 0
        assert result[0].status == "up"

    async def test_interface_with_peers(self, mock_wg):
        mock_run, _ = mock_wg
        dump = (
            f"wg0\tPRIVATE\t{VALID_KEY}\t51820\toff\nwg0\t{VALID_KEY}\t(none)\t1.2.3.4:51820\t10.0.0.2/32\t0\t0\t0\toff"
        )
        mock_run.return_value = (dump, "", 0)

        result = await list_interfaces()
        assert result[0].num_peers == 1
        assert result[0].status == "up"

    async def test_peers_are_counted_per_interface(self, mock_wg):
        mock_run, _ = mock_wg
        peer = f"{VALID_KEY}\t(none)\t(none)\t10.0.0.2/32\t0\t0\t0\toff"
        dump = "\n".join(
            [
                f"wg0\tPRIVATE\t{VALID_KEY}\t51820\toff",
                f"wg0\t{peer}",
                f"wg0\t{peer}",
                f"wg1\tPRIVATE\t{VALID_KEY}\t51821\toff",
            ]
        )
        mock_run.return_value = (dump, "", 0)

        result = await list_interfaces()
        assert {i.name: i.num_peers for i in result} == {"wg0": 2, "wg1": 0}

    async def test_running_interface_without_conf_is_listed(self, mock_wg):
        mock_run, _ = mock_wg
        mock_run.return_value = (f"wg0\tPRIVATE\t{VALID_KEY}\t51820\toff", "", 0)

        result = await list_interfaces()
        assert [i.name for i in result] == ["wg0"]

    async def test_down_interfaces_listed_by_name_only(self, mock_wg):
        mock_run, tmp_path = mock_wg
        mock_run.return_value = ("", "", 0)
        (tmp_path / "wg0.conf").write_text("[Interface]\nListenPort = 51820\n")

        result = await list_interfaces()
        assert len(result) == 1
        assert result[0].name == "wg0"
        assert result[0].status == "down"
        assert result[0].listen_port is None
        assert result[0].num_peers is None  # unknown: the .conf is never read

    async def test_conf_contents_are_not_read(self, mock_wg):
        mock_run, tmp_path = mock_wg
        mock_run.return_value = ("", "", 0)
        (tmp_path / "wg0.conf").write_text("garbage that is not a WireGuard config")

        result = await list_interfaces()
        assert result[0].name == "wg0"

    async def test_shows_both_up_and_down(self, mock_wg):
        mock_run, tmp_path = mock_wg
        mock_run.return_value = (f"wg0\tPRIVATE\t{VALID_KEY}\t51820\toff", "", 0)
        (tmp_path / "wg0.conf").write_text("")
        (tmp_path / "wg1.conf").write_text("")

        result = await list_interfaces()
        assert {r.name: r.status for r in result} == {"wg0": "up", "wg1": "down"}

    async def test_interface_created_outside_wg_quick(self, mock_wg):
        mock_run, _ = mock_wg
        mock_run.return_value = (f"vpn#1\tPRIVATE\t{VALID_KEY}\t51820\toff", "", 0)
        assert [i.name for i in await list_interfaces()] == ["vpn#1"]

    async def test_empty_when_no_interfaces(self, mock_wg):
        mock_run, _ = mock_wg
        mock_run.return_value = ("", "", 0)
        assert await list_interfaces() == []

    async def test_raises_when_wg_fails(self, mock_wg):
        mock_run, tmp_path = mock_wg
        (tmp_path / "wg0.conf").write_text("")
        mock_run.return_value = ("", "Unable to access interface: Protocol not supported", 1)
        with pytest.raises(WireGuardError, match="Protocol not supported"):
            await list_interfaces()

    async def test_permission_error_is_unavailable(self, mock_wg):
        mock_run, _ = mock_wg
        mock_run.return_value = ("", "Unable to access interface: Operation not permitted", 1)
        with pytest.raises(WireGuardUnavailable, match="CAP_NET_ADMIN"):
            await list_interfaces()

    async def test_skips_invalid_conf_names(self, mock_wg):
        mock_run, tmp_path = mock_wg
        mock_run.return_value = ("", "", 0)
        (tmp_path / "wg0.conf").write_text("")
        (tmp_path / "inv@lid.conf").write_text("")
        result = await list_interfaces()
        assert [i.name for i in result] == ["wg0"]


# ---------------------------------------------------------------------------
# get_interface
# ---------------------------------------------------------------------------


class TestGetInterface:
    async def test_returns_running_interface(self, tmp_path):
        dump = f"PRIVATE\t{VALID_KEY}\t51820\toff\n{VALID_KEY}\t(none)\t(none)\t10.0.0.2/32\t0\t0\t0\toff"
        with (
            patch("api.services.wireguard._run", new_callable=AsyncMock, return_value=(dump, "", 0)),
            patch("api.services.wireguard.CONFIG_DIR", tmp_path),
        ):
            result = await get_interface("wg0")
            assert result is not None
            assert result.name == "wg0"
            assert result.public_key == VALID_KEY
            assert result.listen_port == 51820
            assert result.num_peers == 1
            assert result.status == "up"

    async def test_returns_down_interface_when_conf_exists(self, tmp_path):
        (tmp_path / "wg0.conf").write_text("[Interface]\nListenPort = 1111\n")
        with (
            patch("api.services.wireguard._run", new_callable=AsyncMock, return_value=("", NOT_RUNNING, 1)),
            patch("api.services.wireguard.CONFIG_DIR", tmp_path),
        ):
            result = await get_interface("wg0")
            assert result is not None
            assert result.status == "down"
            assert result.listen_port is None
            assert result.num_peers is None

    async def test_not_running_and_no_conf_is_not_found(self, tmp_path):
        with (
            patch("api.services.wireguard._run", new_callable=AsyncMock, return_value=("", NOT_RUNNING, 1)),
            patch("api.services.wireguard.CONFIG_DIR", tmp_path),
            pytest.raises(InterfaceNotFound),
        ):
            await get_interface("wg0")


# ---------------------------------------------------------------------------
# update_interface (wg set)
# ---------------------------------------------------------------------------


class TestUpdateInterface:
    async def test_sets_all_fields(self):
        update = InterfaceUpdate(private_key=VALID_KEY, listen_port=51821, fwmark="0x10")
        with patch("api.services.wireguard._run", new_callable=AsyncMock) as mock_run:
            mock_run.side_effect = [("", "", 0), (RUNNING_DUMP, "", 0)]
            interface = await update_interface("wg0", update)
        assert interface.name == "wg0"
        assert mock_run.await_args_list == [
            call(
                ["wg", "set", "wg0", "private-key", SECRET_ARG, "listen-port", "51821", "fwmark", "0x10"],
                secret=VALID_KEY,
            ),
            call(["wg", "show", "wg0", "dump"]),
        ]

    async def test_omitted_fields_are_left_unchanged(self):
        with patch("api.services.wireguard._run", new_callable=AsyncMock) as mock_run:
            mock_run.side_effect = [("", "", 0), (RUNNING_DUMP, "", 0)]
            await update_interface("wg0", InterfaceUpdate(listen_port=51821))
        assert mock_run.await_args_list[0] == call(["wg", "set", "wg0", "listen-port", "51821"], secret=None)

    async def test_does_not_write_files(self, tmp_path):
        with (
            patch("api.services.wireguard._run", new_callable=AsyncMock) as mock_run,
            patch("api.services.wireguard.CONFIG_DIR", tmp_path),
        ):
            mock_run.side_effect = [("", "", 0), (RUNNING_DUMP, "", 0)]
            await update_interface("wg0", InterfaceUpdate(private_key=VALID_KEY))
        assert list(tmp_path.iterdir()) == []

    async def test_returns_wg_error(self):
        with (
            patch("api.services.wireguard._run", new_callable=AsyncMock, return_value=("", "Invalid fwmark", 1)),
            pytest.raises(WireGuardError, match="Invalid fwmark"),
        ):
            await update_interface("wg0", InterfaceUpdate(listen_port=51821))

    async def test_down_interface_with_conf(self, tmp_path):
        (tmp_path / "wg0.conf").write_text("")
        with (
            patch("api.services.wireguard._run", new_callable=AsyncMock, return_value=("", NOT_RUNNING, 1)),
            pytest.raises(InterfaceNotRunning),
        ):
            await update_interface("wg0", InterfaceUpdate(listen_port=51821))

    async def test_unknown_interface(self):
        with (
            patch("api.services.wireguard._run", new_callable=AsyncMock, return_value=("", NOT_RUNNING, 1)),
            pytest.raises(InterfaceNotFound),
        ):
            await update_interface("wg0", InterfaceUpdate(listen_port=51821))


# ---------------------------------------------------------------------------
# Lifecycle (wg-quick)
# ---------------------------------------------------------------------------


class TestLifecycle:
    @pytest.mark.parametrize(
        ("func", "action"),
        [(interface_up, "up"), (interface_down, "down"), (interface_save, "save")],
    )
    async def test_runs_wg_quick(self, tmp_path, func, action):
        (tmp_path / "wg0.conf").write_text("")
        show = ("", NOT_RUNNING, 1) if action == "up" else (RUNNING_DUMP, "", 0)
        with patch("api.services.wireguard._run", new_callable=AsyncMock) as mock_run:
            after = ("", NOT_RUNNING, 1) if action == "down" else (RUNNING_DUMP, "", 0)
            mock_run.side_effect = [show, ("", "", 0), after]
            interface = await func("wg0")
        assert interface.status == ("down" if action == "down" else "up")
        assert mock_run.await_args_list == [
            call(["wg", "show", "wg0", "dump"]),
            call(["wg-quick", action, "wg0"], secret=None),
            call(["wg", "show", "wg0", "dump"]),
        ]

    async def test_up_when_running_is_refused(self, tmp_path):
        (tmp_path / "wg0.conf").write_text("")
        with (
            patch("api.services.wireguard._run", new_callable=AsyncMock, return_value=(RUNNING_DUMP, "", 0)),
            pytest.raises(InterfaceAlreadyRunning),
        ):
            await interface_up("wg0")

    @pytest.mark.parametrize("func", [interface_down, interface_save])
    async def test_down_or_save_when_not_running_is_refused(self, tmp_path, func):
        (tmp_path / "wg0.conf").write_text("")
        with (
            patch("api.services.wireguard._run", new_callable=AsyncMock, return_value=("", NOT_RUNNING, 1)),
            pytest.raises(InterfaceNotRunning),
        ):
            await func("wg0")

    @pytest.mark.parametrize("func", [interface_up, interface_down, interface_save])
    async def test_requires_conf(self, tmp_path, func):
        with (
            patch("api.services.wireguard._run", new_callable=AsyncMock) as mock_run,
            patch("api.services.wireguard.CONFIG_DIR", tmp_path),
            pytest.raises(InterfaceNotFound),
        ):
            await func("wg0")
        mock_run.assert_not_awaited()


# ---------------------------------------------------------------------------
# create_interface / delete_interface
# ---------------------------------------------------------------------------


class TestCreateInterface:
    NEW = InterfaceCreate(name="wg0", address="10.0.0.1/24", private_key=VALID_KEY, listen_port=51820)

    async def test_writes_a_private_conf_and_brings_it_up(self, tmp_path):
        with patch("api.services.wireguard._run", new_callable=AsyncMock) as mock_run:
            mock_run.side_effect = [("", NOT_RUNNING, 1), ("", "", 0), (RUNNING_DUMP, "", 0)]
            assert (await create_interface(self.NEW)).status == "up"
        conf = tmp_path / "wg0.conf"
        assert conf.read_text() == f"[Interface]\nAddress = 10.0.0.1/24\nPrivateKey = {VALID_KEY}\nListenPort = 51820\n"
        assert conf.stat().st_mode & 0o777 == 0o600
        assert mock_run.await_args_list[1] == call(["wg-quick", "up", "wg0"], secret=None)

    async def test_existing_conf_is_never_overwritten(self, tmp_path):
        (tmp_path / "wg0.conf").write_text("mine")
        with (
            patch("api.services.wireguard._run", new_callable=AsyncMock, return_value=("", NOT_RUNNING, 1)),
            pytest.raises(InterfaceAlreadyExists),
        ):
            await create_interface(self.NEW)
        assert (tmp_path / "wg0.conf").read_text() == "mine"

    async def test_running_interface_without_conf_is_a_conflict(self, tmp_path):
        with (
            patch("api.services.wireguard._run", new_callable=AsyncMock, return_value=(RUNNING_DUMP, "", 0)),
            pytest.raises(InterfaceAlreadyExists),
        ):
            await create_interface(self.NEW)
        assert not (tmp_path / "wg0.conf").exists()

    async def test_failed_up_leaves_no_conf(self, tmp_path):
        with patch("api.services.wireguard._run", new_callable=AsyncMock) as mock_run:
            mock_run.side_effect = [("", NOT_RUNNING, 1), ("", "RTNETLINK answers: Operation not supported", 1)]
            with pytest.raises(WireGuardError):
                await create_interface(self.NEW)
        assert not (tmp_path / "wg0.conf").exists()


class TestDeleteInterface:
    async def test_running_interface_is_brought_down_first(self, tmp_path):
        (tmp_path / "wg0.conf").write_text("")
        with patch("api.services.wireguard._run", new_callable=AsyncMock) as mock_run:
            mock_run.side_effect = [(RUNNING_DUMP, "", 0), ("", "", 0)]
            await delete_interface("wg0")
        assert mock_run.await_args_list[-1] == call(["wg-quick", "down", "wg0"], secret=None)
        assert not (tmp_path / "wg0.conf").exists()

    async def test_down_interface_only_loses_its_conf(self, tmp_path):
        (tmp_path / "wg0.conf").write_text("")
        with patch(
            "api.services.wireguard._run", new_callable=AsyncMock, return_value=("", NOT_RUNNING, 1)
        ) as mock_run:
            await delete_interface("wg0")
        assert mock_run.await_count == 1  # only the state check, no wg-quick down
        assert not (tmp_path / "wg0.conf").exists()

    async def test_unknown_interface(self):
        with pytest.raises(InterfaceNotFound):
            await delete_interface("wg0")
