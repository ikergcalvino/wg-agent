import asyncio
import os
import pathlib
import subprocess
import sys
from unittest.mock import AsyncMock, patch

import pytest

from api.exceptions import WireGuardTimeout
from api.services.wireguard import (
    _conf_path,
    _interface_from_dump,
    _peer_from_dump,
    _run,
    interface_save,
)
from tests.conftest import RUNNING_DUMP, VALID_KEY

# ---------------------------------------------------------------------------
# _run
# ---------------------------------------------------------------------------


class TestRun:
    async def test_secret_is_passed_through_a_pipe(self):
        out, _, rc = await _run(["cat", "/dev/stdin"], secret=VALID_KEY)
        assert (out, rc) == (VALID_KEY, 0)

    async def test_secret_never_appears_in_arguments(self):
        out, _, _ = await _run(["sh", "-c", 'echo "$0"', "/dev/stdin"], secret=VALID_KEY)
        assert out == "/dev/stdin"
        assert VALID_KEY not in out

    def test_secret_works_under_uvloop(self):
        # wg opens its key path, so stdin must be a pipe that can be reopened as /dev/stdin.
        code = f"""
import asyncio
import uvloop
from api.services.wireguard import _run
print(asyncio.run(_run(["cat", "/dev/stdin"], secret={VALID_KEY!r}), loop_factory=uvloop.new_event_loop))
"""
        result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=10, check=True)
        assert result.stdout.strip() == f"({VALID_KEY!r}, '', 0)"

    async def test_pipe_is_closed_after_the_command(self):
        before = set(pathlib.Path("/proc/self/fd").iterdir())
        await _run(["cat", "/dev/stdin"], secret=VALID_KEY)
        assert set(pathlib.Path("/proc/self/fd").iterdir()) == before

    async def test_own_settings_stay_out_of_the_command_environment(self, monkeypatch):
        # wg-quick runs PostUp/PostDown hooks with the environment it gets.
        monkeypatch.setenv("LOG_LEVEL", "DEBUG")
        out, _, rc = await _run(["env"])
        variables = dict(line.split("=", 1) for line in out.splitlines())
        assert rc == 0
        assert "API_KEY" not in variables
        assert "LOG_LEVEL" not in variables
        assert variables["PATH"] == os.environ["PATH"]

    async def test_endpoint_resolution_fails_fast(self, monkeypatch):
        # A hostname that does not resolve must fail at once, not retry past the command timeout.
        monkeypatch.delenv("WG_ENDPOINT_RESOLUTION_RETRIES", raising=False)
        out, _, _ = await _run(["env"])
        assert "WG_ENDPOINT_RESOLUTION_RETRIES=0" in out.splitlines()

    async def test_endpoint_resolution_retries_can_be_overridden(self, monkeypatch):
        monkeypatch.setenv("WG_ENDPOINT_RESOLUTION_RETRIES", "infinity")
        out, _, _ = await _run(["env"])
        assert "WG_ENDPOINT_RESOLUTION_RETRIES=infinity" in out.splitlines()

    async def test_command_does_not_inherit_stdin(self):
        out, _, rc = await _run(["cat"])
        assert (out, rc) == ("", 0)

    async def test_timeout_raises(self):
        with (
            patch("api.services.wireguard._CMD_TIMEOUT", 0.1),
            pytest.raises(WireGuardTimeout, match=r"sleep did not finish within 0\.1s"),
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

    async def test_timeout_lets_the_command_clean_up_first(self, tmp_path):
        # wg-quick up traps SIGTERM to delete the interface it was creating.
        marker = tmp_path / "cleaned"
        with patch("api.services.wireguard._CMD_TIMEOUT", 0.3), pytest.raises(WireGuardTimeout):
            await _run(["sh", "-c", f"trap 'touch {marker}; exit 1' TERM; sleep 30 & wait"])
        assert marker.exists()

    async def test_timeout_kills_a_command_that_ignores_sigterm(self):
        with (
            patch("api.services.wireguard._CMD_TIMEOUT", 0.2),
            patch("api.services.wireguard._KILL_GRACE", 0.2),
            pytest.raises(WireGuardTimeout),
        ):
            async with asyncio.timeout(5):
                await _run(["sh", "-c", "trap '' TERM; sleep 30"])


# ---------------------------------------------------------------------------
# _conf_path
# ---------------------------------------------------------------------------


class TestConfPath:
    def test_valid_name(self, tmp_path):
        with patch("api.services.wireguard.CONFIG_DIR", tmp_path):
            result = _conf_path("wg0")
            assert result == tmp_path / "wg0.conf"

    @pytest.mark.parametrize("name", ["../etc/passwd", "a/b", "/etc/passwd", "", "x" * 16])
    def test_invalid_names_rejected(self, tmp_path, name):
        with (
            patch("api.services.wireguard.CONFIG_DIR", tmp_path),
            pytest.raises(ValueError, match="Invalid interface name"),
        ):
            _conf_path(name)

    def test_dots_stay_inside_the_directory(self, tmp_path):
        with patch("api.services.wireguard.CONFIG_DIR", tmp_path):
            assert _conf_path("..").parent == tmp_path

    async def test_symlinked_conf_is_accepted(self, tmp_path):
        target = tmp_path / "elsewhere" / "wg0.conf"
        target.parent.mkdir()
        target.write_text("")
        (tmp_path / "confs").mkdir()
        (tmp_path / "confs" / "wg0.conf").symlink_to(target)
        with (
            patch("api.services.wireguard.CONFIG_DIR", tmp_path / "confs"),
            patch("api.services.wireguard._run", new_callable=AsyncMock) as mock_run,
        ):
            mock_run.side_effect = [(RUNNING_DUMP, "", 0), ("", "", 0), (RUNNING_DUMP, "", 0)]
            await interface_save("wg0")
        mock_run.assert_any_await(["wg-quick", "save", "wg0"], secret=None)


# ---------------------------------------------------------------------------
# _peer_from_dump
# ---------------------------------------------------------------------------


class TestPeerFromDump:
    def test_parses_fields(self):
        peer = _peer_from_dump(f"{VALID_KEY}\tPSK\t1.2.3.4:51820\t10.0.0.2/32\t1700000000\t1024\t2048\t25")
        assert peer.model_dump() == {
            "public_key": VALID_KEY,
            "endpoint": "1.2.3.4:51820",
            "allowed_ips": "10.0.0.2/32",
            "latest_handshake": 1700000000,
            "transfer_rx": 1024,
            "transfer_tx": 2048,
            "persistent_keepalive": 25,
        }

    def test_none_values(self):
        peer = _peer_from_dump(f"{VALID_KEY}\t(none)\t(none)\t(none)\t0\t0\t0\toff")
        assert (peer.endpoint, peer.allowed_ips, peer.latest_handshake, peer.persistent_keepalive) == (None,) * 4

    @pytest.mark.parametrize("line", ["too\tfew\tfields", f"{VALID_KEY}\t(none)\t(none)\t(none)\tBAD\t0\t0\toff"])
    def test_unexpected_output_fails_loudly(self, line):
        # wg writes the dump; if its format ever changes, an error beats silently dropping peers.
        with pytest.raises(ValueError, match=r"values to unpack|invalid literal"):
            _peer_from_dump(line)


# ---------------------------------------------------------------------------
# _interface_from_dump
# ---------------------------------------------------------------------------


class TestInterfaceFromDump:
    def test_parses_fields(self):
        peer = f"{VALID_KEY}\t(none)\t(none)\t10.0.0.2/32\t0\t0\t0\toff"
        interface = _interface_from_dump("wg0", [f"PRIVATE\t{VALID_KEY}\t51820\t0x1234", peer, peer])
        assert interface.num_peers == 2
        assert interface.name == "wg0"
        assert interface.status == "up"
        assert interface.public_key == VALID_KEY
        assert interface.listen_port == 51820
        assert interface.fwmark == "0x1234"

    def test_none_values(self):
        interface = _interface_from_dump("wg0", ["(none)\t(none)\t0\toff"])
        assert interface.num_peers == 0
        assert interface.public_key is None
        assert interface.listen_port is None
        assert interface.fwmark is None

    async def test_undecodable_output_is_replaced(self):
        out, _, rc = await _run(["printf", "\\377ok"])
        assert rc == 0
        assert out == "�ok"
