# ABOUTME: Tests for WatchRepository, PendingRetireRepository and the user/booking repository additions.
# ABOUTME: Runs against an in-memory SQLite database with the current schema.

import logging
from datetime import date, datetime, timedelta

import pytest
from sqlmodel import select

from src.db_models import (
    AppointmentLog,
    BookingSession,
    PendingRetire,
    ServiceSubscription,
    User,
    Watch,
)
from src.repositories import (
    MAX_OPEN_WATCHES,
    BookingSessionRepository,
    LimitReached,
    LiveAlert,
    PendingRetireRepository,
    UserRepository,
    WatchRecord,
    WatchRepository,
)
from src.watches import when
from src.watches.slots import Slot, SlotTime, WatchSnapshot
from src.watches.when import PRESETS, WhenSpec

USER = 1
OTHER = 2
NOW = datetime(2026, 10, 22, 10, 0)
ASAP = PRESETS["asap"]
D1 = date(2026, 10, 29)
D2 = date(2026, 11, 26)


@pytest.fixture
def repo(db_session):
    users = UserRepository(db_session)
    users.create_user(USER, language="en")
    users.create_user(OTHER, language="ru")
    return WatchRepository(db_session)


def create(repo, service_id, office_id=None, when=ASAP, user_id=USER) -> WatchRecord:
    rec, _ = repo.create_or_update(user_id, service_id, office_id, when)
    return rec


def row(db_session, watch_id) -> Watch:
    db_session.expire_all()
    return db_session.get(Watch, watch_id)


class TestCreateOrUpdate:
    def test_creates_active_watch(self, repo):
        spec = WhenSpec("between", date_from=D1, date_to=D2)
        rec, updated = repo.create_or_update(USER, 100, 10, spec)

        assert updated is False
        assert isinstance(rec, WatchRecord)
        assert (rec.user_id, rec.service_id, rec.office_id) == (USER, 100, 10)
        assert rec.when == spec
        assert rec.status == "active"
        assert rec.alerted == frozenset()
        assert rec.live is None and rec.snapshot is None and rec.interacted_at is None
        assert rec.is_open

    def test_same_service_updates_open_watch(self, repo, db_session):
        first = create(repo, 100, 10)
        repo.set_status(first.id, "paused", pause_reason="user")
        repo.set_alerted(first.id, frozenset({Slot(D1, 10)}))

        rec, updated = repo.create_or_update(USER, 100, None, PRESETS["2w"])

        assert updated is True
        assert rec.id == first.id
        assert rec.office_id is None
        assert rec.when == PRESETS["2w"]
        assert rec.status == "active" and rec.pause_reason is None
        assert rec.alerted == frozenset()
        assert repo.count_open(USER) == 1

    def test_ended_watch_of_same_service_does_not_block_new_one(self, repo):
        first = create(repo, 100)
        repo.set_status(first.id, "ended", end_reason="stopped")

        rec, updated = repo.create_or_update(USER, 100, None, ASAP)

        assert updated is False and rec.id != first.id

    def test_limit_on_create(self, repo):
        for service_id in range(MAX_OPEN_WATCHES):
            create(repo, service_id)
        with pytest.raises(LimitReached):
            repo.create_or_update(USER, 99, None, ASAP)
        assert repo.count_open(USER) == 5

    def test_paused_counts_towards_limit_and_update_allowed_at_limit(self, repo):
        recs = [create(repo, service_id) for service_id in range(MAX_OPEN_WATCHES)]
        repo.set_status(recs[0].id, "paused", pause_reason="user")
        with pytest.raises(LimitReached):
            repo.create_or_update(USER, 99, None, ASAP)
        rec, updated = repo.create_or_update(USER, 3, 7, ASAP)
        assert updated is True and rec.office_id == 7

    def test_limit_is_per_user(self, repo):
        for service_id in range(MAX_OPEN_WATCHES):
            create(repo, service_id)
        assert create(repo, 1, user_id=OTHER).user_id == OTHER


