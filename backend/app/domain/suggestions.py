"""Deterministic suggestion ranking (pure logic, no DB).

Quick Add and the transaction form call ``rank_suggestions`` with usage
aggregates so far every choice is reproducible and testable in isolation:

usage::

    {"mcdonalds lunch": [{"category_id": 3, "category_name": "Dining out",
                          "count": 4}, ...], ...}

totals::

    [{"category_id": 1, "category_name": "Groceries", "count": 22}, ...]

The ranker never queries; it only reorders what the service already loaded.
"""

from __future__ import annotations

import re
import unicodedata

_SPACES = re.compile(r"\s+")


def normalize_description(text: str) -> str:
    """Lowercase, strip accents and collapse punctuation/whitespace."""
    if not text:
        return ""
    value = unicodedata.normalize("NFKD", text)
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = re.sub(r"[^a-z0-9]+", " ", value.lower())
    return _SPACES.sub(" ", value).strip()


def describe_tokens(text: str) -> frozenset[str]:
    return frozenset(normalize_description(text).split())


def rank_suggestions(
    query: str,
    usage: dict[str, list[dict[str, object]]],
    totals: list[dict[str, object]],
    limit: int = 5,
) -> list[dict[str, object]]:
    """Rank category suggestions for ``query``.

    Returns up to ``limit`` entries of::

        {"category_id": int, "category_name": str,
         "confidence": "exact" | "similar" | "popular",
         "evidence": str | None}

    Confidence tiers: exact (same normalized description was categorized
    before), similar (shared tokens with a previously categorized
    description), popular (a frequently used category with no text match).
    """
    query_norm = normalize_description(query)
    ranked: list[dict[str, object]] = []
    seen: set[int] = set()

    def add(category_id: int, category_name: str, score: float,
            confidence: str, evidence: str | None) -> None:
        if category_id in seen:
            return
        seen.add(category_id)
        ranked.append(
            {
                "category_id": category_id,
                "category_name": category_name,
                "confidence": confidence,
                "evidence": evidence,
                "score": round(score, 3),
            }
        )

    if query_norm and query_norm in usage:
        categories = sorted(
            usage[query_norm], key=lambda row: -(row.get("count") or 0)
        )
        for position, row in enumerate(categories):
            count = row.get("count") or 0
            evidence = (
                f"Used {count} time{'s' if count != 1 else ''} for "
                f"'{row.get('description') or query}'"
            )
            add(
                row["category_id"],
                row["category_name"],
                score=count * 10 + (limit - position),
                confidence="exact",
                evidence=evidence,
            )
        if ranked:
            return ranked[:limit]

    if query_norm:
        query_tokens = describe_tokens(query_norm)
        similar_scores: list[tuple[float, dict]] = []
        if query_tokens:
            for desc_norm, categories in usage.items():
                tokens = frozenset(desc_norm.split())
                overlap = query_tokens & tokens
                if not overlap:
                    continue
                similarity = len(overlap) / max(len(query_tokens), len(tokens), 1)
                if similarity <= 0:
                    continue
                for row in categories:
                    count = row.get("count") or 0
                    similar_scores.append(
                        (
                            count * (0.5 + 0.5 * similarity),
                            row,
                            similarity,
                        )
                    )
        similar_scores.sort(key=lambda item: -item[0])
        for score, row, similarity in similar_scores:
            evidence = (
                f"Similar to '{row.get('description')}' — used "
                f"{row.get('count')} time{'s' if row.get('count') != 1 else ''}"
            )
            add(
                row["category_id"],
                row["category_name"],
                score=score,
                confidence="similar",
                evidence=evidence,
            )
        if ranked:
            return ranked[:limit]

    for row in totals:
        add(
            row["category_id"],
            row["category_name"],
            score=row.get("count") or 0,
            confidence="popular",
            evidence=(
                f"Used {row.get('count')} time{'s' if row.get('count') != 1 else ''} overall"
            ),
        )
    return ranked[:limit]