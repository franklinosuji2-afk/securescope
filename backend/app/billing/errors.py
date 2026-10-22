from __future__ import annotations


class PlanLimitError(Exception):
    """An action would go beyond what the organization's plan includes. The message is safe to show to the user."""
