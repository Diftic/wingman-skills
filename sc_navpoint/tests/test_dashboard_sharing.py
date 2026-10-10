import base64
import io
from PIL import Image
import numpy as np
import pytest


def test_phone_qr_decodes_to_the_lan_dashboard():
    from navpoint_ui.sharing import qr_png_base64
    import cv2
    url = 'http://192.168.1.20:7869'
    png = base64.b64decode(qr_png_base64(url))
    image = Image.open(io.BytesIO(png)).convert('RGB')
    # Match Accountant's compact three-pixel modules and four-module border.
    assert image.size == (99, 99)
    decoded, points, _ = cv2.QRCodeDetector().detectAndDecode(np.asarray(image))
    assert decoded == url
    assert points is not None


def test_dashboard_lan_url_uses_actual_server_port(monkeypatch):
    from navpoint_ui.app import NavPointServer
    from navpoint_ui import sharing
    monkeypatch.setattr(sharing, 'get_lan_ip', lambda: '192.168.1.20')
    server = NavPointServer(db=None, port=8765)
    assert server.lan_url == 'http://192.168.1.20:8765'
    monkeypatch.setattr(sharing, 'get_lan_ip', lambda: '')
    assert server.lan_url == ''
    assert server.url == 'http://127.0.0.1:8765'


def test_lan_lookup_failure_does_not_advertise_loopback(monkeypatch):
    from navpoint_ui import sharing
    def unavailable(*args):
        raise OSError('No network')
    monkeypatch.setattr(sharing.socket, 'socket', unavailable)
    assert sharing.get_lan_ip() == ''
