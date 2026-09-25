"""Load the Markdown policy corpus and split it into citable passages."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import yaml

from .settings import DATA_DIR

CORPUS_DIR = DATA_DIR / "corpus"


@dataclass(frozen=True)
class Passage:
    passage_id: str  # "<document_id>#<n>"
    document_id: str
    index: int
    heading: str
    text: str


@dataclass
class Document:
    document_id: str
    title: str
    owner: str
    effective_date: str
    status: str
    access_groups: list[str]
    country: list[str]
    superseded_by: str | None
    supersedes: str | None
    body: str
    passages: list[Passage] = field(default_factory=list)

    @property
    def is_active(self) -> bool:
        return self.status == "active"

    def metadata(self) -> dict:
        return {
            "document_id": self.document_id,
            "title": self.title,
            "owner": self.owner,
            "effective_date": self.effective_date,
            "status": self.status,
            "superseded_by": self.superseded_by,
            "supersedes": self.supersedes,
            "access_groups": self.access_groups,
            "country": self.country,
        }


class Corpus:
    def __init__(self, documents: list[Document], version: str):
        self.documents = {d.document_id: d for d in documents}
        self.version = version
        self.passages = {p.passage_id: p for d in documents for p in d.passages}

    def get(self, document_id: str) -> Document | None:
        return self.documents.get(document_id)

    def passage(self, passage_id: str) -> Passage | None:
        return self.passages.get(passage_id)


def _split_passages(document_id: str, body: str) -> list[Passage]:
    """One passage per '## ' section. Text before the first section becomes an overview passage."""
    sections: list[tuple[str, list[str]]] = [("Overview", [])]
    for line in body.splitlines():
        if line.startswith("## "):
            sections.append((line[3:].strip(), []))
        elif line.startswith("# "):
            continue
        else:
            sections[-1][1].append(line)
    passages = []
    n = 0
    for heading, lines in sections:
        text = "\n".join(lines).strip()
        if not text:
            continue
        n += 1
        passages.append(Passage(f"{document_id}#{n}", document_id, n, heading, text))
    return passages


def parse_document(raw: str) -> Document:
    if not raw.startswith("---"):
        raise ValueError("document is missing front matter")
    _, fm, body = raw.split("---", 2)
    meta = yaml.safe_load(fm)
    required = ["document_id", "title", "owner", "effective_date", "status", "access_groups"]
    missing = [k for k in required if k not in meta]
    if missing:
        raise ValueError(f"front matter missing {missing}")
    if meta["status"] not in {"active", "superseded"}:
        raise ValueError(f"invalid status {meta['status']!r}")
    if meta["status"] == "superseded" and not meta.get("superseded_by"):
        raise ValueError("superseded documents need superseded_by")
    country = meta.get("country") or []
    if isinstance(country, str):
        country = [country]
    doc = Document(
        document_id=meta["document_id"],
        title=meta["title"],
        owner=meta["owner"],
        effective_date=str(meta["effective_date"]),
        status=meta["status"],
        access_groups=list(meta["access_groups"]),
        country=list(country),
        superseded_by=meta.get("superseded_by"),
        supersedes=meta.get("supersedes"),
        body=body.strip(),
    )
    doc.passages = _split_passages(doc.document_id, doc.body)
    return doc


def load_corpus(directory: Path = CORPUS_DIR) -> Corpus:
    files = sorted(directory.glob("*.md"))
    digest = hashlib.sha256()
    docs = []
    for f in files:
        raw = f.read_text(encoding="utf-8")
        digest.update(f.name.encode() + b"\0" + raw.encode())
        docs.append(parse_document(raw))
    return Corpus(docs, version=f"corpus-{digest.hexdigest()[:12]}")


@lru_cache(maxsize=1)
def get_corpus() -> Corpus:
    return load_corpus()
