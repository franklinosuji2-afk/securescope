"""What moving to a lower plan would change. Read-only: it counts and explains, it never changes or deletes."""

from __future__ import annotations

from dataclasses import dataclass

from app.billing.plans import Plan
from app.repositories.billing import PlanUsage


@dataclass(frozen=True, slots=True)
class Effect:
    key: str
    # "over_limit": more than the lower plan allows; "feature_lost": a feature the lower plan does not include;
    # "history": data that the lower plan's history period would clear.
    kind: str
    message: str
    used: int
    limit: int | None


def downgrade_effects(current: Plan, target: Plan, usage: PlanUsage) -> list[Effect]:
    effects: list[Effect] = []
    if target.max_websites is not None and usage.websites > target.max_websites:
        effects.append(
            Effect(
                "websites",
                "over_limit",
                f"You have {usage.websites} websites and {target.name} includes {target.max_websites}. "
                "They all stay, but you could not add another until you are within the limit.",
                usage.websites,
                target.max_websites,
            )
        )
    if target.scans_per_month is not None and usage.scans_this_month > target.scans_per_month:
        effects.append(
            Effect(
                "scans",
                "over_limit",
                f"You have started {usage.scans_this_month} scans this month and {target.name} includes "
                f"{target.scans_per_month}. No new scans could start until the month renews.",
                usage.scans_this_month,
                target.scans_per_month,
            )
        )
    if target.history_days < current.history_days and usage.scans_older_than_history:
        effects.append(
            Effect(
                "history",
                "history",
                f"{target.name} keeps {target.history_days} days of scan history. "
                f"{usage.scans_older_than_history} scans older than that would be cleared by the "
                "automatic clean-up, with their reports.",
                usage.scans_older_than_history,
                None,
            )
        )
    if current.scheduled_scans and not target.scheduled_scans:
        effects.append(
            Effect(
                "scheduled_scans",
                "feature_lost",
                f"Scheduled scans and API tokens are not part of {target.name}. "
                f"{usage.schedules} schedules and {usage.api_tokens} API tokens would stop working.",
                usage.schedules + usage.api_tokens,
                None,
            )
        )
    if current.can_invite and not target.can_invite:
        effects.append(
            Effect(
                "team",
                "feature_lost",
                f"Inviting people is not part of {target.name}. "
                f"{usage.members} members stay, and {usage.pending_invitations} open invitations "
                "could no longer be used to add people.",
                usage.members,
                None,
            )
        )
    if current.client_workspace and not target.client_workspace:
        effects.append(
            Effect(
                "clients",
                "feature_lost",
                f"Client workspaces, branded reports and shared report links are not part of {target.name}. "
                f"{usage.clients} clients would no longer be available.",
                usage.clients,
                None,
            )
        )
    return effects