class TestQueries:
    def test_find_open_get_and_get_for_user(self, repo):
        rec = create(repo, 100)
        assert repo.find_open(USER, 100).id == rec.id
        assert repo.find_open(USER, 200) is None
        assert repo.get(rec.id).id == rec.id
        assert repo.get(999) is None
        assert repo.get_for_user(rec.id, USER).id == rec.id
        assert repo.get_for_user(rec.id, OTHER) is None

    def test_find_open_ignores_ended(self, repo):
        rec = create(repo, 100)
        repo.set_status(rec.id, "ended", end_reason="stopped")
        assert repo.find_open(USER, 100) is None
        assert repo.count_open(USER) == 0

    def test_list_for_user_open_first_then_recent_ended(self, repo, db_session):
        first = create(repo, 1)
        second = create(repo, 2)
        booked = create(repo, 3)
        stopped = create(repo, 4)
        old = create(repo, 5)
        repo.set_status(booked.id, "ended", end_reason="booked")
        repo.set_status(stopped.id, "ended", end_reason="stopped")
        repo.set_status(old.id, "ended", end_reason="deadline")
        db_session.get(Watch, old.id).ended_at = NOW - timedelta(days=30)
        db_session.commit()
        create(repo, 9, user_id=OTHER)

        ids = [
            r.id for r in repo.list_for_user(USER, ended_since=NOW - timedelta(days=7))
        ]

        assert ids == [first.id, second.id, booked.id]
        all_ids = [r.id for r in repo.list_for_user(USER, ended_since=None)]
        assert all_ids == [first.id, second.id, booked.id, old.id]

    def test_list_active_excludes_paused_and_ended(self, repo):
        active = create(repo, 1)
        paused = create(repo, 2)
        ended = create(repo, 3)
        repo.set_status(paused.id, "paused", pause_reason="user")
        repo.set_status(ended.id, "ended", end_reason="stopped")
        assert [r.id for r in repo.list_active()] == [active.id]

    def test_list_paused_of_every_user(self, repo):
        create(repo, 1)
        mine = create(repo, 2)
        theirs = create(repo, 2, user_id=OTHER)
        ended = create(repo, 3)
        repo.set_status(mine.id, "paused", pause_reason="user")
        repo.set_status(theirs.id, "paused", pause_reason="blocked")
        repo.set_status(ended.id, "ended", end_reason="stopped")
        assert [r.id for r in repo.list_paused()] == [mine.id, theirs.id]

    def test_bad_row_is_skipped_and_logged(self, repo, db_session, caplog):
        good = create(repo, 1)
        bad = create(repo, 2)
        db_session.get(Watch, bad.id).date_to = "not-a-date"
        db_session.get(Watch, bad.id).when_kind = "before"
        db_session.commit()

        with caplog.at_level(logging.ERROR, logger="src.repositories"):
            assert [r.id for r in repo.list_active()] == [good.id]
            assert [r.id for r in repo.list_for_user(USER, None)] == [good.id]
        assert any(str(bad.id) in r.getMessage() for r in caplog.records)

    def test_bad_json_row_is_skipped(self, repo, db_session, caplog):
        bad = create(repo, 2)
        db_session.get(Watch, bad.id).alerted_slots = "{oops"
        db_session.commit()
        with caplog.at_level(logging.ERROR, logger="src.repositories"):
            assert repo.list_active() == []
            assert repo.get(bad.id) is None

    @pytest.mark.parametrize(
        ("column", "value"),
        [
            ("alerted_slots", "[1]"),
            ("alerted_slots", "[null]"),
            ("alert_shown_slots", '[["2026-10-29", 1]]'),
            (
                "last_snapshot",
                (
                    '{"checked_at": "2026-10-22T10:00:00", "ok": true,'
                    ' "slots": [7], "earliest_times": []}'
                ),
            ),
        ],
    )
    def test_wrong_shaped_json_row_is_skipped(
        self, repo, db_session, caplog, column, value
    ):
        good = create(repo, 1)
        bad = create(repo, 2)
        if column == "alert_shown_slots":
            repo.set_live_alert(
                bad.id, USER, 77, "slots", frozenset(), frozenset(), "h"
            )
        setattr(db_session.get(Watch, bad.id), column, value)
        db_session.commit()

        with caplog.at_level(logging.ERROR, logger="src.repositories"):
            assert [r.id for r in repo.list_active()] == [good.id]
            assert [r.id for r in repo.list_for_user(USER, None)] == [good.id]
        assert any(str(bad.id) in r.getMessage() for r in caplog.records)

    def test_counts(self, repo):
        create(repo, 1)
        paused = create(repo, 2)
        ended = create(repo, 3)
        create(repo, 1, user_id=OTHER)
        repo.set_status(paused.id, "paused", pause_reason="user")
        repo.set_status(ended.id, "ended", end_reason="stopped")
        assert repo.counts() == {
            "active": 2,
            "paused": 1,
            "ended": 1,
            "users_with_open": 2,
        }


