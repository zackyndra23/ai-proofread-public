from app.core import ratelimit as rl


def test_enforce_rps_allows(flask_app, monkeypatch):
    monkeypatch.setattr(rl, 'ratelimit_incr', lambda key, window: (1, 200.0))
    with flask_app.test_request_context(headers={'X-APIKey': 'k'}):
        resp = rl.enforce_rps('bp', rps=5, window_sec=1)
        assert resp is None


def test_enforce_rps_blocks(flask_app, monkeypatch):
    monkeypatch.setattr(rl.time, 'time', lambda: 100.0)
    monkeypatch.setattr(rl, 'ratelimit_incr', lambda key, window: (6, 110.0))
    with flask_app.test_request_context(headers={'X-APIKey': 'k'}):
        resp = rl.enforce_rps('bp', rps=5, window_sec=1)
        assert isinstance(resp, tuple)
        body, status, headers = resp
        assert status == 429
        assert headers['Retry-After'] == '10'
        data = body.get_json()
        assert data['error'] == 'LLM_RATE_LIMITED'
