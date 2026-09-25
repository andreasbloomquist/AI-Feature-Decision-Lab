"""LLM providers.

- AnthropicProvider: the real provider, via the official `anthropic` SDK.
- FixtureProvider:   replays saved example outputs so the UI works without a key. Its outputs
                     are illustrative, carry no latency or token usage, and are always labeled.
- ScriptedProvider:  test double.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .settings import DATA_DIR, Settings

FIXTURE_FILE = DATA_DIR / "fixtures" / "llm_outputs.json"


@dataclass
class LLMResult:
    text: str
    model: str
    input_tokens: int | None
    output_tokens: int | None
    latency_ms: float | None
    stop_reason: str | None = None


class LLMError(Exception):
    """A model call failed. `kind` is a short machine-readable category shown in the UI."""

    def __init__(self, kind: str, message: str, latency_ms: float | None = None):
        super().__init__(message)
        self.kind = kind
        self.message = message
        self.latency_ms = latency_ms


class LLMProvider(Protocol):
    name: str
    model: str
    is_fixture: bool

    def generate(self, system: str, user: str, *, max_tokens: int, fixture_key: str | None = None) -> LLMResult: ...


def fixture_key(approach: str, question: str, role: str) -> str:
    return f"{approach}|{role}|{' '.join(question.lower().split())}"


class AnthropicProvider:
    is_fixture = False

    def __init__(self, settings: Settings, model: str | None = None):
        import anthropic  # imported lazily so fixture mode works without the SDK configured

        self._anthropic = anthropic
        self.name = "anthropic"
        self.model = model or settings.model
        self.effort = settings.effort
        # The SDK reads ANTHROPIC_API_KEY from the environment; we never pass or log it.
        self.client = anthropic.Anthropic(timeout=settings.timeout_s, max_retries=settings.max_retries)

    def generate(self, system: str, user: str, *, max_tokens: int, fixture_key: str | None = None) -> LLMResult:
        a = self._anthropic
        kwargs = dict(
            model=self.model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        if self.effort:
            kwargs["output_config"] = {"effort": self.effort}
        start = time.perf_counter()
        try:
            resp = self.client.messages.create(**kwargs)
        except a.APITimeoutError as e:
            raise LLMError("timeout", "model request timed out", _ms(start)) from e
        except a.RateLimitError as e:
            raise LLMError("rate_limited", "provider rate limit reached", _ms(start)) from e
        except a.AuthenticationError as e:
            raise LLMError("auth", "provider rejected the API key", _ms(start)) from e
        except a.BadRequestError as e:
            raise LLMError("bad_request", f"provider rejected the request: {e.message}"[:300], _ms(start)) from e
        except a.APIStatusError as e:
            raise LLMError("api_error", f"provider returned HTTP {e.status_code}", _ms(start)) from e
        except a.APIConnectionError as e:
            raise LLMError("connection", "could not reach the provider", _ms(start)) from e
        latency = _ms(start)
        if resp.stop_reason == "refusal":
            raise LLMError("refusal", "model declined the request", latency)
        text = "".join(getattr(b, "text", "") for b in resp.content if b.type == "text")
        usage = getattr(resp, "usage", None)
        in_tok = out_tok = None
        if usage is not None and usage.input_tokens is not None and usage.output_tokens is not None:
            in_tok = (
                usage.input_tokens
                + (getattr(usage, "cache_creation_input_tokens", 0) or 0)
                + (getattr(usage, "cache_read_input_tokens", 0) or 0)
            )
            out_tok = usage.output_tokens
        return LLMResult(text, self.model, in_tok, out_tok, latency, resp.stop_reason)


class FixtureProvider:
    """Replays saved example outputs keyed by approach, role and question."""

    is_fixture = True

    def __init__(self, path: Path = FIXTURE_FILE):
        self.name = "fixture"
        self.path = path
        data = json.loads(path.read_text()) if path.exists() else {"outputs": {}}
        self.meta = {k: v for k, v in data.items() if k != "outputs"}
        self.model = self.meta.get("model_label", "fixture")
        self.outputs: dict[str, dict] = data.get("outputs", {})

    def generate(self, system: str, user: str, *, max_tokens: int, fixture_key: str | None = None) -> LLMResult:
        entry = self.outputs.get(fixture_key or "")
        if entry is None:
            raise LLMError(
                "fixture_missing",
                "Fixture mode has saved responses only for the sample questions. Add an API key to ask anything.",
            )
        if entry.get("error"):
            raise LLMError(entry["error"], entry.get("message", "simulated failure (fixture)"))
        # No latency or token usage: fixture outputs were not measured.
        return LLMResult(entry["text"], self.model, None, None, None, "fixture")


class ScriptedProvider:
    """Test double: `script(system, user) -> str | LLMResult`, or raise LLMError."""

    is_fixture = False

    def __init__(
        self,
        script: Callable[[str, str], object],
        model: str = "claude-opus-5",
        usage: tuple[int, int] | None = (1000, 100),
    ):
        self.name = "scripted"
        self.model = model
        self.script = script
        self.usage = usage

    def generate(self, system: str, user: str, *, max_tokens: int, fixture_key: str | None = None) -> LLMResult:
        start = time.perf_counter()
        out = self.script(system, user)
        if isinstance(out, LLMResult):
            return out
        in_tok, out_tok = self.usage if self.usage else (None, None)
        return LLMResult(str(out), self.model, in_tok, out_tok, _ms(start))


def _ms(start: float) -> float:
    return round((time.perf_counter() - start) * 1000, 1)


def make_provider(settings: Settings, *, judge: bool = False) -> LLMProvider:
    if not settings.live_available:
        return FixtureProvider()
    if settings.provider == "anthropic":
        return AnthropicProvider(settings, model=settings.judge_model if judge else settings.model)
    raise ValueError(f"unsupported LLM_PROVIDER {settings.provider!r}")
