# ABOUTME: Pure decision of what to do with a watch's live alert after a check.
# ABOUTME: Implements the state x event table of the alert lifecycle (push, edit, defer, nothing).

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

from src.watches.slots import Slot, top_days

INTERACTION_LOCK = timedelta(minutes=10)


class Interaction(StrEnum):
    NONE = "none"
    ACTIVE = "active"
    RELEASED = "released"


class AlertAction(StrEnum):
    NOOP = "noop"
    DEFER = "defer"
    PUSH = "push"
    EDIT = "edit"
    EDIT_EMPTY = "edit_empty"


@dataclass(frozen=True)
class AlertDecision:
    action: AlertAction
    silent: bool = False  # PUSH without notification sound
    # queue the old live alert for "Outdated" after sending
    retire_previous: bool = False
    alerted: frozenset[Slot] | None = None  # new alerted set; None = unchanged
    clear_interaction: bool = False


def interaction_state(
    booking_active: bool, interacted_at: datetime | None, now: datetime
) -> Interaction:
    if booking_active:
        return Interaction.ACTIVE
    if interacted_at is None:
        return Interaction.NONE
    if now - interacted_at < INTERACTION_LOCK:
        return Interaction.ACTIVE
    return Interaction.RELEASED


def decide_alert(
    alerted: frozenset[Slot],
    current: frozenset[Slot],
    live_kind: str | None,
    shown: frozenset[Slot],
    render_changed: bool,
    interaction: Interaction,
) -> AlertDecision:
    """`alerted` must already be pruned of past days."""
    if interaction is Interaction.ACTIVE:
        return AlertDecision(AlertAction.DEFER)

    released = interaction is Interaction.RELEASED

    if not current:
        if live_kind == "slots":
            return AlertDecision(
                AlertAction.EDIT_EMPTY, alerted=frozenset(), clear_interaction=released
            )
        return AlertDecision(AlertAction.NOOP, alerted=frozenset())

    merged = alerted | current
    new_top = top_days(current) - {s.day for s in alerted}
    if new_top:
        return AlertDecision(
            AlertAction.PUSH,
            retire_previous=live_kind is not None,
            alerted=merged,
            clear_interaction=released,
        )

    if live_kind is None:
        return AlertDecision(AlertAction.NOOP, alerted=merged)

    if live_kind != "slots":
        # The live message says there is nothing; replace it even though no day is new
        return AlertDecision(
            AlertAction.PUSH,
            silent=True,
            retire_previous=True,
            alerted=merged,
            clear_interaction=released,
        )

    changed = current != shown or render_changed
    if not changed:
        return AlertDecision(AlertAction.NOOP, clear_interaction=released)
    if released:
        return AlertDecision(
            AlertAction.PUSH,
            silent=True,
            retire_previous=True,
            alerted=merged,
            clear_interaction=True,
        )
    return AlertDecision(AlertAction.EDIT, alerted=merged)
