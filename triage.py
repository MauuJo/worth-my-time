from __future__ import annotations

from typing import Any

CLAIMED_PENALTY = -3
COMPETING_PR_PENALTY = -3
INACTIVE_DAYS = 60
INACTIVE_PENALTY = -2
NEWCOMER_RATE_THRESHOLD = 0.5
NEWCOMER_BONUS = 2
MEDIAN_MERGE_DAYS = 7
MEDIAN_MERGE_BONUS = 1
ISSUE_BODY_LENGTH = 200
ISSUE_BODY_BONUS = 1
CONTRIBUTING_BONUS = 1


def verdict(
    issue: dict[str, Any] | None,
    claimed_flag: bool | None,
    n_prs: int | None,
    health: dict[str, Any] | None,
    days_since_push: int | None,
    has_contributing: bool | None,
) -> tuple[str, list[str]]:
    """Return a deterministic label and short explanation for a candidate issue."""
    score = 0
    reasons: list[str] = []

    if claimed_flag is True:
        score += CLAIMED_PENALTY
        reasons.append("Issue looks claimed.")
    elif claimed_flag is None:
        reasons.append("not enough data: claim status missing.")

    if n_prs is not None:
        if n_prs > 0:
            score += COMPETING_PR_PENALTY
            reasons.append("Competing PRs are open.")
    else:
        reasons.append("not enough data: competing PRs missing.")

    if days_since_push is not None:
        if days_since_push >= INACTIVE_DAYS:
            score += INACTIVE_PENALTY
            reasons.append("Repo inactive for 60+ days.")
    else:
        reasons.append("not enough data: repo push history missing.")

    if health is not None:
        newcomer_rate = health.get("newcomer_merge_rate")
        if newcomer_rate is not None and newcomer_rate >= NEWCOMER_RATE_THRESHOLD:
            score += NEWCOMER_BONUS
            reasons.append("Newcomer merge rate is strong.")
        median_days = health.get("median_days_to_merge")
        if median_days is not None and median_days <= MEDIAN_MERGE_DAYS:
            score += MEDIAN_MERGE_BONUS
            reasons.append("Median merge time is fast.")
    else:
        reasons.append("not enough data: repo health missing.")

    issue_body = (issue or {}).get("body") or ""
    if len(issue_body) > ISSUE_BODY_LENGTH:
        score += ISSUE_BODY_BONUS
        reasons.append("Issue description is detailed.")
    elif issue_body == "":
        reasons.append("not enough data: issue body missing.")

    if has_contributing is True:
        score += CONTRIBUTING_BONUS
        reasons.append("Repo has CONTRIBUTING guidance.")
    elif has_contributing is None:
        reasons.append("not enough data: CONTRIBUTING status missing.")

    if score >= 2:
        label = "Go"
    elif score >= 0:
        label = "Risky"
    else:
        label = "Skip"

    return label, reasons
