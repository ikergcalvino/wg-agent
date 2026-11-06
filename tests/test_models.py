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
        iface = Interface(
            name="wg0",
            status="up",
            public_key=VALID_KEY,
            listen_port=51820,
            fw_mark="0x1234",
            num_peers=3,
        )
        assert iface.num_peers == 3
        assert iface.fw_mark == "0x1234"

    def test_minimal(self):
        iface = Interface(name="wg0", status="down")
        assert iface.num_peers == 0
        assert iface.public_key is None
        assert iface.listen_port is None

    def test_any_kernel_name_is_accepted(self):
        # ip link allows names that wg-quick does not, e.g. for interfaces created outside the agent.
        assert Interface(name="vpn#1", status="up").name == "vpn#1"

    def test_invalid_public_key(self):
        with pytest.raises(ValidationError, match="key format"):
            Interface(name="wg0", status="up", public_key=INVALID_KEY)

    def test_has_no_private_key(self):
        assert "private_key" not in Interface.model_fields


class TestInterfaceUpdate:
    def test_valid_full(self):
        update = InterfaceUpdate(private_key=VALID_KEY, listen_port=51820, fw_mark="off")
        assert update.listen_port == 51820

    def test_empty(self):
        assert InterfaceUpdate().model_dump(exclude_unset=True) == {}

    def test_invalid_private_key(self):
        with pytest.raises(ValidationError, match="key format"):
            InterfaceUpdate(private_key=INVALID_KEY)

    def test_listen_port_zero_picks_a_random_port(self):
        assert InterfaceUpdate(listen_port=0).listen_port == 0

    @pytest.mark.parametrize("port", [-1, 70000])
    def test_invalid_listen_port(self, port):
        with pytest.raises(ValidationError):
            InterfaceUpdate(listen_port=port)

    @pytest.mark.parametrize("mark", ["off", "0", "1234", "0x1234", "0xFFFFFFFF", "4294967295"])
    def test_valid_fw_mark(self, mark):
        assert InterfaceUpdate(fw_mark=mark).fw_mark == mark

    @pytest.mark.parametrize("mark", ["", "on", "0x", "-1", "0x123456789", "4294967296", "1\nPostUp = id"])
    def test_invalid_fw_mark(self, mark):
        with pytest.raises(ValidationError, match="fw_mark"):
            InterfaceUpdate(fw_mark=mark)

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

    @pytest.mark.parametrize("missing", ["public_key", "allowed_ips"])
    def test_required_fields(self, missing):
        data = {"public_key": VALID_KEY, "allowed_ips": "10.0.0.2/32"}
        del data[missing]
        with pytest.raises(ValidationError, match=missing):
            PeerCreate(**data)

    def test_invalid_public_key(self):
        with pytest.raises(ValidationError, match="key format"):
            PeerCreate(public_key=INVALID_KEY, allowed_ips="10.0.0.2/32")

    def test_invalid_allowed_ips(self):
        with pytest.raises(ValidationError, match="CIDR"):
            PeerCreate(public_key=VALID_KEY, allowed_ips="not-a-cidr")

    def test_all_wg_fields(self):
        peer = PeerCreate(
            public_key=VALID_KEY,
            allowed_ips="10.0.0.2/32",
            endpoint="1.2.3.4:51820",
            preshared_key=VALID_KEY,
            persistent_keepalive=25,
        )
        assert peer.endpoint == "1.2.3.4:51820"
        assert peer.persistent_keepalive == 25


class TestPeerUpdate:
    def test_empty(self):
        assert PeerUpdate().model_dump(exclude_unset=True) == {}

    @pytest.mark.parametrize("ips", ["10.0.0.2/32", "10.0.0.0/24, fd00::/64", "0.0.0.0/0, ::/0"])
    def test_valid_allowed_ips(self, ips):
        assert PeerUpdate(allowed_ips=ips).allowed_ips == ips

    def test_invalid_allowed_ips(self):
        with pytest.raises(ValidationError, match="CIDR"):
            PeerUpdate(allowed_ips="not-a-cidr")

    def test_invalid_preshared_key(self):
        with pytest.raises(ValidationError, match="key format"):
            PeerUpdate(preshared_key=INVALID_KEY)

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
        ],
    )
    def test_invalid(self, endpoint):
        with pytest.raises(ValidationError, match="Invalid endpoint"):
            PeerUpdate(endpoint=endpoint)
