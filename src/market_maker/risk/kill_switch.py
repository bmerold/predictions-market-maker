"""Kill switch for emergency trading halt.

Provides a mechanism to immediately stop all trading activity
when dangerous conditions are detected.
"""

from __future__ import annotations

from datetime import UTC, datetime


class KillSwitch:
    """Emergency stop mechanism for trading.

    When activated, blocks all quote generation until manually reset.
    Records activation reason and time for incident review.

    This is a critical safety mechanism that should:
    - Be triggered by severe risk violations (PnL limits)
    - Be manually activated in emergencies
    - Require explicit manual reset before trading resumes
    """

    def __init__(self) -> None:
        """Initialize an inactive kill switch."""
        self._active = False
        self._activation_reason: str | None = None
        self._activation_time: datetime | None = None

    def is_active(self) -> bool:
        """Return True if the kill switch is active."""
        return self._active

    @property
    def activation_reason(self) -> str | None:
        """Return the reason for activation, or None if not active."""
        return self._activation_reason

    @property
    def activation_time(self) -> datetime | None:
        """Return when the kill switch was activated, or None if not active."""
        return self._activation_time

    def activate(self, reason: str) -> None:
        """Activate the kill switch.

        If already active, keeps the original reason and time.

        Args:
            reason: Human-readable reason for activation
        """
        if self._active:
            # Already active, don't overwrite first reason
            return

        self._active = True
        self._activation_reason = reason
        self._activation_time = datetime.now(UTC)

    def reset(self) -> None:
        """Reset the kill switch to inactive state.

        This should only be called after the incident has been
        reviewed and it's safe to resume trading.
        """
        self._active = False
        self._activation_reason = None
        self._activation_time = None
