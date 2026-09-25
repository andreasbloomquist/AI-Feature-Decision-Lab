"""The UI file server must never serve files outside frontend/dist (e.g. .env with the API key)."""

import pytest

from app.main import static_file


@pytest.fixture
def dist(tmp_path):
    root = tmp_path / "dist"
    (root / "assets").mkdir(parents=True)
    (root / "index.html").write_text("<html></html>")
    (root / "assets" / "app.js").write_text("js")
    (tmp_path / ".env").write_text("ANTHROPIC_API_KEY=sk-secret")
    return root


def test_serves_files_inside_root(dist):
    assert static_file(dist, "index.html") == (dist / "index.html").resolve()
    assert static_file(dist, "assets/app.js") == (dist / "assets" / "app.js").resolve()


@pytest.mark.parametrize("path", ["../.env", "assets/../../.env", "/etc/passwd", "", "assets", "missing.js"])
def test_rejects_traversal_absolute_directories_and_missing(dist, path):
    assert static_file(dist, path) is None


def test_encoded_traversal_over_http_returns_index_not_secret(tmp_path, monkeypatch, dist):
    from fastapi.testclient import TestClient

    from app import main

    if not main.FRONTEND_DIST.exists():
        pytest.skip("frontend not built; route not mounted")
    monkeypatch.setenv("LAB_DB_PATH", str(tmp_path / "t.sqlite3"))
    monkeypatch.setenv("FIXTURE_MODE", "1")
    main.reset_caches()
    with TestClient(main.app) as c:
        for url in ("/..%2F..%2FMakefile", "/%2E%2E/%2E%2E/backend/app/settings.py"):
            r = c.get(url)
            assert "PY ?=" not in r.text and "Runtime settings" not in r.text
    main.reset_caches()
