import asyncio
import contextlib
import logging
import os
import signal
from pathlib import Path

from api.config import Settings
from api.models import IFACE_NAME_PATTERN
from api.models.interfaces import Interface, InterfaceCreate, InterfaceUpdate
from api.models.peers import Peer, PeerCreate, PeerUpdate

logger = logging.getLogger("wg-agent")

# Not configurable: wg-quick always reads /etc/wireguard/<name>.conf, so the API must look there too.
CONFIG_DIR = Path("/etc/wireguard")
_CMD_TIMEOUT = 30
_KILL_GRACE = 5

SECRET_ARG = "<secret>"  # noqa: S105 - a placeholder, not a secret

# The API's own settings, the API key above all, stay out of the environment of wg,
# wg-quick and the PostUp/PostDown hooks that wg-quick runs.
_OWN_ENV = frozenset(name.upper() for name in Settings.model_fields)

# wg retries an unresolvable endpoint hostname 15 times, for boot before the network is up. Here that
# only turns a typo into a 504; the container environment can still set its own value.
_CMD_ENV_DEFAULTS = {"WG_ENDPOINT_RESOLUTION_RETRIES": "0"}

# wg's errors for a name with no running WireGuard interface: none by that name,
# or a link of another type (e.g. lo).
_NOT_RUNNING_ERRORS = ("No such device", "Not supported")

# wg-quick up/down/save on the same interface must not overlap: concurrent saves
# share a temporary file, and up/down race each other. Locks live in this process,
# so the API must run with a single worker.
_lifecycle_locks: dict[str, asyncio.Lock] = {}


class InterfaceNotFound(Exception):
    """No WireGuard interface is running with this name and it has no config file."""

    def __init__(self, name: str) -> None:
        super().__init__(f"Interface '{name}' not found")


class InterfaceNotRunning(Exception):
    """The interface has a config file but is down."""

    def __init__(self, name: str) -> None:
        super().__init__(f"Interface '{name}' is not running")


class InterfaceAlreadyRunning(Exception):
    """wg-quick up on an interface that is already up."""

    def __init__(self, name: str) -> None:
        super().__init__(f"Interface '{name}' is already running")


class InterfaceAlreadyExists(Exception):
    """Create with a name that already has a config file or a running interface."""

    def __init__(self, name: str) -> None:
        super().__init__(f"Interface '{name}' already exists")


class WireGuardError(Exception):
    """A wg or wg-quick command failed. The message is its error output."""


class WireGuardUnavailable(Exception):
    """wg or wg-quick cannot be used at all: not installed, or no CAP_NET_ADMIN."""


class WireGuardTimeout(Exception):
    """A wg or wg-quick command did not finish in time."""


async def _run(args: list[str], secret: str | None = None) -> tuple[str, str, int]:
    """Run a command without a shell. A secret is written to a pipe and passed to the
    command as a /dev/fd/N path wherever SECRET_ARG appears in args, so it never shows
    in the process list and never touches disk."""
    read_fd: int | None = None
    if secret is not None:
        read_fd, write_fd = os.pipe()
        try:
            os.write(write_fd, secret.encode())  # a key is 44 bytes, far below the pipe buffer
        finally:
            os.close(write_fd)
        args = [f"/dev/fd/{read_fd}" if arg == SECRET_ARG else arg for arg in args]
    logger.debug("exec: %s", args)
    try:
        # Not stdin: under uvloop, writing to the stdin of a command that reads
        # /dev/stdin itself (as wg does) fails with "the handler is closed".
        # A new session lets a timeout kill wg-quick together with its hooks.
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            pass_fds=(read_fd,) if read_fd is not None else (),
            start_new_session=True,
            env=_CMD_ENV_DEFAULTS | {k: v for k, v in os.environ.items() if k.upper() not in _OWN_ENV},
        )
    except OSError as exc:
        logger.error("cannot execute %s: %s", args[0], exc)
        raise WireGuardUnavailable(f"Cannot execute {args[0]}: {exc.strerror}") from exc
    finally:
        if read_fd is not None:
            os.close(read_fd)
    try:
        async with asyncio.timeout(_CMD_TIMEOUT):
            stdout, stderr = await proc.communicate()
    except TimeoutError:
        # SIGTERM first: wg-quick traps it to remove a half-created interface or its save temp file.
        with contextlib.suppress(ProcessLookupError):
            os.killpg(proc.pid, signal.SIGTERM)
        with contextlib.suppress(TimeoutError):
            async with asyncio.timeout(_KILL_GRACE):
                await proc.wait()
        with contextlib.suppress(ProcessLookupError):
            os.killpg(proc.pid, signal.SIGKILL)  # whatever is left, such as a hook that ignores SIGTERM
        await proc.wait()
        logger.error("cmd %s timed out after %ds", args, _CMD_TIMEOUT)
        raise WireGuardTimeout(f"{args[0]} did not finish within {_CMD_TIMEOUT}s") from None
    out = stdout.decode(errors="replace").strip()
    err = stderr.decode(errors="replace").strip()
    rc = proc.returncode or 0
    if rc != 0:
        # Not a warning yet: some failures are expected, like the health probe. _failure() warns.
        logger.debug("cmd %s failed (rc=%d): %s", args, rc, err)
    return out, err, rc


