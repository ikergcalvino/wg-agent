from fastapi import APIRouter, HTTPException

from api.models.interfaces import Interface, InterfaceAction, InterfaceCreate, InterfaceUpdate
from api.routers import IfaceName
from api.services import wireguard as wg

router = APIRouter(prefix="/interfaces", tags=["interfaces"])


@router.get("")
async def list_interfaces() -> list[Interface]:
    return await wg.list_interfaces()


@router.get("/{name}")
async def get_interface(name: IfaceName) -> Interface:
    data = await wg.get_interface(name)
    if not data:
        raise HTTPException(status_code=404, detail=f"Interface '{name}' not found")
    return data


@router.post("", status_code=201)
async def create_interface(body: InterfaceCreate) -> Interface:
    await wg.create_interface(body)
    return await get_interface(body.name)


@router.delete("/{name}", status_code=204)
async def delete_interface(name: IfaceName) -> None:
    await wg.delete_interface(name)


@router.patch("/{name}")
async def update_interface(name: IfaceName, body: InterfaceUpdate) -> Interface:
    await wg.update_interface(name, body)
    result = await wg.get_interface(name)
    if not result:
        raise HTTPException(status_code=500, detail="Interface updated but could not be retrieved")
    return result


@router.post("/{name}/up")
async def interface_up(name: IfaceName) -> InterfaceAction:
    await wg.interface_up(name)
    return InterfaceAction(status="up", interface=name)


@router.post("/{name}/down")
async def interface_down(name: IfaceName) -> InterfaceAction:
    await wg.interface_down(name)
    return InterfaceAction(status="down", interface=name)


@router.post("/{name}/save")
async def interface_save(name: IfaceName) -> InterfaceAction:
    await wg.interface_save(name)
    return InterfaceAction(status="saved", interface=name)