class TestWhenAndOffice:
    def test_set_when_reopens_ended_watch(self, repo, db_session):
        rec = create(repo, 1)
        repo.record_check(rec.id, WatchSnapshot(NOW, True, frozenset({Slot(D1, 1)})))
        repo.set_alerted(rec.id, frozenset({Slot(D1, 1)}))
        repo.set_status(rec.id, "ended", end_reason="deadline")

        updated = repo.set_when(rec.id, PRESETS["1m"])

        assert updated.id == rec.id
        assert updated.status == "active"
        assert updated.when == PRESETS["1m"]
        assert updated.end_reason is None and updated.ended_at is None
        assert updated.pause_reason is None
        assert updated.alerted == frozenset()
        assert updated.snapshot is None and updated.last_checked_at is None

    def test_set_when_resumes_paused(self, repo):
        rec = create(repo, 1)
        repo.set_status(rec.id, "paused", pause_reason="user")
        assert repo.set_when(rec.id, ASAP).status == "active"

    @pytest.mark.parametrize("end_reason", ["deadline", "gone", "booked", "stopped"])
    def test_reopen_at_limit_raises(self, repo, end_reason):
        ended = create(repo, 99)
        repo.set_status(ended.id, "ended", end_reason=end_reason)
        for service_id in range(MAX_OPEN_WATCHES):
            create(repo, service_id)
        with pytest.raises(LimitReached):
            repo.set_when(ended.id, ASAP)
        with pytest.raises(LimitReached):
            repo.set_office(ended.id, None)
        assert repo.get(ended.id).status == "ended"

    def test_change_time_of_open_watch_at_limit_is_allowed(self, repo):
        recs = [create(repo, service_id) for service_id in range(MAX_OPEN_WATCHES)]
        assert repo.set_when(recs[0].id, PRESETS["3m"]).when == PRESETS["3m"]
        assert repo.set_office(recs[0].id, 5).office_id == 5

    def test_reopen_when_service_already_has_open_watch_updates_that_watch(self, repo):
        ended = create(repo, 1, office_id=10)
        repo.set_status(ended.id, "ended", end_reason="gone")
        current = create(repo, 1, office_id=None)

        updated = repo.set_when(ended.id, PRESETS["2w"])

        assert updated.id == current.id
        assert updated.when == PRESETS["2w"]
        assert updated.office_id == 10
        assert repo.get(ended.id).status == "ended"
        assert repo.count_open(USER) == 1

    def test_set_office_on_ended_watch_skips_limit_when_service_is_open(self, repo):
        ended = create(repo, 100, office_id=10)
        repo.set_status(ended.id, "ended", end_reason="gone")
        for service_id in [100, 1, 2, 3, 4]:
            create(repo, service_id)

        updated = repo.set_office(ended.id, None)

        assert updated.id == ended.id and updated.office_id is None
        assert repo.set_when(ended.id, ASAP).id != ended.id
        assert repo.count_open(USER) == MAX_OPEN_WATCHES

    def test_reopen_redirect_keeps_live_alert_of_pressed_watch(self, repo):
        ended = create(repo, 1, office_id=10)
        repo.set_status(ended.id, "ended", end_reason="deadline")
        repo.set_live_alert(ended.id, USER, 77, "ended", frozenset(), frozenset(), "h")
        current = create(repo, 1, office_id=None)

        updated = repo.set_when(ended.id, PRESETS["2w"])

        assert updated.id == current.id
        assert updated.live is None
        live = repo.get(ended.id).live
        assert (live.message_id, live.kind) == (77, "ended")

    def test_set_office_keeps_status(self, repo):
        rec = create(repo, 1, office_id=10)
        repo.set_status(rec.id, "ended", end_reason="gone")
        updated = repo.set_office(rec.id, None)
        assert updated.office_id is None and updated.status == "ended"