def _failure(args: list[str], err: str, rc: int) -> Exception:
    logger.warning("cmd %s failed (rc=%d): %s", args, rc, err)
    if "Operation not permitted" in err:  # wg without CAP_NET_ADMIN
        return WireGuardUnavailable(f"{err} (the API needs CAP_NET_ADMIN)")
    return WireGuardError(err or f"{args[0]} exited with status {rc}")


async def _check(args: list[str], secret: str | None = None) -> str:
    """Run a command and return its output, raising if it fails."""
    out, err, rc = await _run(args, secret=secret)
    if rc != 0:
        raise _failure(args, err, rc)
    return out


async def _show(name: str) -> list[str] | None:
    """Lines of `wg show <name> dump`, or None if no WireGuard interface by that name is running."""
    args = ["wg", "show", name, "dump"]
    out, err, rc = await _run(args)
    if rc == 0:
        return out.splitlines()
    if any(e in err for e in _NOT_RUNNING_ERRORS):
        return None
    raise _failure(args, err, rc)


async def _wg_set(name: str, args: list[str], secret: str | None = None) -> None:
    """Run `wg set <name> ...` on a running interface."""
    cmd = ["wg", "set", name, *args]
    _, err, rc = await _run(cmd, secret=secret)
    if rc == 0:
        return
    if any(e in err for e in _NOT_RUNNING_ERRORS):
        raise _not_running(name)
    raise _failure(cmd, err, rc)


def _not_running(name: str) -> Exception:
    """409 if wg-quick can bring the interface up, 404 if it does not exist at all."""
    return InterfaceNotRunning(name) if _conf_path(name).exists() else InterfaceNotFound(name)


def _conf_path(name: str) -> Path:
    # The name pattern allows no '/', so the path cannot leave the config directory.
    # The file itself may be a symlink, as wg-quick allows.
    if not IFACE_NAME_PATTERN.fullmatch(name):
        raise ValueError(f"Invalid interface name: {name}")
    return CONFIG_DIR / f"{name}.conf"


def _require_conf(name: str) -> None:
    if not _conf_path(name).exists():
        raise InterfaceNotFound(name)


async def has_access() -> bool:
    """Whether wg can query the kernel: the module is loaded and the API has CAP_NET_ADMIN."""
    try:
        # A valid name that never exists: wg answers "No such device" only when it can reach WireGuard.
        return await _show("wg-agent-probe") is None
    except WireGuardError, WireGuardUnavailable, WireGuardTimeout:
        return False


def _interface_from_dump(name: str, fields: list[str]) -> Interface:
    # fields: private-key, public-key, listen-port, fwmark
    _, public_key, listen_port, fwmark = fields[:4]
    return Interface(
        name=name,
        status="up",
        public_key=public_key if public_key != "(none)" else None,
        listen_port=(int(listen_port) or None) if listen_port.isdigit() else None,
        fwmark=fwmark if fwmark != "off" else None,
    )


async def list_interfaces() -> list[Interface]:
    interfaces: dict[str, Interface] = {}

    stdout = await _check(["wg", "show", "all", "dump"])
    for line in stdout.splitlines():
        parts = line.split("\t")
        if len(parts) == 5:
            interfaces[parts[0]] = _interface_from_dump(parts[0], parts[1:])
        elif len(parts) == 9 and parts[0] in interfaces:
            interfaces[parts[0]].num_peers += 1

    # shortcut: blocking listing of a small local dir; use asyncio.to_thread if it ever gets slow
    for conf_file in sorted(CONFIG_DIR.glob("*.conf")):  # noqa: ASYNC240
        name = conf_file.stem
        if name in interfaces:
            continue
        if not IFACE_NAME_PATTERN.fullmatch(name):
            logger.warning("skipping .conf with invalid interface name: %s", name)
            continue
        interfaces[name] = Interface(name=name, status="down")

    return list(interfaces.values())


async def get_interface(name: str) -> Interface | None:
    lines = await _show(name)
    if lines:
        iface = _interface_from_dump(name, lines[0].split("\t"))
        iface.num_peers = len(lines) - 1
        return iface

    if _conf_path(name).exists():
        return Interface(name=name, status="down")
    return None


