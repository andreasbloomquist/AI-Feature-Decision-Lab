"""Local BM25 retrieval.

Access control happens *before* indexing: each role gets its own index built only from the
active documents it may read, so restricted text never enters scoring, term statistics,
snippets or model context for that role.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from threading import Lock

from .access import authorized_documents, check_role
from .corpus import Corpus, Passage

STOPWORDS = set(
    """a an and are as at be by can do does for from get got has have how i if in into is it its
    me my of on or our so than that the their them then there these they this to up was we what
    when where which who whom why will with would you your much many any after before about
    should need needs must may i'm im also only just""".split()
)

TOKEN_RE = re.compile(r"[a-z0-9£$]+(?:[.,][0-9]+)*")


def _stem(tok: str) -> str:
    for suffix in ("ies",):
        if tok.endswith(suffix) and len(tok) > 4:
            return tok[: -len(suffix)] + "y"
    if tok.endswith("s") and not tok.endswith("ss") and len(tok) > 3:
        return tok[:-1]
    return tok


def tokenize(text: str) -> list[str]:
    text = text.lower().replace("’", "'")
    out = []
    for tok in TOKEN_RE.findall(text):
        tok = tok.replace(",", "")
        if tok in STOPWORDS or len(tok) < 2 and not tok.isdigit():
            continue
        out.append(_stem(tok))
    return out


@dataclass(frozen=True)
class ScoredPassage:
    passage: Passage
    score: float


class BM25Index:
    def __init__(self, passages: list[Passage], titles: dict[str, str], k1: float = 1.5, b: float = 0.75):
        self.passages = passages
        self.k1, self.b = k1, b
        # Index the document title and section heading with the text so "travel policy" style
        # queries find the right section.
        self.doc_tokens = [tokenize(f"{titles[p.document_id]} {p.heading} {p.text}") for p in passages]
        self.tf = [Counter(toks) for toks in self.doc_tokens]
        self.lengths = [len(t) for t in self.doc_tokens]
        self.avgdl = (sum(self.lengths) / len(self.lengths)) if self.lengths else 0.0
        df: Counter = Counter()
        for toks in self.doc_tokens:
            df.update(set(toks))
        n = len(passages)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def score(self, query_tokens: list[str], i: int) -> float:
        tf, dl = self.tf[i], self.lengths[i]
        s = 0.0
        for t in query_tokens:
            f = tf.get(t)
            if not f:
                continue
            s += self.idf[t] * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * dl / self.avgdl))
        return s

    def search(self, query: str, k: int) -> list[ScoredPassage]:
        q = tokenize(query)
        scored = [(self.score(q, i), i) for i in range(len(self.passages))]
        scored = [x for x in scored if x[0] > 0]
        scored.sort(key=lambda x: (-x[0], self.passages[x[1]].passage_id))
        return [ScoredPassage(self.passages[i], round(s, 4)) for s, i in scored[:k]]


class Retriever:
    """Role-filtered, active-only retrieval. One cached index per (role, k1, b)."""

    def __init__(self, corpus: Corpus):
        self.corpus = corpus
        self._indexes: dict[tuple, BM25Index] = {}
        self._lock = Lock()

    def index_for(self, role: str, k1: float = 1.5, b: float = 0.75) -> BM25Index:
        check_role(role)
        key = (role, k1, b)
        with self._lock:
            if key not in self._indexes:
                docs = authorized_documents(self.corpus, role, active_only=True)
                passages = [p for d in sorted(docs, key=lambda d: d.document_id) for p in d.passages]
                titles = {d.document_id: d.title for d in docs}
                self._indexes[key] = BM25Index(passages, titles, k1=k1, b=b)
            return self._indexes[key]

    def retrieve(self, query: str, role: str, k: int = 5, k1: float = 1.5, b: float = 0.75) -> list[ScoredPassage]:
        return self.index_for(role, k1, b).search(query, k)