class TestStatus:
    def test_end_sets_reason_and_time(self, repo):
        rec = create(repo, 1)
        repo.set_status(rec.id, "ended", end_reason="booked")
        ended = repo.get(rec.id)
        assert ended.status == "ended" and ended.end_reason == "booked"
        assert ended.ended_at is not None
        assert not ended.is_open

    def test_pause_and_resume(self, repo):
        rec = create(repo, 1)
        repo.set_status(rec.id, "paused", pause_reason="user")
        assert repo.get(rec.id).pause_reason == "user"
        repo.set_status(rec.id, "active")
        assert repo.get(rec.id).pause_reason is None

    def test_blocked_pause_and_resume_only_blocked(self, repo):
        a = create(repo, 1)
        b = create(repo, 2)
        user_paused = create(repo, 3)
        ended = create(repo, 4)
        repo.set_status(user_paused.id, "paused", pause_reason="user")
        repo.set_status(ended.id, "ended", end_reason="stopped")
        other = create(repo, 1, user_id=OTHER)

        assert repo.pause_all_for_user(USER) == 2
        assert {repo.get(a.id).pause_reason, repo.get(b.id).pause_reason} == {"blocked"}
        assert repo.get(other.id).status == "active"
        assert repo.resume_blocked(USER) == 2
        assert repo.get(a.id).status == "active"
        assert repo.get(user_paused.id).pause_reason == "user"
        assert repo.get(ended.id).status == "ended"
        assert repo.resume_blocked(USER) == 0


class TestCheckAndLiveAlert:
    def test_record_check(self, repo):
        rec = create(repo, 1)
        snap = WatchSnapshot(NOW, True, frozenset({Slot(D1, 1)}), (SlotTime(5, 1),))
        assert repo.record_check(rec.id, snap) is True
        stored = repo.get(rec.id)
        assert stored.snapshot == snap
        assert stored.last_checked_at == NOW

    def test_failed_check_changes_nothing(self, repo):
        rec = create(repo, 1)
        assert repo.record_check(rec.id, WatchSnapshot(NOW, False)) is False
        stored = repo.get(rec.id)
        assert stored.snapshot is None and stored.last_checked_at is None

    def test_set_update_clear_live_alert(self, repo, db_session):
        rec = create(repo, 1)
        shown = frozenset({Slot(D1, 1)})
        repo.mark_interaction(USER, 77, NOW)
        repo.set_live_alert(rec.id, USER, 77, "slots", shown, shown, "h1")

        live = repo.get(rec.id).live
        assert isinstance(live, LiveAlert)
        assert (
            live.chat_id,
            live.message_id,
            live.kind,
            live.shown,
            live.render_hash,
        ) == (
            USER,
            77,
            "slots",
            shown,
            "h1",
        )
        assert live.sent_at is not None

        repo.mark_interaction(USER, 77, NOW)
        assert repo.get(rec.id).interacted_at == NOW
        repo.set_live_alert(rec.id, USER, 78, "slots", shown, shown, "h2")
        assert repo.get(rec.id).interacted_at is None

        both = frozenset({Slot(D1, 1), Slot(D2, 1)})
        repo.update_live_alert(rec.id, "empty", frozenset(), both, "h3")
        stored = repo.get(rec.id)
        assert stored.live.kind == "empty" and stored.live.shown == frozenset()
        assert stored.live.message_id == 78
        assert stored.alerted == both

        repo.mark_interaction(USER, 78, NOW)
        repo.clear_live_alert(rec.id, reset_alerted=False)
        stored = repo.get(rec.id)
        assert stored.live is None and stored.interacted_at is None
        assert stored.alerted == both
        assert row(db_session, rec.id).alert_shown_slots == "[]"

    def test_clear_live_alert_reset_and_explicit_alerted(self, repo):
        rec = create(repo, 1)
        a = frozenset({Slot(D1, 1)})
        repo.set_live_alert(rec.id, USER, 5, "slots", a, a, "h")
        repo.clear_live_alert(
            rec.id, reset_alerted=False, alerted=frozenset({Slot(D2, 1)})
        )
        assert repo.get(rec.id).alerted == frozenset({Slot(D2, 1)})
        repo.clear_live_alert(rec.id, reset_alerted=True)
        assert repo.get(rec.id).alerted == frozenset()

    def test_mark_interaction_only_matching_live_alert(self, repo):
        rec = create(repo, 1)
        repo.set_live_alert(rec.id, USER, 5, "slots", frozenset(), frozenset(), "h")
        assert repo.mark_interaction(USER, 6, NOW) is None
        assert repo.mark_interaction(OTHER, 5, NOW) is None
        assert repo.get(rec.id).interacted_at is None
        assert repo.mark_interaction(USER, 5, NOW) == rec.id
        assert repo.get(rec.id).interacted_at == NOW

    def test_clear_interaction_is_conditional(self, repo):
        rec = create(repo, 1)
        repo.set_live_alert(rec.id, USER, 5, "slots", frozenset(), frozenset(), "h")
        repo.mark_interaction(USER, 5, NOW)
        newer = NOW + timedelta(minutes=1)
        repo.mark_interaction(USER, 5, newer)

        assert repo.clear_interaction(rec.id, seen=NOW) is False
        assert repo.get(rec.id).interacted_at == newer
        assert repo.clear_interaction(rec.id, seen=newer) is True
        assert repo.get(rec.id).interacted_at is None
        assert repo.clear_interaction(rec.id, seen=None) is True


