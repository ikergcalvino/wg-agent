from unittest.mock import AsyncMock, patch

import pytest

from tests.conftest import NOT_RUNNING, VALID_KEY

# ---------------------------------------------------------------------------
# List Peers
# ---------------------------------------------------------------------------


class TestListPeers:
    async def test_success(self, client):
        dump = f"PRIVATE\tPUBLIC\t51820\toff\n{VALID_KEY}\t(none)\t1.2.3.4:51820\t10.0.0.2/32\t0\t0\t0\toff"
        with patch("api.services.wireguard._run", new_callable=AsyncMock, return_value=(dump, "", 0)):
            r = await client.get("/api/v1/interfaces/wg0/peers")
            assert r.status_code == 200
            assert len(r.json()) == 1

    async def test_interface_not_found(self, client, tmp_path):
        with (
            patch("api.services.wireguard._run", new_callable=AsyncMock, return_value=("", NOT_RUNNING, 1)),
            patch("api.services.wireguard.CONFIG_DIR", tmp_path),
        ):
            r = await client.get("/api/v1/interfaces/wg0/peers")
            assert r.status_code == 404


# ---------------------------------------------------------------------------
# Create Peer
# ---------------------------------------------------------------------------


class TestCreatePeer:
    async def test_success(self, client):
        dump = f"PRIVATE\tPUBLIC\t51820\toff\n{VALID_KEY}\t(none)\t(none)\t10.0.0.2/32\t0\t0\t0\toff"
        with patch("api.services.wireguard._run", new_callable=AsyncMock) as mock_run:
            mock_run.side_effect = [
                ("", "", 0),  # wg set
                (dump, "", 0),  # wg show dump (get_peer)
            ]
            r = await client.post(
                "/api/v1/interfaces/wg0/peers",
                json={"public_key": VALID_KEY, "allowed_ips": "10.0.0.2/32"},
            )
            assert r.status_code == 201
            assert r.json()["public_key"] == VALID_KEY

    async def test_missing_public_key(self, client):
        r = await client.post(
            "/api/v1/interfaces/wg0/peers",
            json={"allowed_ips": "10.0.0.2/32"},
        )
        assert r.status_code == 422

    async def test_missing_allowed_ips(self, client):
        r = await client.post(
            "/api/v1/interfaces/wg0/peers",
            json={"public_key": VALID_KEY},
        )
        assert r.status_code == 422

    async def test_invalid_key(self, client):
        r = await client.post(
            "/api/v1/interfaces/wg0/peers",
            json={"public_key": "bad", "allowed_ips": "10.0.0.2/32"},
        )
        assert r.status_code == 422


# ---------------------------------------------------------------------------
# Get Peer
# ---------------------------------------------------------------------------


class TestGetPeer:
    async def test_success(self, client):
        dump = f"PRIVATE\tPUBLIC\t51820\toff\n{VALID_KEY}\t(none)\t1.2.3.4:51820\t10.0.0.2/32\t0\t0\t0\toff"
        with patch("api.services.wireguard._run", new_callable=AsyncMock, return_value=(dump, "", 0)):
            r = await client.get(f"/api/v1/interfaces/wg0/peers/{VALID_KEY}")
            assert r.status_code == 200
            assert r.json()["public_key"] == VALID_KEY

    async def test_not_found(self, client):
        dump = "PRIVATE\tPUBLIC\t51820\toff"
        with patch("api.services.wireguard._run", new_callable=AsyncMock, return_value=(dump, "", 0)):
            r = await client.get(f"/api/v1/interfaces/wg0/peers/{VALID_KEY}")
            assert r.status_code == 404

    async def test_interface_not_found(self, client, tmp_path):
        with (
            patch("api.services.wireguard._run", new_callable=AsyncMock, return_value=("", NOT_RUNNING, 1)),
            patch("api.services.wireguard.CONFIG_DIR", tmp_path),
        ):
            r = await client.get(f"/api/v1/interfaces/wg0/peers/{VALID_KEY}")
            assert r.status_code == 404


# ---------------------------------------------------------------------------
# Update Peer
# ---------------------------------------------------------------------------


