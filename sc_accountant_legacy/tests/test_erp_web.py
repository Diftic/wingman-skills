"""HTTP trust boundaries and dashboard delivery, independent of Wingman runtime."""

import pytest
from fastapi.testclient import TestClient


class BoundaryEngine:
    """Minimal engine substitute while domain engine is developed independently."""

    def __init__(self):
        self.calls = []

    def command(self, action, data):
        self.calls.append((action, data))
        if data.get("name") == "invalid":
            raise ValueError("Name cannot be invalid")
        if data.get("name") == "broken":
            raise RuntimeError("private database path")
        return {"ok": True, "id": "op-1"}

    def view(self, section="overview", **filters):
        return {"mode": "simple", "data": {"section": section, "filters": filters}}


@pytest.fixture
def client():
    from erp_web import create_app

    return TestClient(create_app(BoundaryEngine()), base_url="http://127.0.0.1:7863")


def post(client, action="start_operation", data=None, origin="http://127.0.0.1:7863"):
    headers = {"Origin": origin} if origin else {}
    return client.post(
        "/api/erp/command",
        json={"action": action, "data": data or {"name": "Run"}},
        headers=headers,
    )


@pytest.mark.parametrize(
    "origin",
    [
        None,
        "null",
        "https://evil.example",
        "http://127.0.0.1:9999",
        "http://localhost:7863",
    ],
)
def test_foreign_or_missing_origin_cannot_modify_records(client, origin):
    assert post(client, origin=origin).status_code == 403
    assert client.app.state.engine.calls == []


def test_rebinding_host_cannot_read_or_modify_records(client):
    assert (
        client.get("/api/erp/overview", headers={"host": "evil.example"}).status_code
        == 400
    )
    assert post(client).status_code == 200


def test_only_explicit_commands_are_reachable(client):
    assert post(client, action="close").status_code == 400
    assert client.app.state.engine.calls == []
    assert post(client).json() == {"ok": True, "id": "op-1"}


def test_validation_is_explained_but_unexpected_errors_are_private(client):
    bad = post(client, data={"name": "invalid"})
    assert bad.status_code == 400
    assert bad.json()["detail"] == "Name cannot be invalid"
    broken = post(client, data={"name": "broken"})
    assert broken.status_code == 500
    assert "private" not in broken.text


def test_reads_are_bounded_and_sections_are_allowlisted(client):
    assert client.get("/api/erp/inventory?limit=201").status_code == 422
    assert client.get("/api/erp/inventory?offset=-1").status_code == 422
    assert client.get("/api/erp/secret").status_code == 404
    result = client.get("/api/erp/inventory?limit=25&offset=50").json()
    assert result["data"]["filters"]["limit"] == 25
    assert result["data"]["filters"]["offset"] == 50


def test_large_mutations_rejected_before_engine(client):
    assert post(client, data={"notes": "x" * 70000}).status_code == 413
    assert client.app.state.engine.calls == []


def test_dashboard_assets_are_local_and_have_browser_protections(client):
    home = client.get("/")
    assert home.status_code == 200
    assert "SC Accountant" in home.text
    assert "frame-ancestors 'none'" in home.headers["content-security-policy"]
    assert client.get("/app.js").status_code == 200
    assert client.get("/style.css").status_code == 200
    assert client.get("/../erp.py").status_code == 404


def test_personal_trading_workflow_uses_same_records_in_both_modes(tmp_path):
    from erp import ERP
    from erp_web import create_app

    engine = ERP(tmp_path / "web.sqlite3")
    try:
        with TestClient(create_app(engine), base_url="http://127.0.0.1:7863") as client:
            assert (
                post(client, "reconcile_wallet", {"amount": "200000"}).status_code
                == 200
            )
            operation = post(client, "start_operation", {"name": "Hauling run"}).json()
            lot = post(
                client,
                "buy_stock",
                {
                    "item_id": "ore",
                    "item_name": "Ore",
                    "quantity": "100",
                    "unit": "SCU",
                    "location": "Port",
                    "amount": "100000",
                    "operation_id": operation["id"],
                },
            ).json()
            sale = post(
                client,
                "sell_stock",
                {
                    "lot_id": lot["id"],
                    "quantity": "50",
                    "amount": "70000",
                    "operation_id": operation["id"],
                },
            )
            assert sale.status_code == 200, sale.text
            before = client.get("/api/erp/overview").json()
            assert before["data"]["balance"] == "170000.00"
            assert before["data"]["realized_profit"] == "20000.00"
            assert before["data"]["inventory_cost"] == "50000.00"
            assert post(client, "set_mode", {"mode": "advanced"}).status_code == 200
            after = client.get("/api/erp/overview").json()
            assert after["mode"] == "advanced"
            for key in ("balance", "realized_profit", "inventory_cost"):
                assert before["data"][key] == after["data"][key]
    finally:
        engine.close()


