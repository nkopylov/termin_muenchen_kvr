# ABOUTME: Tests for the pure alert decision: one test per row of the design's state x event table.
# ABOUTME: Also covers the interaction lock boundary and flapping slot sets.

from datetime import date, datetime, timedelta

import pytest

from src.watches.alert_decision import (
    INTERACTION_LOCK,
    AlertAction,
    AlertDecision,
    Interaction,
    decide_alert,
    interaction_state,
)
from src.watches.slots import Slot

D1, D2, D3, D4, D5 = (date(2026, 11, d) for d in (2, 3, 4, 5, 6))
A = Slot(D1, 1)
B = Slot(D2, 1)
C = Slot(D3, 1)
FAR = Slot(D5, 1)
NOW = datetime(2026, 10, 22, 12, 0)

NONE, ACTIVE, RELEASED = Interaction.NONE, Interaction.ACTIVE, Interaction.RELEASED


def fs(*slots):
    return frozenset(slots)


class TestInteractionState:
    def test_lock_is_ten_minutes(self):
        assert INTERACTION_LOCK == timedelta(minutes=10)

    def test_booking_is_active(self):
        assert interaction_state(True, None, NOW) is ACTIVE
        assert interaction_state(True, NOW - timedelta(hours=1), NOW) is ACTIVE

    def test_recent_tap_is_active(self):
        tapped = NOW - timedelta(minutes=9, seconds=59)
        assert interaction_state(False, tapped, NOW) is ACTIVE

    def test_tap_ten_minutes_ago_is_released(self):
        assert interaction_state(False, NOW - timedelta(minutes=10), NOW) is RELEASED

    def test_no_tap_is_none(self):
        assert interaction_state(False, None, NOW) is NONE


class TestTableRows:
    @pytest.mark.parametrize("live", [None, "slots", "empty"])
    @pytest.mark.parametrize("current", [fs(), fs(A)])
    def test_row1_active_defers(self, live, current):
        decision = decide_alert(fs(), current, live, fs(), True, ACTIVE)
        assert decision == AlertDecision(AlertAction.DEFER)

    @pytest.mark.parametrize("interaction", [NONE, RELEASED])
    @pytest.mark.parametrize("live", [None, "slots", "empty"])
    def test_row2_new_top_day_pushes_with_sound(self, interaction, live):
        decision = decide_alert(fs(A), fs(A, B), live, fs(A), True, interaction)
        assert decision.action is AlertAction.PUSH
        assert decision.silent is False
        assert decision.retire_previous is (live is not None)
        assert decision.alerted == fs(A, B)
        assert decision.clear_interaction is (interaction is RELEASED)

    def test_row2_alerted_keeps_vanished_slots(self):
        decision = decide_alert(fs(C), fs(A), "slots", fs(C), False, NONE)
        assert decision.action is AlertAction.PUSH
        assert decision.alerted == fs(A, C)

    def test_row3_changed_slots_edit_in_place(self):
        decision = decide_alert(fs(A, B), fs(A), "slots", fs(A, B), False, NONE)
        assert decision == AlertDecision(AlertAction.EDIT, alerted=fs(A, B))

    def test_row3_render_change_alone_edits(self):
        decision = decide_alert(fs(A), fs(A), "slots", fs(A), True, NONE)
        assert decision.action is AlertAction.EDIT

    def test_row4_same_render_is_noop(self):
        decision = decide_alert(fs(A), fs(A), "slots", fs(A), False, NONE)
        assert decision == AlertDecision(AlertAction.NOOP)

    def test_row5_released_change_pushes_silently(self):
        decision = decide_alert(fs(A, B), fs(A), "slots", fs(A, B), False, RELEASED)
        assert decision == AlertDecision(
            AlertAction.PUSH,
            silent=True,
            retire_previous=True,
            alerted=fs(A, B),
            clear_interaction=True,
        )

    def test_row6_released_same_render_clears_interaction(self):
        decision = decide_alert(fs(A), fs(A), "slots", fs(A), False, RELEASED)
        assert decision == AlertDecision(AlertAction.NOOP, clear_interaction=True)

    @pytest.mark.parametrize("interaction", [NONE, RELEASED])
    def test_row7_no_live_message_no_repeat(self, interaction):
        decision = decide_alert(fs(A, B), fs(A), None, fs(), True, interaction)
        assert decision == AlertDecision(AlertAction.NOOP, alerted=fs(A, B))

    @pytest.mark.parametrize("interaction", [NONE, RELEASED])
    def test_row8_going_empty_edits_and_resets(self, interaction):
        decision = decide_alert(fs(A), fs(), "slots", fs(A), True, interaction)
        assert decision == AlertDecision(
            AlertAction.EDIT_EMPTY,
            alerted=fs(),
            clear_interaction=interaction is RELEASED,
        )

    @pytest.mark.parametrize("live", ["empty", None])
    def test_row9_still_empty_resets_alerted(self, live):
        decision = decide_alert(fs(A), fs(), live, fs(), False, NONE)
        assert decision == AlertDecision(AlertAction.NOOP, alerted=fs())


class TestConsequences:
    def test_flapping_does_not_push_twice(self):
        first = decide_alert(fs(), fs(A, B), None, fs(), True, NONE)
        assert first.action is AlertAction.PUSH
        second = decide_alert(first.alerted, fs(A), "slots", fs(A, B), True, NONE)
        assert second.action is AlertAction.EDIT
        assert second.alerted == fs(A, B)
        third = decide_alert(second.alerted, fs(A, B), "slots", fs(A), True, NONE)
        assert third.action is AlertAction.EDIT

    def test_far_horizon_day_is_silent_edit(self):
        alerted = fs(A, B, C)
        decision = decide_alert(alerted, fs(A, B, C, FAR), "slots", alerted, True, NONE)
        assert decision.action is AlertAction.EDIT

    def test_second_office_on_alerted_day_is_silent_edit(self):
        decision = decide_alert(fs(A), fs(A, Slot(D1, 2)), "slots", fs(A), True, NONE)
        assert decision.action is AlertAction.EDIT

    def test_new_earlier_day_pushes(self):
        alerted = fs(B, C, Slot(D4, 1))
        earlier = Slot(date(2026, 11, 1), 1)
        decision = decide_alert(
            alerted, alerted | {earlier}, "slots", alerted, True, NONE
        )
        assert decision.action is AlertAction.PUSH

    def test_after_empty_alert_any_slot_pushes_and_retires(self):
        decision = decide_alert(fs(), fs(FAR), "empty", fs(), True, NONE)
        assert decision.action is AlertAction.PUSH
        assert decision.retire_previous is True

    def test_empty_alert_with_stale_alerted_still_replaces_message(self):
        decision = decide_alert(fs(A), fs(A), "empty", fs(), True, NONE)
        assert decision.action is AlertAction.PUSH
        assert decision.silent is True
        assert decision.retire_previous is True
