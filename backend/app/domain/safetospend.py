"""Safe-to-Spend formula (pure).

The engine answers one question: of the money currently available, how much
can be spent each remaining day of the period without touching committed
amounts? The formula is deliberately explicit and auditable:

    available          money you currently have access to
  - obligations        upcoming fixed / recurring bills due before the next
                       period
  - planned_savings    the savings bucket set aside for this period
  - reserve            a safety reserve the user wants to keep untouched
  --------------------------------------------------------------
  = discretionary      spendable money for the rest of the period
  / remaining_days     calendar days left in the period (inclusive)
  = daily budget

``remaining_days`` uses the inclusive day count so a period with the last
day remaining still produces a `1` for the per-day figure.
"""

from __future__ import annotations


def calculate(
    available: float,
    obligations: float,
    planned_savings: float,
    reserve: float,
    remaining_days: int,
) -> dict:
    """Compute the Safe-to-Spend breakdown.

    Returns the committed/discretionary/daily amounts plus a transparent
    human-readable explanation. Discretionary money is clamped at zero
    (a negative spendable amount would be a fabricated number).
    """
    available = round(float(available), 2)
    obligations = round(float(obligations), 2)
    planned_savings = round(float(planned_savings), 2)
    reserve = round(float(reserve), 2)

    committed = round(obligations + planned_savings + reserve, 2)
    discretionary = round(max(0.0, available - committed), 2)

    daily = (
        round(discretionary / remaining_days, 2)
        if remaining_days and remaining_days > 0
        else None
    )

    explanation = (
        f"Available {available:.2f} - upcoming obligations {obligations:.2f} "
        f"- planned savings {planned_savings:.2f} - reserve {reserve:.2f} "
        f"= discretionary {discretionary:.2f} "
        f"spread over {remaining_days} remaining day(s) "
        f"= {daily:.2f} per day."
        if daily is not None
        else (
            f"Available {available:.2f} - upcoming obligations {obligations:.2f} "
            f"- planned savings {planned_savings:.2f} - reserve {reserve:.2f} "
            f"= discretionary {discretionary:.2f} (daily figure unavailable until "
            "the period has remaining days)."
        )
    )

    return {
        "available": available,
        "committed": committed,
        "obligations": obligations,
        "planned_savings": planned_savings,
        "reserve": reserve,
        "discretionary": discretionary,
        "remaining_days": remaining_days,
        "daily": daily,
        "explanation": explanation,
    }