def test_server_releases_listener_without_closing_owned_engine():
    import socket
    from urllib.request import urlopen
    from erp_web import ERPServer

    server = ERPServer(BoundaryEngine(), port=0)
    try:
        assert server.start().startswith("http://127.0.0.1:")
        with urlopen(server.url + "/api/erp/overview", timeout=3) as response:
            assert response.status == 200
        assert server.start() == server.url
    finally:
        server.stop()
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", server.port))


def test_dashboard_import_without_unbundled_trustedhost(monkeypatch):
    import builtins
    import importlib.util
    from pathlib import Path

    original = builtins.__import__

    def packaged_import(name, *args, **kwargs):
        if name == "starlette.middleware.trustedhost":
            raise ModuleNotFoundError(name)
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", packaged_import)
    path = Path(__file__).resolve().parents[1] / "erp_web.py"
    spec = importlib.util.spec_from_file_location("accountant_web_host_probe", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with TestClient(
        module.create_app(BoundaryEngine()), base_url="http://127.0.0.1:7863"
    ) as client:
        assert client.get("/api/erp/overview").status_code == 200
        assert (
            client.get(
                "/api/erp/overview", headers={"host": "evil.example"}
            ).status_code
            == 400
        )


@pytest.mark.parametrize(
    "host",
    [
        "localhost.evil.test",
        "127.0.0.1.evil.test",
        "localhost:7863:extra",
        "localhost@evil.test",
    ],
)
def test_malformed_or_nonlocal_host_is_rejected(client, host):
    assert client.get("/api/erp/overview", headers={"host": host}).status_code == 400


def test_phone_qr_bootstraps_session_without_opening_records_to_other_clients():
    from erp_web import create_app
    engine = BoundaryEngine()
    app = create_app(engine, lan_host="192.168.1.20", access_token="test-phone-token")
    with TestClient(app, base_url="http://192.168.1.20:7863") as phone:
        assert phone.get("/api/erp/overview").status_code == 403
        assert phone.get("/?share=wrong").status_code == 403
        assert phone.get("/?share=wrong%E2%98%83").status_code == 403
        # Spoofing Host must not bypass the phone's session requirement.
        assert phone.get("/api/erp/overview", headers={"host":"127.0.0.1:7863"}).status_code == 403
        home = phone.get("/?share=test-phone-token")
        assert home.status_code == 200 and "SC Accountant" in home.text
        assert home.url.query == b""
        assert phone.get("/app.js").status_code == 200
        assert phone.get("/api/erp/overview").status_code == 200
        assert post(phone, origin="http://192.168.1.20:7863").status_code == 200
        assert post(phone, origin="http://evil.example").status_code == 403
    with TestClient(app, base_url="http://192.168.1.20:7863") as stranger:
        assert stranger.get("/api/erp/overview").status_code == 403


def test_shared_server_keeps_loopback_access_and_local_only_default():
    from erp_web import create_app, ERPServer
    app = create_app(BoundaryEngine(), lan_host="192.168.1.20", access_token="phone-token")
    with TestClient(app, base_url="http://127.0.0.1:7863", client=("127.0.0.1", 54321)) as local:
        assert local.get("/api/erp/overview").status_code == 200
    assert ERPServer(BoundaryEngine()).lan_url == ""


def test_real_phone_listener_session_and_shutdown(monkeypatch):
    from http.client import HTTPConnection
    from urllib.parse import urlsplit
    import socket
    import erp_sharing
    from erp_web import ERPServer
    monkeypatch.setattr(erp_sharing, "get_lan_ip", lambda: "192.168.1.20")
    server = ERPServer(BoundaryEngine(), port=0, share_on_lan=True)
    try:
        server.start()
        phone = urlsplit(server.lan_url)
        assert phone.port == server.port
        conn = HTTPConnection("127.0.0.1", server.port, timeout=3)
        try:
            conn.request("GET", "/api/erp/overview", headers={"Host": phone.netloc})
            response = conn.getresponse()
            assert response.status == 403
            response.read()
            conn.request("GET", "/?" + phone.query, headers={"Host": phone.netloc})
            response = conn.getresponse()
            assert response.status == 303
            cookie = response.getheader("Set-Cookie")
            assert "HttpOnly" in cookie and "SameSite=strict" in cookie
            response.read()
            conn.request("GET", "/api/erp/overview", headers={"Host": phone.netloc, "Cookie": cookie.split(';')[0]})
            response = conn.getresponse()
            assert response.status == 200
            response.read()
        finally:
            conn.close()
    finally:
        server.stop()
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", server.port))