async def update_interface(name: str, update: InterfaceUpdate) -> None:
    args: list[str] = []
    if update.private_key:
        args += ["private-key", SECRET_ARG]
    if update.listen_port is not None:
        args += ["listen-port", str(update.listen_port)]
    if update.fwmark is not None:
        args += ["fwmark", update.fwmark]
    if not args:  # `wg set <name>` alone only prints its usage; still answer 404/409 like any PATCH
        if await _show(name) is None:
            raise _not_running(name)
        return
    logger.info("updating interface %s", name)
    await _wg_set(name, args, secret=update.private_key)


async def _wg_quick(action: str, name: str) -> None:
    _require_conf(name)
    async with _lifecycle_locks.setdefault(name, asyncio.Lock()):
        running = await _show(name) is not None
        if action == "up" and running:
            raise InterfaceAlreadyRunning(name)
        if action in ("down", "save") and not running:
            raise InterfaceNotRunning(name)
        logger.info("wg-quick %s %s", action, name)
        await _check(["wg-quick", action, name])


async def create_interface(iface: InterfaceCreate) -> None:
    conf = _conf_path(iface.name)
    content = f"[Interface]\nAddress = {iface.address}\nPrivateKey = {iface.private_key}\n"
    if iface.listen_port is not None:
        content += f"ListenPort = {iface.listen_port}\n"
    async with _lifecycle_locks.setdefault(iface.name, asyncio.Lock()):
        if await _show(iface.name) is not None:
            raise InterfaceAlreadyExists(iface.name)
        try:
            fd = os.open(conf, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            raise InterfaceAlreadyExists(iface.name) from None
        with os.fdopen(fd, "w") as f:
            f.write(content)
        logger.info("creating interface %s", iface.name)
        try:
            await _check(["wg-quick", "up", iface.name])
        except BaseException:
            conf.unlink()  # leave nothing behind when the interface cannot come up
            raise


async def delete_interface(name: str) -> None:
    _require_conf(name)
    async with _lifecycle_locks.setdefault(name, asyncio.Lock()):
        if await _show(name) is not None:
            await _check(["wg-quick", "down", name])
        logger.info("deleting interface %s", name)
        _conf_path(name).unlink()


async def interface_up(name: str) -> None:
    await _wg_quick("up", name)


async def interface_down(name: str) -> None:
    await _wg_quick("down", name)


async def interface_save(name: str) -> None:
    await _wg_quick("save", name)


def _parse_peers_dump(lines: list[str]) -> list[Peer]:
    peers: list[Peer] = []
    for line in lines:
        parts = line.split("\t")
        if len(parts) < 8:
            continue
        try:
            peers.append(
                Peer(
                    # parts[1] is the preshared key: a secret, never read back.
                    public_key=parts[0],
                    endpoint=parts[2] if parts[2] != "(none)" else None,
                    allowed_ips=parts[3] if parts[3] != "(none)" else None,
                    latest_handshake=int(parts[4]) if parts[4] != "0" else None,
                    transfer_rx=int(parts[5]),
                    transfer_tx=int(parts[6]),
                    persistent_keepalive=int(parts[7]) if parts[7] != "off" else None,
                )
            )
        except ValueError, IndexError:
            logger.warning("skipping malformed peer dump line: %s", line)
    return peers


async def list_peers(iface: str) -> list[Peer]:
    lines = await _show(iface)
    if lines is None:
        raise _not_running(iface)
    return _parse_peers_dump(lines[1:])


async def get_peer(iface: str, public_key: str) -> Peer | None:
    peers = await list_peers(iface)
    return next((p for p in peers if p.public_key == public_key), None)


async def set_peer(iface: str, public_key: str, peer: PeerCreate | PeerUpdate) -> None:
    """Create or update a peer. Omitted fields are not changed."""
    args = ["peer", public_key]
    if peer.allowed_ips is not None:
        args += ["allowed-ips", peer.allowed_ips]
    if peer.endpoint:
        args += ["endpoint", peer.endpoint]
    if peer.preshared_key:
        args += ["preshared-key", SECRET_ARG]
    elif "preshared_key" in peer.model_fields_set:  # an explicit null removes it
        args += ["preshared-key", "/dev/null"]
    if peer.persistent_keepalive is not None:
        args += ["persistent-keepalive", str(peer.persistent_keepalive)]
    logger.info("setting peer %s on %s", public_key[:8], iface)
    await _wg_set(iface, args, secret=peer.preshared_key)


async def delete_peer(iface: str, public_key: str) -> None:
    logger.info("deleting peer %s from %s", public_key[:8], iface)
    await _wg_set(iface, ["peer", public_key, "remove"])
