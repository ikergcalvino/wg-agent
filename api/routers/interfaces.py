from fastapi import APIRouter

from api.models.interfaces import Interface, InterfaceCreate, InterfaceUpdate
from api.services import wireguard as wg
from api.types import InterfaceName

router = APIRouter(prefix="/interfaces", tags=["interfaces"])


@router.get("")
async def list_interfaces() -> list[Interface]:
    return await wg.list_interfaces()


@router.get("/{name}")
async def get_interface(name: InterfaceName) -> Interface:
    return await wg.get_interface(name)


@router.post("", status_code=201)
async def create_interface(body: InterfaceCreate) -> Interface:
    return await wg.create_interface(body)


@router.delete("/{name}", status_code=204)
async def delete_interface(name: InterfaceName) -> None:
    await wg.delete_interface(name)


@router.patch("/{name}")
async def update_interface(name: InterfaceName, body: InterfaceUpdate) -> Interface:
    return await wg.update_interface(name, body)


@router.post("/{name}/up")
async def interface_up(name: InterfaceName) -> Interface:
    return await wg.interface_up(name)


@router.post("/{name}/down")
async def interface_down(name: InterfaceName) -> Interface:
    return await wg.interface_down(name)


@router.post("/{name}/save")
async def interface_save(name: InterfaceName) -> Interface:
    return await wg.interface_save(name)
