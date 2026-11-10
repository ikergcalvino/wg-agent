import shutil
from pathlib import Path

# What the health check reads: the process's capabilities, and the kernel module's sysfs entry.
PROC_STATUS = Path("/proc/self/status")
WIREGUARD_MODULE = Path("/sys/module/wireguard")
_CAP_NET_ADMIN = 12  # bit number, from linux/capability.h


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
