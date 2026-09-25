import pytest

from app.approaches import ApproachContext, build_approaches
from app.corpus import get_corpus
from app.db import Database
from app.retrieval import Retriever


@pytest.fixture
def corpus():
    return get_corpus()


@pytest.fixture
def retriever(corpus):
    return Retriever(corpus)


@pytest.fixture
def make_approaches(corpus, retriever):
    def _make(llm):
        return build_approaches(ApproachContext(corpus=corpus, retriever=retriever, llm=llm))

    return _make


@pytest.fixture
def db(tmp_path):
    return Database(tmp_path / "test.sqlite3")


@pytest.fixture
def client(tmp_path, monkeypatch):
    """API client with an isolated database, in fixture mode (no key)."""
    monkeypatch.setenv("LAB_DB_PATH", str(tmp_path / "api.sqlite3"))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("FIXTURE_MODE", "1")
    from fastapi.testclient import TestClient

    from app import main

    main.reset_caches()
    with TestClient(main.app) as c:
        yield c
    main.reset_caches()
