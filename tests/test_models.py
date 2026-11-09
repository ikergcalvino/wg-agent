import pytest
from pydantic import ValidationError

from api.models.interfaces import Interface, InterfaceUpdate
from api.models.peers import Peer, PeerCreate, PeerUpdate
from tests.conftest import VALID_KEY

INVALID_KEY = "not-a-valid-key"


# ---------------------------------------------------------------------------
# Interface
# ---------------------------------------------------------------------------


class TestInterface:
    def test_runtime_fields(self):
        interface = Interface(
            name="wg0",
            status="up",
            public_key=VALID_KEY,
            listen_port=51820,
            fwmark="0x1234",
            num_peers=3,
        )
        assert interface.num_peers == 3
        assert interface.fwmark == "0x1234"

    def test_minimal(self):
        interface = Interface(name="wg0", status="down")
        assert interface.num_peers == 0
        assert interface.public_key is None
        assert interface.listen_port is None

    def test_any_kernel_name_is_accepted(self):
        # ip link allows names that wg-quick does not, e.g. for interfaces created outside the agent.
        assert Interface(name="vpn#1", status="up").name == "vpn#1"

    def test_has_no_private_key(self):
        assert "private_key" not in Interface.model_fields


class TestInterfaceUpdate:
    def test_valid_full(self):
        update = InterfaceUpdate(private_key=VALID_KEY, listen_port=51820, fwmark="off")
        assert update.listen_port == 51820

    def test_empty(self):
        assert InterfaceUpdate().model_dump(exclude_unset=True) == {}

    @pytest.mark.parametrize("key", [INVALID_KEY, VALID_KEY + "\n"])
    def test_invalid_private_key(self, key):
        with pytest.raises(ValidationError, match="Invalid WireGuard key"):
            InterfaceUpdate(private_key=key)

    def test_listen_port_zero_picks_a_random_port(self):
        assert InterfaceUpdate(listen_port=0).listen_port == 0

    @pytest.mark.parametrize("port", [-1, 70000])
    def test_invalid_listen_port(self, port):
        with pytest.raises(ValidationError):
            InterfaceUpdate(listen_port=port)

    @pytest.mark.parametrize(
        "mark", ["off", "OFF", "0", "010", "1234", "0x1234", "0xFFFFFFFF", "0x00000000ff", "4294967295"]
    )
    def test_valid_fwmark(self, mark):
        assert InterfaceUpdate(fwmark=mark).fwmark == mark

    @pytest.mark.parametrize(
        "mark", ["", "on", "0x", "0XFF", "-1", "+1", " 1", "1_0", "0x123456789", "4294967296", "1\n", "1\nPostUp = id"]
    )
    def test_invalid_fwmark(self, mark):
        with pytest.raises(ValidationError, match="fwmark"):
            InterfaceUpdate(fwmark=mark)

    @pytest.mark.parametrize("field", ["name", "address", "dns", "post_up", "save_config"])
    def test_wg_quick_and_unknown_fields_forbidden(self, field):
        with pytest.raises(ValidationError, match="extra"):
            InterfaceUpdate.model_validate({field: "x"})


# ---------------------------------------------------------------------------
# Peer
# ---------------------------------------------------------------------------


class TestPeer:
    def test_runtime_fields(self):
        peer = Peer(
            public_key=VALID_KEY,
            allowed_ips="10.0.0.2/32",
            endpoint="1.2.3.4:51820",
            latest_handshake=1700000000,
            transfer_rx=1024,
            transfer_tx=2048,
            persistent_keepalive=25,
        )
        assert peer.transfer_rx == 1024

    def test_has_no_preshared_key(self):
        assert "preshared_key" not in Peer.model_fields


