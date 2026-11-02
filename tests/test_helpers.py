import asyncio
import os
import pathlib
from unittest.mock import AsyncMock, patch

import pytest
import uvloop

from api.services.wireguard import (
    SECRET_ARG,
    WireGuardTimeout,
    _conf_path,
    _interface_from_dump,
    _parse_peers_dump,
    _run,
    interface_save,
)
from tests.conftest import RUNNING_DUMP, VALID_KEY

# ---------------------------------------------------------------------------
# _run
# ---------------------------------------------------------------------------


class TestRun:
    async def test_secret_is_passed_through_a_pipe(self):
        out, _, rc = await _run(["cat", SECRET_ARG], secret=VALID_KEY)
        assert (out, rc) == (VALID_KEY, 0)

    async def test_secret_never_appears_in_arguments(self):
        out, _, _ = await _run(["sh", "-c", 'echo "$0"', SECRET_ARG], secret=VALID_KEY)
        assert out.startswith("/dev/fd/")
        assert VALID_KEY not in out

    async def test_secret_works_under_uvloop(self):
        # uvicorn runs the app on uvloop, where passing secrets through stdin broke.
        def run_on_uvloop():
            return asyncio.run(_run(["cat", SECRET_ARG], secret=VALID_KEY), loop_factory=uvloop.new_event_loop)

        out, _, rc = await asyncio.to_thread(run_on_uvloop)
        assert (out, rc) == (VALID_KEY, 0)

    async def test_pipe_is_closed_after_the_command(self):
        before = set(os.listdir("/proc/self/fd"))
        await _run(["cat", SECRET_ARG], secret=VALID_KEY)
        assert set(os.listdir("/proc/self/fd")) == before

    async def test_command_does_not_inherit_stdin(self):
        out, _, rc = await _run(["cat"])
        assert (out, rc) == ("", 0)

    async def test_timeout_raises(self):
        with (
            patch("api.services.wireguard._CMD_TIMEOUT", 0.1),
            pytest.raises(WireGuardTimeout, match="sleep did not finish within 0.1s"),
        ):
            await _run(["sleep", "10"])

    async def test_timeout_kills_child_processes_too(self, tmp_path):
        # wg-quick runs hooks as child processes; a timeout must not leave them behind.
        pid_file = tmp_path / "child.pid"
        with (
            patch("api.services.wireguard._CMD_TIMEOUT", 0.3),
            pytest.raises(WireGuardTimeout),
        ):
            await _run(["sh", "-c", f"sleep 30 & echo $! > {pid_file}; wait"])
        child = int(pid_file.read_text())
        await asyncio.sleep(0.1)
        status = pathlib.Path(f"/proc/{child}/stat")
        assert not status.exists() or status.read_text().split()[2] == "Z"


# ---------------------------------------------------------------------------
# _conf_path
# ---------------------------------------------------------------------------


class TestConfPath:
    def test_valid_name(self, tmp_path):
        with patch("api.services.wireguard.WG_CONFIG_DIR", tmp_path):
            result = _conf_path("wg0")
            assert result == tmp_path / "wg0.conf"

    @pytest.mark.parametrize("name", ["../etc/passwd", "a/b", "/etc/passwd", "", "x" * 16])
    def test_invalid_names_rejected(self, tmp_path, name):
        with (
            patch("api.services.wireguard.WG_CONFIG_DIR", tmp_path),
            pytest.raises(ValueError, match="Invalid interface name"),
        ):
            _conf_path(name)

    def test_dots_stay_inside_the_directory(self, tmp_path):
        with patch("api.services.wireguard.WG_CONFIG_DIR", tmp_path):
            assert _conf_path("..").parent == tmp_path

    async def test_symlinked_conf_is_accepted(self, tmp_path):
        target = tmp_path / "elsewhere" / "wg0.conf"
        target.parent.mkdir()
        target.write_text("")
        (tmp_path / "confs").mkdir()
        (tmp_path / "confs" / "wg0.conf").symlink_to(target)
        with (
            patch("api.services.wireguard.WG_CONFIG_DIR", tmp_path / "confs"),
            patch("api.services.wireguard._run", new_callable=AsyncMock) as mock_run,
        ):
            mock_run.side_effect = [(RUNNING_DUMP, "", 0), ("", "", 0)]
            await interface_save("wg0")
        mock_run.assert_awaited_with(["wg-quick", "save", "wg0"], secret=None)


# ---------------------------------------------------------------------------
# _parse_peers_dump
# ---------------------------------------------------------------------------


class TestParsePeersDump:
    def test_parses_peer_line(self):
        line = f"{VALID_KEY}\t(none)\t1.2.3.4:51820\t10.0.0.2/32\t1700000000\t1024\t2048\toff"
        peers = _parse_peers_dump([line])
        assert len(peers) == 1
        assert peers[0].public_key == VALID_KEY
        assert peers[0].endpoint == "1.2.3.4:51820"
        assert peers[0].persistent_keepalive is None

    def test_parses_multiple_peers(self):
        lines = [
            f"{VALID_KEY}\t(none)\t1.2.3.4:51820\t10.0.0.2/32\t0\t0\t0\toff",
            f"{VALID_KEY}\t(none)\t5.6.7.8:51820\t10.0.0.3/32\t0\t0\t0\t25",
        ]
        peers = _parse_peers_dump(lines)
        assert len(peers) == 2
        assert peers[1].persistent_keepalive == 25

    def test_skips_short_lines(self):
        peers = _parse_peers_dump(["too\tfew\tfields"])
        assert peers == []

    def test_empty_input(self):
        assert _parse_peers_dump([]) == []

    def test_none_values(self):
        line = f"{VALID_KEY}\t(none)\t(none)\t(none)\t0\t0\t0\toff"
        peers = _parse_peers_dump([line])
        assert peers[0].endpoint is None
        assert peers[0].allowed_ips is None
        assert peers[0].latest_handshake is None

    def test_malformed_line_skipped(self):
        line = f"{VALID_KEY}\t(none)\t(none)\t(none)\tBAD\tBAD\tBAD\toff"
        peers = _parse_peers_dump([line])
        assert peers == []


# ---------------------------------------------------------------------------
# _interface_from_dump
# ---------------------------------------------------------------------------


class TestInterfaceFromDump:
    def test_parses_fields(self):
        iface = _interface_from_dump("wg0", ["PRIVATE", VALID_KEY, "51820", "0x1234"])
        assert iface.name == "wg0"
        assert iface.status == "up"
        assert iface.public_key == VALID_KEY
        assert iface.listen_port == 51820
        assert iface.fw_mark == "0x1234"

    def test_none_values(self):
        iface = _interface_from_dump("wg0", ["(none)", "(none)", "0", "off"])
        assert iface.public_key is None
        assert iface.listen_port is None
        assert iface.fw_mark is None

    async def test_undecodable_output_is_replaced(self):
        out, err, rc = await _run(["printf", "\\377ok"])
        assert rc == 0
        assert out == "�ok"