class TestUpdatePeer:
    async def test_success(self, client):
        dump = f"PRIVATE\tPUBLIC\t51820\toff\n{VALID_KEY}\t(none)\t(none)\t10.0.0.3/32\t0\t0\t0\toff"
        with patch("api.services.wireguard._run", new_callable=AsyncMock) as mock_run:
            mock_run.side_effect = [
                (dump, "", 0),  # wg show dump (the peer exists)
                ("", "", 0),  # wg set
                (dump, "", 0),  # wg show dump (get_peer)
            ]
            r = await client.patch(
                f"/api/v1/interfaces/wg0/peers/{VALID_KEY}",
                json={"allowed_ips": "10.0.0.3/32"},
            )
            assert r.status_code == 200

    async def test_missing_peer_is_not_created(self, client):
        dump = "PRIVATE\tPUBLIC\t51820\toff"
        with patch("api.services.wireguard._run", new_callable=AsyncMock, return_value=(dump, "", 0)) as mock_run:
            r = await client.patch(f"/api/v1/interfaces/wg0/peers/{VALID_KEY}", json={"persistent_keepalive": 10})
            assert r.status_code == 404
            assert r.json()["detail"] == "Peer not found"
            assert all(c.args[0][1] != "set" for c in mock_run.await_args_list)

    async def test_put_is_not_allowed(self, client):
        r = await client.put(f"/api/v1/interfaces/wg0/peers/{VALID_KEY}", json={"allowed_ips": "10.0.0.3/32"})
        assert r.status_code == 405

    async def test_extra_field_rejected(self, client):
        r = await client.patch(
            f"/api/v1/interfaces/wg0/peers/{VALID_KEY}",
            json={"allowed_ips": "10.0.0.3/32", "unknown": "x"},
        )
        assert r.status_code == 422


# ---------------------------------------------------------------------------
# Delete Peer
# ---------------------------------------------------------------------------


class TestDeletePeer:
    async def test_success(self, client):
        with patch("api.services.wireguard._run", new_callable=AsyncMock, return_value=("", "", 0)):
            r = await client.delete(f"/api/v1/interfaces/wg0/peers/{VALID_KEY}")
            assert r.status_code == 204

    async def test_wg_failure(self, client):
        with patch("api.services.wireguard._run", new_callable=AsyncMock, return_value=("", "Line unrecognized", 1)):
            r = await client.delete(f"/api/v1/interfaces/wg0/peers/{VALID_KEY}")
            assert r.status_code == 400

    async def test_down_interface_is_a_conflict(self, client, tmp_path):
        (tmp_path / "wg0.conf").write_text("")
        with patch("api.services.wireguard._run", new_callable=AsyncMock, return_value=("", NOT_RUNNING, 1)):
            r = await client.delete(f"/api/v1/interfaces/wg0/peers/{VALID_KEY}")
            assert r.status_code == 409


# ---------------------------------------------------------------------------
# Keys containing '/'
# ---------------------------------------------------------------------------

SLASH_KEY = "ab/defghijklmnopqrstuvwxyz0123456789ABCDEFE="


class TestSlashInPublicKey:
    @pytest.mark.parametrize("path_key", [SLASH_KEY, SLASH_KEY.replace("/", "%2F")])
    async def test_get(self, client, path_key):
        dump = f"PRIVATE\tPUBLIC\t51820\toff\n{SLASH_KEY}\t(none)\t(none)\t10.0.0.2/32\t0\t0\t0\toff"
        with patch("api.services.wireguard._run", new_callable=AsyncMock, return_value=(dump, "", 0)):
            r = await client.get(f"/api/v1/interfaces/wg0/peers/{path_key}")
            assert r.status_code == 200
            assert r.json()["public_key"] == SLASH_KEY

    async def test_patch(self, client):
        dump = f"PRIVATE\tPUBLIC\t51820\toff\n{SLASH_KEY}\t(none)\t(none)\t10.0.0.3/32\t0\t0\t0\toff"
        with patch("api.services.wireguard._run", new_callable=AsyncMock) as mock_run:
            mock_run.side_effect = [(dump, "", 0), ("", "", 0), (dump, "", 0)]
            r = await client.patch(f"/api/v1/interfaces/wg0/peers/{SLASH_KEY}", json={"allowed_ips": "10.0.0.3/32"})
            assert r.status_code == 200
            assert mock_run.call_args_list[1][0][0][:5] == ["wg", "set", "wg0", "peer", SLASH_KEY]

    async def test_delete(self, client):
        with patch("api.services.wireguard._run", new_callable=AsyncMock, return_value=("", "", 0)) as mock_run:
            r = await client.delete(f"/api/v1/interfaces/wg0/peers/{SLASH_KEY}")
            assert r.status_code == 204
            mock_run.assert_awaited_once_with(["wg", "set", "wg0", "peer", SLASH_KEY, "remove"], secret=None)

    async def test_extra_segments_rejected(self, client):
        r = await client.get(f"/api/v1/interfaces/wg0/peers/{SLASH_KEY}/extra")
        assert r.status_code == 422


