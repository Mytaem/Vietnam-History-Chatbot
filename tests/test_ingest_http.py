"""Test ingest/http.py: cache phản hồi API (không gọi mạng)."""
from hgr.ingest.http import ApiClient


def test_cache_avoids_second_request(tmp_path, monkeypatch):
    client = ApiClient("https://example.invalid/api.php", "test-agent", cache_dir=tmp_path)
    calls = []
    monkeypatch.setattr(client, "_fetch", lambda params: calls.append(params) or {"ok": params["q"]})
    assert client.get({"q": "Ngô Quyền"}) == {"ok": "Ngô Quyền"}
    assert client.get({"q": "Ngô Quyền"}) == {"ok": "Ngô Quyền"}
    assert client.get({"q": "Lê Lợi"}) == {"ok": "Lê Lợi"}
    assert len(calls) == 2


def test_no_cache_dir_always_fetches(monkeypatch):
    client = ApiClient("https://example.invalid/api.php", "test-agent")
    calls = []
    monkeypatch.setattr(client, "_fetch", lambda params: calls.append(params) or {})
    client.get({"q": 1}); client.get({"q": 1})
    assert len(calls) == 2
