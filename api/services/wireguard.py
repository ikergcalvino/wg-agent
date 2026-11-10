import asyncio
import contextlib
import logging
import os
import shutil
import signal
from pathlib import Path

from api.config import Settings
from api.exceptions import (
    InterfaceAlreadyExists,
    InterfaceAlreadyRunning,
    InterfaceNotFound,
    InterfaceNotRunning,
    PeerAlreadyExists,
    PeerNotFound,
    WireGuardError,
    WireGuardTimeout,
    WireGuardUnavailable,
)
from api.models.interfaces import Interface, InterfaceCreate, InterfaceUpdate
from api.models.peers import Peer, PeerCreate, PeerUpdate
from api.types import INTERFACE_NAME_PATTERN

logger = logging.getLogger("wg-agent")

# Not configurable: wg-quick always reads /etc/wireguard/<name>.conf, so the API must look there too.
CONFIG_DIR = Path("/etc/wireguard")
# What the health check reads: the process's capabilities, and the kernel module's sysfs entry.
PROC_STATUS = Path("/proc/self/status")
WIREGUARD_MODULE = Path("/sys/module/wireguard")
_CAP_NET_ADMIN = 12  # bit number, from linux/capability.h
_CMD_TIMEOUT = 30
_KILL_GRACE = 5

# The API's own settings, the API key above all, stay out of the environment of wg,
# wg-quick and the PostUp/PostDown hooks that wg-quick runs.
_OWN_ENV = frozenset(name.upper() for name in Settings.model_fields)

# wg retries an unresolvable endpoint hostname 15 times, for boot before the network is up. Here that
# only turns a typo into a 504; the container environment can still set its own value.
_CMD_ENV_DEFAULTS = {"WG_ENDPOINT_RESOLUTION_RETRIES": "0"}

# wg's errors for a name with no running WireGuard interface: none by that name,
# or a link of another type (e.g. lo).
_NOT_RUNNING_ERRORS = ("No such device", "Not supported")


async def _run(args: list[str], secret: str | None = None) -> tuple[str, str, int]:
    """Run a command without a shell. A secret is written to a pipe and passed as stdin,
    so it never appears in the process list or touches disk."""
    read_fd: int | None = None
    if secret is not None:
        read_fd, write_fd = os.pipe()
        try:
            os.write(write_fd, secret.encode())  # a key is 44 bytes, far below the pipe buffer
        finally:
            os.close(write_fd)
        # wg set expects a path and opens it. Use an OS pipe directly: uvloop's stdin=PIPE
        # is a socket, which cannot be reopened via /dev/stdin.
    logger.debug("exec: %s", args)
    try:
        # A new session lets a timeout kill wg-quick together with its hooks.
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdin=read_fd if read_fd is not None else asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
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
    if not INTERFACE_NAME_PATTERN.fullmatch(name):
        raise ValueError(f"Invalid interface name: {name}")
    return CONFIG_DIR / f"{name}.conf"


def _require_conf(name: str) -> None:
    if not _conf_path(name).exists():
        raise InterfaceNotFound(name)


def health_errors() -> list[str]:
    """What keeps the agent from managing WireGuard on this host, without running any command."""
    errors = [f"{tool} is not installed" for tool in ("wg", "wg-quick") if shutil.which(tool) is None]
    if not _has_net_admin():
        errors.append("the agent lacks CAP_NET_ADMIN")
    if not WIREGUARD_MODULE.exists():
        errors.append("the WireGuard kernel module is not loaded")
    return errors


def _has_net_admin() -> bool:
    for line in PROC_STATUS.read_text().splitlines():
        if line.startswith("CapEff:"):
            return bool(int(line.split()[1], 16) >> _CAP_NET_ADMIN & 1)
    return False


def _interface_from_dump(name: str, lines: list[str]) -> Interface:
    """An interface from its `wg show <name> dump` lines: its own line, then one per peer."""
    # private-key, public-key, listen-port, fwmark
    _, public_key, listen_port, fwmark = lines[0].split("\t")[:4]
    return Interface(
        name=name,
        status="up",
        public_key=public_key if public_key != "(none)" else None,
        listen_port=(int(listen_port) or None) if listen_port.isdigit() else None,
        fwmark=fwmark if fwmark != "off" else None,
        num_peers=len(lines) - 1,
    )


async def list_interfaces() -> list[Interface]:
    # `wg show all dump` is `wg show <name> dump` for every interface, each line prefixed with the name.
    dumps: dict[str, list[str]] = {}
    for line in (await _check(["wg", "show", "all", "dump"])).splitlines():
        name, _, rest = line.partition("\t")
        dumps.setdefault(name, []).append(rest)
    interfaces = {name: _interface_from_dump(name, lines) for name, lines in dumps.items()}

    # shortcut: blocking listing of a small local dir; use asyncio.to_thread if it ever gets slow
    for conf_file in sorted(CONFIG_DIR.glob("*.conf")):  # noqa: ASYNC240
        name = conf_file.stem
        if name in interfaces:
            continue
        if not INTERFACE_NAME_PATTERN.fullmatch(name):
            logger.warning("skipping .conf with invalid interface name: %s", name)
            continue
        interfaces[name] = Interface(name=name, status="down")

    return list(interfaces.values())


async def get_interface(name: str) -> Interface:
    lines = await _show(name)
    if lines:
        return _interface_from_dump(name, lines)
    if _conf_path(name).exists():
        return Interface(name=name, status="down")
    raise InterfaceNotFound(name)