# ---------------------------------------------------------------------------
# Preshared keys are write-only
# ---------------------------------------------------------------------------


class TestPresharedKeyNotExposed:
    DUMP = f"PRIVATE\tPUBLIC\t51820\toff\n{VALID_KEY}\t{VALID_KEY}\t(none)\t10.0.0.2/32\t0\t0\t0\toff"

    async def test_list(self, client):
        with patch("api.services.wireguard._run", new_callable=AsyncMock, return_value=(self.DUMP, "", 0)):
            r = await client.get("/api/v1/interfaces/wg0/peers")
            assert r.status_code == 200
            assert "preshared_key" not in r.json()[0]

    async def test_get(self, client):
        with patch("api.services.wireguard._run", new_callable=AsyncMock, return_value=(self.DUMP, "", 0)):
            r = await client.get(f"/api/v1/interfaces/wg0/peers/{VALID_KEY}")
            assert "preshared_key" not in r.json()

    async def test_create_accepts_but_does_not_return_it(self, client):
        with patch("api.services.wireguard._run", new_callable=AsyncMock) as mock_run:
            mock_run.side_effect = [("", "", 0), (self.DUMP, "", 0)]
            r = await client.post(
                "/api/v1/interfaces/wg0/peers",
                json={"public_key": VALID_KEY, "allowed_ips": "10.0.0.2/32", "preshared_key": VALID_KEY},
            )
            assert r.status_code == 201
            assert "preshared_key" not in r.json()
            assert mock_run.call_args_list[0][1]["secret"] == VALID_KEY

    async def test_schema_is_write_only(self, client):
        schemas = (await client.get("/api/v1/openapi.json")).json()["components"]["schemas"]
        assert schemas["PeerCreate"]["properties"]["preshared_key"]["writeOnly"] is True
        assert schemas["PeerUpdate"]["properties"]["preshared_key"]["writeOnly"] is True
        assert "preshared_key" not in schemas["Peer"]["properties"]


class TestEndpointValidation:
    async def test_invalid_endpoint_never_reaches_wg(self, client):
        with patch("api.services.wireguard._run", new_callable=AsyncMock) as mock_run:
            r = await client.post(
                "/api/v1/interfaces/wg0/peers",
                json={"public_key": VALID_KEY, "allowed_ips": "10.0.0.2/32", "endpoint": "--help:1"},
            )
            assert r.status_code == 422
            mock_run.assert_not_awaited()


class TestPeerBodies:
    async def test_update_rejects_public_key_in_body(self, client):
        r = await client.patch(f"/api/v1/interfaces/wg0/peers/{VALID_KEY}", json={"public_key": VALID_KEY})
        assert r.status_code == 422

    async def test_create_rejects_read_only_fields(self, client):
        r = await client.post(
            "/api/v1/interfaces/wg0/peers",
            json={"public_key": VALID_KEY, "allowed_ips": "10.0.0.2/32", "transfer_rx": 0},
        )
        assert r.status_code == 422


class TestUnpaddedKey:
    # wg needs all 44 characters; without the final "=" it rejects the key.
    UNPADDED = VALID_KEY.removesuffix("=")

    async def test_path_key_without_padding_is_rejected(self, client):
        r = await client.get(f"/api/v1/interfaces/wg0/peers/{self.UNPADDED}")
        assert r.status_code == 422

    async def test_body_key_without_padding_is_rejected(self, client):
        r = await client.post(
            "/api/v1/interfaces/wg0/peers", json={"public_key": self.UNPADDED, "allowed_ips": "10.0.0.2/32"}
        )
        assert r.status_code == 422
