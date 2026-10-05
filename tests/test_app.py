import importlib

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("OF_DATA", "demo")
    monkeypatch.delenv("OF_TOKEN", raising=False)
    import dashboard.app as app_mod
    importlib.reload(app_mod)
    return TestClient(app_mod.app)


@pytest.mark.parametrize("qs", ["ratio=nan", "ratio=inf", "ratio=0.5", "bar=999999999", "bar=1", "stack=-999999",
                                "row=-1", "mode=evil"])
def test_ws_rejects_garbage_params(client, qs):
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(f"/ws/footprint?sym=ES&mode=sim&{qs}") as ws:
            ws.receive_json()


@pytest.mark.parametrize("url", ["/api/chart?tf=2h", "/api/chart?days=999999", "/api/chart?days=-3",
                                 "/api/watchlist?tf=bad"])
def test_http_rejects_garbage_params(client, url):
    assert client.get(url).status_code == 422


def test_chart_ok(client):
    r = client.get("/api/chart?sym=ES&tf=4h&days=30")
    assert r.status_code == 200 and r.json()["bars"]


def test_token_required_when_set(monkeypatch):
    monkeypatch.setenv("OF_DATA", "demo")
    monkeypatch.setenv("OF_TOKEN", "s3cret")
    import dashboard.app as app_mod
    importlib.reload(app_mod)
    c = TestClient(app_mod.app)
    assert c.get("/api/symbols").status_code == 401
    assert c.get("/api/symbols", headers={"Authorization": "Bearer nope"}).status_code == 401
    assert c.get("/api/symbols", headers={"Authorization": "Bearer s3cret"}).status_code == 200
    assert c.get("/?token=s3cret").status_code == 200       # sets the cookie...
    assert c.get("/api/symbols").status_code == 200          # ...so later calls work
    with pytest.raises(WebSocketDisconnect):
        with TestClient(app_mod.app).websocket_connect("/ws/footprint?sym=ES&mode=sim") as ws:
            ws.receive_json()
    with c.websocket_connect("/ws/footprint?sym=ES&mode=sim") as ws:  # cookie carries over
        assert ws.receive_json()["type"] == "snapshot"
    monkeypatch.delenv("OF_TOKEN")
    importlib.reload(app_mod)