class TestPendingRetires:
    def test_add_upserts_and_due(self, db_session):
        repo = PendingRetireRepository(db_session)
        repo.add(USER, USER, 5, "old", NOW)
        repo.add(USER, USER, 5, "new", NOW + timedelta(minutes=1))
        repo.add(USER, USER, 6, "other", NOW + timedelta(hours=1))

        assert repo.due(NOW) == []
        [item] = repo.due(NOW + timedelta(minutes=1))
        assert (item.chat_id, item.message_id, item.text, item.attempts) == (
            USER,
            5,
            "new",
            0,
        )
        assert [i.message_id for i in repo.due(NOW + timedelta(hours=2))] == [5, 6]

    def test_touch_only_postpones(self, db_session):
        repo = PendingRetireRepository(db_session)
        repo.add(USER, USER, 5, "t", NOW)
        assert repo.touch(USER, 5, NOW + timedelta(minutes=10)) is True
        assert repo.due(NOW + timedelta(minutes=9)) == []
        repo.touch(USER, 5, NOW + timedelta(minutes=1))
        assert repo.due(NOW + timedelta(minutes=9)) == []
        assert repo.touch(USER, 99, NOW) is False

    def test_reschedule_discard_delete(self, db_session):
        repo = PendingRetireRepository(db_session)
        repo.add(USER, USER, 5, "t", NOW)
        repo.add(USER, USER, 6, "t", NOW)
        [first, second] = repo.due(NOW)
        repo.reschedule(first.id, NOW + timedelta(minutes=2), attempts=3)
        assert [i.id for i in repo.due(NOW)] == [second.id]
        [later] = [i for i in repo.due(NOW + timedelta(minutes=2)) if i.id == first.id]
        assert later.attempts == 3
        assert repo.discard(USER, 6) is True
        assert repo.discard(USER, 6) is False
        repo.delete(first.id)
        assert repo.due(NOW + timedelta(days=1)) == []

    def test_list_for_user_ignores_not_before(self, db_session):
        repo = PendingRetireRepository(db_session)
        repo.add(USER, USER, 5, "a", NOW + timedelta(days=1))
        repo.add(OTHER, OTHER, 6, "b", NOW)
        repo.add(USER, USER, 7, "c", NOW)
        assert [(i.message_id, i.text) for i in repo.list_for_user(USER)] == [
            (5, "a"),
            (7, "c"),
        ]
        assert repo.list_for_user(99) == []