class TestPeerCreate:
    def test_valid(self):
        peer = PeerCreate(public_key=VALID_KEY, allowed_ips="10.0.0.2/32")
        assert peer.public_key == VALID_KEY

    def test_public_key_is_required(self):
        with pytest.raises(ValidationError, match="public_key"):
            PeerCreate.model_validate({"allowed_ips": "10.0.0.2/32"})

    def test_public_key_is_enough(self):
        # As in wg(8): PublicKey is the only required field of a peer.
        assert PeerCreate(public_key=VALID_KEY).allowed_ips is None

    def test_invalid_public_key(self):
        with pytest.raises(ValidationError, match="Invalid WireGuard key"):
            PeerCreate(public_key=INVALID_KEY, allowed_ips="10.0.0.2/32")

    def test_invalid_allowed_ips(self):
        with pytest.raises(ValidationError, match="Invalid allowed IP"):
            PeerCreate(public_key=VALID_KEY, allowed_ips="not-a-cidr")

    def test_all_wg_fields(self):
        peer = PeerCreate(
            public_key=VALID_KEY,
            allowed_ips="10.0.0.2/32",
            endpoint="1.2.3.4:51820",
            persistent_keepalive=25,
        )
        assert peer.endpoint == "1.2.3.4:51820"
        assert peer.persistent_keepalive == 25


class TestPeerUpdate:
    def test_empty(self):
        assert PeerUpdate().model_dump(exclude_unset=True) == {}

    @pytest.mark.parametrize(
        "ips", ["10.0.0.2/32", "10.0.0.0/24, fd00::/64", "0.0.0.0/0, ::/0", "+10.0.0.3/32, -10.0.0.2/32", ""]
    )
    def test_valid_allowed_ips(self, ips):
        assert PeerUpdate(allowed_ips=ips).allowed_ips == ips

    @pytest.mark.parametrize(
        "ips", ["not-a-cidr", " ", "10.0.0.2/32\n", "10.0.0.2/32,", "+", "+-10.0.0.2/32", "+ 10.0.0.2/32"]
    )
    def test_invalid_allowed_ips(self, ips):
        with pytest.raises(ValidationError, match="Invalid allowed IP"):
            PeerUpdate(allowed_ips=ips)

    def test_preshared_key_is_disabled(self):
        with pytest.raises(ValidationError, match="extra"):
            PeerUpdate.model_validate({"preshared_key": VALID_KEY})

    @pytest.mark.parametrize("keepalive", [-1, 70000])
    def test_persistent_keepalive_range(self, keepalive):
        with pytest.raises(ValidationError):
            PeerUpdate(persistent_keepalive=keepalive)

    @pytest.mark.parametrize("field", ["public_key", "latest_handshake", "transfer_rx", "unknown"])
    def test_read_only_and_unknown_fields_forbidden(self, field):
        with pytest.raises(ValidationError, match="extra"):
            PeerUpdate.model_validate({field: 1})


class TestPeerEndpoint:
    @pytest.mark.parametrize(
        "endpoint",
        [
            "1.2.3.4:51820",
            "[fd00::1]:51820",
            "[fe80::1%eth0]:51820",
            "vpn.example.com:51820",
            "localhost:1",
            "host-1:65535",
        ],
    )
    def test_valid(self, endpoint):
        assert PeerUpdate(endpoint=endpoint).endpoint == endpoint

    @pytest.mark.parametrize(
        "endpoint",
        [
            "",
            "1.2.3.4",
            "1.2.3.4:",
            "1.2.3.4:0",
            "1.2.3.4:65536",
            "1.2.3.4:51820x",
            "fd00::1:51820",
            "[not-an-ip]:51820",
            "[1.2.3.4]:51820",
            "-bad.example.com:51820",
            "bad_host:51820",
            "host:51820\nPostUp = id",
            "1.2.3.4:51820 extra",
            "1.2.3.4:51820\n",
            "vpn.example.com\n:51820",
        ],
    )
    def test_invalid(self, endpoint):
        with pytest.raises(ValidationError, match="Invalid endpoint"):
            PeerUpdate(endpoint=endpoint)
