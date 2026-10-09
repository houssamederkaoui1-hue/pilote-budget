"""Pure budget health math shared by the budget engine and its tests."""

from __future__ import annotations

BUDGET_STATUS = {
    "over": "over",
    "approaching": "approaching",
    "healthy": "healthy",
    "none": "none",
}


def utilization(actual: float, planned: float) -> tuple[float | None, bool, str]:
    """Budget usage for one bucket.

    Returns ``(pct_used, over_budget, status)``:

    - ``pct_used`` is ``actual / planned * 100`` once a plan exists;
    - it is ``None`` for spending outside any plan (status ``over``);
    - status is ``over`` when spending exceeds the plan, ``approaching`` when
      the bucket sits at 80-100%, ``healthy`` under that, ``none`` when idle.
    """
    planned = float(planned or 0.0)
    actual = float(actual or 0.0)

    if planned > 0:
        pct = round(actual / planned * 100, 1)
        if actual > planned:
            return pct, True, "over"
        if pct >= 80:
            return pct, False, "approaching"
        return pct, False, "healthy"

    # No plan at all: any spend is unbudgeted and instantly "over".
    if actual > 0:
        return None, True, "over"
    return 0.0, False, "none"


def bucket_opposite_budget(actual: float) -> bool:
    """Convenience flag used by visual states (over/approaching)."""
    _, over, status = utilization(actual, 0)
    return over or status == "over"