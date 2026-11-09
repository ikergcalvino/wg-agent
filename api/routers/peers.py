from fastapi import APIRouter, HTTPException

from api.models.peers import Peer, PeerCreate, PeerUpdate
from api.services import wireguard as wg
from api.types import InterfaceName, WireGuardKey

router = APIRouter(
    prefix="/interfaces/{interface}/peers",
    tags=["peers"],
)


@router.get("")
async def list_peers(interface: InterfaceName) -> list[Peer]:
    return await wg.list_peers(interface)


@router.post("", status_code=201)
async def create_peer(interface: InterfaceName, body: PeerCreate) -> Peer:
    await wg.set_peer(interface, body.public_key, body)
    return await _get_peer_after_change(interface, body.public_key)


# Public keys are base64 and often contain '/', so the key segment uses the
# path converter; WireGuardKey still validates the whole value.
@router.get("/{public_key:path}")
async def get_peer(interface: InterfaceName, public_key: WireGuardKey) -> Peer:
    peer = await wg.get_peer(interface, public_key)
    if not peer:
        raise HTTPException(status_code=404, detail="Peer not found")
    return peer


@router.patch("/{public_key:path}")
async def update_peer(interface: InterfaceName, public_key: WireGuardKey, body: PeerUpdate) -> Peer:
    # wg set would create a missing peer; creating is POST's job.
    if await wg.get_peer(interface, public_key) is None:
        raise HTTPException(status_code=404, detail="Peer not found")
    await wg.set_peer(interface, public_key, body)
    return await _get_peer_after_change(interface, public_key)


@router.delete("/{public_key:path}", status_code=204)
async def delete_peer(interface: InterfaceName, public_key: WireGuardKey) -> None:
    await wg.delete_peer(interface, public_key)


async def _get_peer_after_change(interface: str, public_key: str) -> Peer:
    peer = await wg.get_peer(interface, public_key)
    if not peer:
        raise HTTPException(status_code=404, detail="Peer not found after operation")
    return peer
