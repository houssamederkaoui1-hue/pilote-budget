"""Assistant response-layer providers (rule-based today, LLM-ready).

The provider **only rewrites presentation text** for numbers already computed by
the deterministic engine. It never fabricates figures, never sees raw ledger
rows by default and never sends anything anywhere.

``RuleBasedAssistant`` is the only shipped provider and simply keeps the
engine's wording (its draft methods return ``None``). An LLM provider can be
added later by implementing the same methods in ``PROVIDERS``; enabling it must
be an explicit configuration step so no unexpected traffic can start silently.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.services.profile_service import ProfileService

ASSISTANT_ENGINE_PREFERENCE = "assistant_engine"
DEFAULT_ENGINE_ID = "rules"


class AssistantProvider:
    """Contract every assistant response layer must satisfy.

    - ``id`` — stable machine identifier stored in profile preferences.
    - ``name`` — human label surfaced in the API response.
    - ``draft_overview`` / ``draft_insight_text`` — optional *rewording* hooks:
      all numbers in the returned text must be the engine's. Returning ``None``
      keeps the deterministic wording.
    """

    id: str = DEFAULT_ENGINE_ID
    name: str = "Rules engine"

    def available(self) -> bool:
        return True

    def draft_overview(self, overview: str) -> str:
        return overview

    def draft_insight_text(self, title: str, explanation: str):
        return None


class RuleBasedAssistant(AssistantProvider):
    id = DEFAULT_ENGINE_ID
    name = "Rules engine"


class LLMAssistant(AssistantProvider):
    """Placeholder for a future LLM response layer (not wired anywhere).

    ``available`` is False until deliberately enabled at build time, so it can
    never be selected by accident and no request is ever sent without an
    explicit opt-in.
    """

    id = "llm"
    name = "Language model"
    _configured = False

    def available(self) -> bool:
        return self._configured


PROVIDERS: dict[str, AssistantProvider] = {
    RuleBasedAssistant.id: RuleBasedAssistant(),
    LLMAssistant.id: LLMAssistant(),
}


def get_assistant_provider(session: Session) -> AssistantProvider:
    """Resolve the configured engine, falling back to the rules engine."""
    profile = ProfileService(session).get()
    preference = profile.preferences or {}
    engine = preference.get(ASSISTANT_ENGINE_PREFERENCE, DEFAULT_ENGINE_ID)
    candidate = PROVIDERS.get(engine)
    if candidate is None or not candidate.available():
        return PROVIDERS[DEFAULT_ENGINE_ID]
    return candidate