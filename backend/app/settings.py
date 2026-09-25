"""Runtime settings read from environment variables.

Secrets are read here and nowhere else. `public_settings()` is the only view that leaves
the process (API responses, saved runs), and it never includes key material.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = ROOT / "config"
DATA_DIR = ROOT / "data"
RESULTS_DIR = ROOT / "results"

PROVIDER_KEY_VARS = {"anthropic": "ANTHROPIC_API_KEY"}


def _load_dotenv() -> None:
    """Load KEY=VALUE pairs from ROOT/.env without overriding the real environment."""
    path = ROOT / ".env"
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


@dataclass
class Settings:
    provider: str = "anthropic"
    model: str = "claude-opus-5"
    effort: str | None = "low"
    judge_model: str = "claude-sonnet-5"
    timeout_s: float = 20.0
    max_retries: int = 1
    db_path: Path = field(default_factory=lambda: RESULTS_DIR / "lab.sqlite3")
    force_fixture: bool = False

    @property
    def api_key_env_var(self) -> str:
        return PROVIDER_KEY_VARS.get(self.provider, "")

    @property
    def live_available(self) -> bool:
        """True when a provider key is configured. The key value itself is never exposed."""
        if self.force_fixture:
            return False
        var = self.api_key_env_var
        return bool(var and os.environ.get(var))

    @property
    def mode(self) -> str:
        return "live" if self.live_available else "fixture"


def load_settings() -> Settings:
    _load_dotenv()
    effort = os.environ.get("LLM_EFFORT", "low").strip()
    return Settings(
        provider=os.environ.get("LLM_PROVIDER", "anthropic").strip().lower(),
        model=os.environ.get("LLM_MODEL", "claude-opus-5").strip(),
        effort=effort or None,
        judge_model=os.environ.get("JUDGE_MODEL", "claude-sonnet-5").strip(),
        timeout_s=float(os.environ.get("LLM_TIMEOUT_S", "20")),
        max_retries=int(os.environ.get("LLM_MAX_RETRIES", "1")),
        db_path=Path(os.environ.get("LAB_DB_PATH", str(RESULTS_DIR / "lab.sqlite3"))),
        force_fixture=os.environ.get("FIXTURE_MODE", "").lower() in {"1", "true", "yes"},
    )


def public_settings(s: Settings) -> dict:
    """Settings safe to show in the browser or store with a run. Never includes secrets."""
    return {
        "mode": s.mode,
        "live_available": s.live_available,
        "provider": s.provider,
        "model": s.model,
        "effort": s.effort,
        "judge_model": s.judge_model,
        "timeout_s": s.timeout_s,
        "max_retries": s.max_retries,
        "api_key_env_var": s.api_key_env_var,
    }
