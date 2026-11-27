from fastapi import APIRouter

from api.models.peers import Peer, PeerCreate, PeerUpdate
from api.services import wireguard as wg
from api.types import InterfaceName, WireGuardKey

router = APIRouter(prefix="/interfaces/{interface}/peers", tags=["peers"])


@router.get("")
async def list_peers(interface: InterfaceName) -> list[Peer]:
    return await wg.list_peers(interface)


@router.post("", status_code=201)
async def add_peer(interface: InterfaceName, body: PeerCreate) -> Peer:
    return await wg.add_peer(interface, body)


# Public keys are base64 and often contain '/', so the key segment uses the
# path converter; WireGuardKey still validates the whole value.
@router.get("/{public_key:path}")
async def get_peer(interface: InterfaceName, public_key: WireGuardKey) -> Peer:
    return await wg.get_peer(interface, public_key)


@router.patch("/{public_key:path}")
async def update_peer(interface: InterfaceName, public_key: WireGuardKey, body: PeerUpdate) -> Peer:
    return await wg.update_peer(interface, public_key, body)


@router.delete("/{public_key:path}", status_code=204)
async def delete_peer(interface: InterfaceName, public_key: WireGuardKey) -> None:
    await wg.delete_peer(interface, public_key)
