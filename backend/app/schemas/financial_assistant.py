"""Financial Assistant API schemas."""

from __future__ import annotations

from datetime import date

from app.schemas.base import APIModel


class AssistantPeriod(APIModel):
    period_start: date
    period_end: date


class InsightMetric(APIModel):
    kind: str
    label: str | None = None
    current: float | int | None = None
    previous: float | int | None = None
    change_pct: float | None = None
    unit: str = "currency"


class AssistantInsight(APIModel):
    id: str
    severity: str
    category: str
    title: str
    explanation: str
    metric: InsightMetric | None = None
    actionable: bool = False
    priority: int = 0
    generated_at: str | None = None


class AssistantQuestion(APIModel):
    intent: str
    question: str


class AssistantOverviewResponse(APIModel):
    provider: str
    provider_name: str
    generated_at: str
    period: AssistantPeriod
    currency: str
    has_data: bool
    greeting: str
    overview: str
    insights: list[AssistantInsight]
    questions: list[AssistantQuestion]


class AssistantAskRequest(APIModel):
    question: str
    intent: str | None = None
    goal_id: int | None = None


class AssistantFact(APIModel):
    label: str
    value: float | int | str | None = None
    display: str


class AssistantAskResponse(APIModel):
    intent: str
    question: str
    recognized: bool
    answer: str
    estimate: bool
    source: str
    facts: list[AssistantFact] = []
    metric: InsightMetric | None = None
    generated_at: str | None = None