"""Role-based access control. Applied before retrieval, to model context, to citations and to previews."""
from __future__ import annotations

from .corpus import Corpus, Document

# Each role maps to the access groups it belongs to. Documents list the groups allowed to read them.
ROLE_GROUPS: dict[str, set[str]] = {
    "employee": {"employee"},
    "hr": {"employee", "HR"},
    "finance": {"employee", "Finance"},
    "admin": {"employee", "HR", "Finance", "admin"},
}

ROLE_LABELS = {
    "employee": "Employee",
    "hr": "HR",
    "finance": "Finance",
    "admin": "Administrator",
}


class UnknownRole(ValueError):
    pass


def check_role(role: str) -> str:
    if role not in ROLE_GROUPS:
        raise UnknownRole(f"unknown role {role!r}")
    return role


def can_access(role: str, doc: Document) -> bool:
    return bool(ROLE_GROUPS[check_role(role)] & set(doc.access_groups))


def authorized_documents(corpus: Corpus, role: str, *, active_only: bool) -> list[Document]:
    return [
        d for d in corpus.documents.values()
        if can_access(role, d) and (d.is_active or not active_only)
    ]


def restricted_document_ids(corpus: Corpus, role: str) -> set[str]:
    return {d.document_id for d in corpus.documents.values() if not can_access(role, d)}
