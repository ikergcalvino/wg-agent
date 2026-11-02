import shutil

from fastapi import APIRouter, Depends

from api import __version__
from api.config import settings
from api.dependencies import verify_api_key
from api.models.system import CheckResult, Health, Info
from api.services import wireguard as wg

router = APIRouter(tags=["system"])


@router.get("", dependencies=[Depends(verify_api_key)])
async def info() -> Info:
    return Info(name="wg-agent", version=__version__)


# Public, so container healthchecks and load balancers need no API key.
@router.get("/health")
async def health() -> Health:
    checks: dict[str, CheckResult] = {
        "config_dir": _result(settings.config_dir.is_dir()),
        "wg": _result(shutil.which("wg") is not None),
        "wg_quick": _result(shutil.which("wg-quick") is not None),
    }
    checks["wg_access"] = "ok" if await wg.has_access() else "error"
    ok = all(v == "ok" for v in checks.values())
    return Health(status="ok" if ok else "degraded", checks=checks)


def _result(ok: bool) -> CheckResult:
    return "ok" if ok else "missing"