async def update_interface(name: str, update: InterfaceUpdate) -> Interface:
    args: list[str] = []
    if update.private_key:
        args += ["private-key", "/dev/stdin"]
    if update.listen_port is not None:
        args += ["listen-port", str(update.listen_port)]
    if update.fwmark is not None:
        args += ["fwmark", update.fwmark]
    if args:  # `wg set <name>` alone only prints its usage
        logger.info("updating interface %s", name)
        await _wg_set(name, args, secret=update.private_key)
    lines = await _show(name)
    if lines is None:
        raise _not_running(name)
    return _interface_from_dump(name, lines)


async def _wg_quick(action: str, name: str) -> None:
    _require_conf(name)
    running = await _show(name) is not None
    if action == "up" and running:
        raise InterfaceAlreadyRunning(name)
    if action in ("down", "save") and not running:
        raise InterfaceNotRunning(name)
    logger.info("wg-quick %s %s", action, name)
    await _check(["wg-quick", action, name])


async def create_interface(interface: InterfaceCreate) -> Interface:
    conf = _conf_path(interface.name)
    content = f"[Interface]\nAddress = {interface.address}\nPrivateKey = {interface.private_key}\n"
    if interface.listen_port is not None:
        content += f"ListenPort = {interface.listen_port}\n"
    if await _show(interface.name) is not None:
        raise InterfaceAlreadyExists(interface.name)
    try:
        fd = os.open(conf, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        raise InterfaceAlreadyExists(interface.name) from None
    with os.fdopen(fd, "w") as f:
        f.write(content)
    logger.info("creating interface %s", interface.name)
    try:
        await _check(["wg-quick", "up", interface.name])
    except BaseException:
        conf.unlink()  # leave nothing behind when the interface cannot come up
        raise
    return await get_interface(interface.name)


async def delete_interface(name: str) -> None:
    _require_conf(name)
    if await _show(name) is not None:
        await _check(["wg-quick", "down", name])
    logger.info("deleting interface %s", name)
    _conf_path(name).unlink(missing_ok=True)  # another request may have deleted it meanwhile


async def interface_up(name: str) -> Interface:
    await _wg_quick("up", name)
    return await get_interface(name)


async def interface_down(name: str) -> Interface:
    await _wg_quick("down", name)
    return await get_interface(name)


async def interface_save(name: str) -> Interface:
    await _wg_quick("save", name)
    return await get_interface(name)


def _peer_from_dump(line: str) -> Peer:
    """A peer from its line of `wg show <name> dump`."""
    # The second field is the preshared key: a secret, never read back.
    public_key, _, endpoint, allowed_ips, latest_handshake, transfer_rx, transfer_tx, keepalive = line.split("\t")
    return Peer(
        public_key=public_key,
        endpoint=endpoint if endpoint != "(none)" else None,
        allowed_ips=allowed_ips if allowed_ips != "(none)" else None,
        latest_handshake=int(latest_handshake) or None,
        transfer_rx=int(transfer_rx),
        transfer_tx=int(transfer_tx),
        persistent_keepalive=int(keepalive) if keepalive != "off" else None,
    )


async def list_peers(interface: str) -> list[Peer]:
    lines = await _show(interface)
    if lines is None:
        raise _not_running(interface)
    return [_peer_from_dump(line) for line in lines[1:]]


async def get_peer(interface: str, public_key: str) -> Peer:
    peers = await list_peers(interface)
    found = next((p for p in peers if p.public_key == public_key), None)
    if found is None:
        raise PeerNotFound(public_key)
    return found


async def _has_peer(interface: str, public_key: str) -> bool:
    return any(p.public_key == public_key for p in await list_peers(interface))


async def add_peer(interface: str, peer: PeerCreate) -> Peer:
    # wg set would update an existing peer; changing one is update_peer's job.
    if await _has_peer(interface, peer.public_key):
        raise PeerAlreadyExists(peer.public_key)
    await _set_peer(interface, peer.public_key, peer)
    return await get_peer(interface, peer.public_key)


async def update_peer(interface: str, public_key: str, peer: PeerUpdate) -> Peer:
    await get_peer(interface, public_key)  # wg set would create a missing peer; adding one is add_peer's job
    await _set_peer(interface, public_key, peer)
    return await get_peer(interface, public_key)


async def _set_peer(interface: str, public_key: str, peer: PeerCreate | PeerUpdate) -> None:
    """Apply the peer settings with `wg set`. Omitted fields are not changed."""
    args = ["peer", public_key]
    if peer.allowed_ips is not None:
        args += ["allowed-ips", peer.allowed_ips]
    if peer.endpoint is not None:
        args += ["endpoint", peer.endpoint]
    # preshared-key: disabled for now, to be revisited. It would be passed through stdin too.
    if peer.persistent_keepalive is not None:
        args += ["persistent-keepalive", str(peer.persistent_keepalive)]
    logger.info("setting peer %s on %s", public_key[:8], interface)
    await _wg_set(interface, args)


async def delete_peer(interface: str, public_key: str) -> None:
    # wg set ... remove succeeds even for a peer that does not exist.
    if not await _has_peer(interface, public_key):
        raise PeerNotFound(public_key)
    logger.info("deleting peer %s from %s", public_key[:8], interface)
    await _wg_set(interface, ["peer", public_key, "remove"])