class TestUserAdditions:
    def test_contact(self, db_session):
        users = UserRepository(db_session)
        users.create_user(USER)
        assert users.get_booking_contact(USER) is None
        users.set_booking_contact(USER, "Anna", "anna@example.com")
        assert users.get_booking_contact(USER) == ("Anna", "anna@example.com")
        users.clear_booking_contact(USER)
        assert users.get_booking_contact(USER) is None

    def test_ui_version_and_nav_pointer(self, db_session):
        users = UserRepository(db_session)
        users.create_user(USER)
        assert users.get_user(USER).ui_version == 0
        users.set_ui_version(USER, 2)
        assert users.get_user(USER).ui_version == 2
        assert users.get_nav_message_id(USER) is None
        users.set_nav_message_id(USER, 55)
        assert users.get_nav_message_id(USER) == 55
        users.set_nav_message_id(USER, None)
        assert users.get_nav_message_id(USER) is None
        assert users.get_nav_message_id(999) is None

    def test_delete_user_cascade_leaves_no_rows(self, db_session):
        users = UserRepository(db_session)
        users.create_user(USER)
        users.create_user(OTHER)
        watches = WatchRepository(db_session)
        create(watches, 1)
        create(watches, 1, user_id=OTHER)
        PendingRetireRepository(db_session).add(USER, USER, 5, "t", NOW)
        BookingSessionRepository(db_session).create_session(
            USER, "SELECTING_TIME", 1, 2, "2026-10-29", "", NOW + timedelta(minutes=15)
        )
        db_session.add(ServiceSubscription(user_id=USER, service_id=1, office_id=2))
        db_session.add(AppointmentLog(service_id=1, office_id=2, data="{}"))
        db_session.commit()

        users.delete_user_cascade(USER)

        db_session.expire_all()
        for model in (Watch, PendingRetire, BookingSession, ServiceSubscription, User):
            owners = {r.user_id for r in db_session.exec(select(model))}
            assert USER not in owners, model.__name__
        assert len(db_session.exec(select(Watch)).all()) == 1
        assert len(db_session.exec(select(AppointmentLog)).all()) == 1


class TestBookingSessionAdditions:
    def _create(
        self, repo, user_id=USER, expires=NOW + timedelta(minutes=15), **kwargs
    ):
        return repo.create_session(
            user_id=user_id,
            state="SELECTING_TIME",
            service_id=1,
            office_id=0,
            date="2026-10-29",
            captcha_token="",
            expires_at=expires,
            **kwargs,
        )

    def test_create_with_watch_and_message(self, db_session):
        repo = BookingSessionRepository(db_session)
        self._create(
            repo,
            watch_id=7,
            message_id=70,
            expires=when.utcnow() + timedelta(minutes=5),
        )
        record = repo.get_active(USER)
        assert (record.watch_id, record.message_id, record.office_id) == (7, 70, 0)

    def test_update_office_and_message(self, db_session):
        repo = BookingSessionRepository(db_session)
        self._create(repo, expires=when.utcnow() + timedelta(minutes=5))
        repo.update_session(USER, timestamp=123, office_id=102526, message_id=71)
        record = repo.get_active(USER)
        assert (record.timestamp, record.office_id, record.message_id) == (
            123,
            102526,
            71,
        )

    def test_is_user_in_booking_deletes_nothing(self, db_session):
        repo = BookingSessionRepository(db_session)
        self._create(repo, expires=when.utcnow() - timedelta(minutes=1))
        assert repo.is_user_in_booking(USER) is False
        assert repo.get_session(USER) is not None
        assert repo.get_active(USER) is None

    def test_pop_expired_and_pop_all(self, db_session):
        repo = BookingSessionRepository(db_session)
        now = when.utcnow()
        self._create(repo, USER, expires=now + timedelta(minutes=5), message_id=70)
        self._create(repo, OTHER, expires=now - timedelta(minutes=5), message_id=80)

        [expired] = repo.pop_expired_sessions()
        assert (expired.user_id, expired.message_id) == (OTHER, 80)
        assert repo.get_session(OTHER) is None
        assert repo.get_session(USER) is not None

        [rest] = repo.pop_all_sessions()
        assert rest.user_id == USER
        assert repo.pop_all_sessions() == []
