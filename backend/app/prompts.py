"""Versioned prompt templates stored in config/prompts/*.md."""

from __future__ import annotations

from dataclasses import dataclass
from functools import cache

import yaml

from .settings import CONFIG_DIR


@dataclass(frozen=True)
class PromptTemplate:
    prompt_id: str
    version: str
    system: str
    user: str
    path: str

    def render(self, **values) -> tuple[str, str]:
        return self.system.format(**values), self.user.format(**values)


@cache
def load_prompt(relative_path: str) -> PromptTemplate:
    path = CONFIG_DIR / relative_path
    raw = path.read_text(encoding="utf-8")
    _, fm, body = raw.split("---", 2)
    meta = yaml.safe_load(fm)
    system_part, _, user_part = body.partition("[user]")
    system = system_part.replace("[system]", "", 1).strip()
    return PromptTemplate(
        meta["prompt_id"], meta["version"], system, user_part.strip(), str(path.relative_to(CONFIG_DIR.parent))
    )


@cache
def load_approach_config(name: str) -> dict:
    return yaml.safe_load((CONFIG_DIR / "approaches" / f"{name}.yaml").read_text())
