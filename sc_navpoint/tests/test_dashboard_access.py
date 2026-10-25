"""Who may reach the dashboard.

The API has no other authentication. The app as uvicorn serves it
(``served_app``) admits this computer and, while phone sharing is on, a phone
holding the session that the startup card's QR code hands out. Everyone else,
including a page on another site, is refused.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from database import NavPointDatabase

pytest.importorskip("fastapi.testclient")
from fastapi.testclient import TestClient  # noqa: E402

from navpoint_ui import sharing  # noqa: E402
from navpoint_ui.app import NavPointServer  # noqa: E402

LAN = "192.168.1.20"
TOKEN = "t" * 24
PHONE = ("192.168.1.50", 50000)
PC = ("127.0.0.1", 50000)


def _server(tmp_path: Path, monkeypatch, share: bool = True):
    monkeypatch.setattr(sharing, "get_lan_ip", lambda: LAN)
    db = NavPointDatabase(str(tmp_path))
    alpha = db.add_navpoint("Alpha", "srv1", "Daymar", 1.0, 2.0, 3.0)
    server = NavPointServer(db=db, port=7869, share_on_lan=share, access_token=TOKEN)
    return server, alpha


def _client(server, host: str, peer):
    return TestClient(
        server.served_app, base_url=f"http://{host}", client=peer, follow_redirects=False
    )


def test_without_sharing_the_server_stays_on_loopback(tmp_path, monkeypatch) -> None:
    server, _ = _server(tmp_path, monkeypatch, share=False)
    assert server.bind_host == "127.0.0.1"
    assert server.lan_url == ""


def test_sharing_listens_on_the_lan_behind_a_token_link(tmp_path, monkeypatch) -> None:
    server, _ = _server(tmp_path, monkeypatch)
    assert server.bind_host == "0.0.0.0"
    assert server.lan_url == f"http://{LAN}:7869/?share={TOKEN}"


def test_a_phone_without_the_qr_session_is_refused(tmp_path, monkeypatch) -> None:
    server, _ = _server(tmp_path, monkeypatch)
    phone = _client(server, f"{LAN}:7869", PHONE)
    for path in ("/", "/static/app.js", "/api/navpoints", "/api/nav/state", "/?share=wrong"):
        assert phone.get(path).status_code == 403, path


def test_the_qr_link_gives_a_phone_a_session(tmp_path, monkeypatch) -> None:
    server, alpha = _server(tmp_path, monkeypatch)
    phone = _client(server, f"{LAN}:7869", PHONE)
    opened = phone.get(f"/?share={TOKEN}")
    assert opened.status_code == 303
    assert opened.headers["location"] == "/"
    assert phone.cookies.get("sc_navpoint_session") == TOKEN
    assert phone.get("/").status_code == 200
    assert phone.get("/static/app.js").status_code == 200
    assert phone.get("/api/nav/state").status_code == 200
    origin = {"Origin": f"http://{LAN}:7869"}
    assert phone.post(f"/api/nav/target/{alpha.id}", headers=origin).status_code == 200


def test_a_spoofed_host_never_skips_the_session(tmp_path, monkeypatch) -> None:
    server, _ = _server(tmp_path, monkeypatch)
    assert _client(server, "127.0.0.1:7869", PHONE).get("/").status_code == 403


def test_other_hostnames_are_refused(tmp_path, monkeypatch) -> None:
    # A page on another site that rebinds its own name to this computer.
    server, _ = _server(tmp_path, monkeypatch)
    assert _client(server, "evil.example:7869", PC).get("/").status_code == 400


def test_this_computer_needs_no_token(tmp_path, monkeypatch) -> None:
    server, alpha = _server(tmp_path, monkeypatch)
    pc = _client(server, "127.0.0.1:7869", PC)
    assert pc.get("/").status_code == 200
    origin = {"Origin": "http://127.0.0.1:7869"}
    assert pc.post(f"/api/nav/target/{alpha.id}", headers=origin).status_code == 200


def test_changes_must_come_from_the_dashboard_page(tmp_path, monkeypatch) -> None:
    server, alpha = _server(tmp_path, monkeypatch)
    pc = _client(server, "127.0.0.1:7869", PC)
    assert pc.delete("/api/nav/target").status_code == 403
    other = {"Origin": "http://evil.example"}
    assert pc.post(f"/api/nav/target/{alpha.id}", headers=other).status_code == 403


def test_static_serves_only_the_page_files(tmp_path, monkeypatch) -> None:
    server, _ = _server(tmp_path, monkeypatch, share=False)
    pc = _client(server, "127.0.0.1:7869", PC)
    assert pc.get("/static/app.js").status_code == 200
    assert pc.get("/static/style.css").status_code == 200
    # Any other name is not found, however it is written.
    for path in ("/static/..%2F..%2Fdatabase.py", "/static/..%5C..%5Cdatabase.py",
                 "/static/index.html"):
        assert pc.get(path).status_code == 404, path
