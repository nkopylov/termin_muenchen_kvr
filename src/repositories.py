"""
Repository pattern for database access
Provides clean separation between business logic and data access
"""

import json
import logging
from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional

from sqlmodel import Session, delete, func, select, update

from src.db_models import (
    AppointmentLog,
    BookingSession,
    PendingRetire,
    ServiceSubscription,
    User,
    Watch,
)
from src.watches import when as when_module
from src.watches.slots import (
    Slot,
    WatchSnapshot,
    decode_slots,
    encode_slots,
    snapshot_from_json,
    snapshot_to_json,
)
from src.watches.when import WhenSpec

logger = logging.getLogger(__name__)

MAX_OPEN_WATCHES = 5
OPEN_STATUSES = ("active", "paused")
WHEN_KINDS = ("asap", "within", "before", "between")


class UserRepository:
    """Repository for User operations"""

    def __init__(self, session: Session):
        self.session = session

    def get_user(self, user_id: int) -> User | None:
        """Get user by ID"""
        return self.session.get(User, user_id)

    def create_user(
        self,
        user_id: int,
        username: str | None = None,
        language: str = "",
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> User:
        """Create new user"""
        user = User(
            user_id=user_id,
            username=username,
            language=language,
            start_date=start_date,
            end_date=end_date,
        )
        self.session.add(user)
        self.session.commit()
        self.session.refresh(user)
        return user

    def get_or_create_user(
        self, user_id: int, username: str | None = None, language: str = ""
    ) -> User:
        """Get existing user or create new one"""
        user = self.get_user(user_id)
        if user is None:
            user = self.create_user(user_id, username, language)
        return user

    def set_language(self, user_id: int, language: str) -> bool:
        """Set user's interface language; returns False if the user does not exist"""
        user = self.get_user(user_id)
        if user is None:
            return False
        user.language = language
        self.session.commit()
        return True

    def get_all_users(self) -> list[User]:
        """Get all users"""
        statement = select(User)
        return list(self.session.exec(statement))

    def get_booking_contact(self, user_id: int) -> tuple[str, str] | None:
        """Saved (name, email) for booking, or None"""
        user = self.get_user(user_id)
        if user is None or not user.booking_name or not user.booking_email:
            return None
        return user.booking_name, user.booking_email

    def set_booking_contact(self, user_id: int, name: str, email: str) -> None:
        user = self.get_user(user_id)
        if user is None:
            return
        user.booking_name = name
        user.booking_email = email
        self.session.commit()

    def clear_booking_contact(self, user_id: int) -> None:
        user = self.get_user(user_id)
        if user is None:
            return
        user.booking_name = None
        user.booking_email = None
        self.session.commit()

    def set_ui_version(self, user_id: int, version: int) -> None:
        user = self.get_user(user_id)
        if user is None:
            return
        user.ui_version = version
        self.session.commit()

    def get_nav_message_id(self, user_id: int) -> int | None:
        user = self.get_user(user_id)
        return None if user is None else user.nav_message_id

    def set_nav_message_id(self, user_id: int, message_id: int | None) -> None:
        user = self.get_user(user_id)
        if user is None:
            return
        user.nav_message_id = message_id
        self.session.commit()

    def delete_user_cascade(self, user_id: int) -> None:
        """Delete the user and every row that belongs to them, children first"""
        for model in (PendingRetire, Watch, BookingSession, ServiceSubscription):
            self.session.exec(delete(model).where(model.user_id == user_id))
        self.session.exec(delete(User).where(User.user_id == user_id))
        self.session.commit()
        self.session.expire_all()


class SubscriptionRepository:
    """Repository for ServiceSubscription operations"""

    def __init__(self, session: Session):
        self.session = session

    def delete_all_user_subscriptions(self, user_id: int) -> int:
        """Delete all subscriptions for a user"""
        statement = delete(ServiceSubscription).where(
            ServiceSubscription.user_id == user_id
        )
        result = self.session.exec(statement)
        self.session.commit()
        return result.rowcount


class AppointmentLogRepository:
    """Repository for AppointmentLog operations"""

    def __init__(self, session: Session):
        self.session = session

    def log_appointment(
        self, service_id: int, office_id: int, data: dict
    ) -> AppointmentLog:
        """Log appointment availability"""
        log = AppointmentLog(
            service_id=service_id, office_id=office_id, data=json.dumps(data)
        )
        self.session.add(log)
        self.session.commit()
        self.session.refresh(log)
        return log

    def get_recent_logs(
        self, service_id: int | None = None, limit: int = 100
    ) -> list[AppointmentLog]:
        """Get recent appointment logs"""
        statement = select(AppointmentLog).order_by(AppointmentLog.found_at.desc())

        if service_id:
            statement = statement.where(AppointmentLog.service_id == service_id)

        statement = statement.limit(limit)
        return list(self.session.exec(statement))

    def get_all_logs(self, limit: int = 1000) -> list[dict]:
        """Get all appointment logs as dictionaries"""
        statement = (
            select(AppointmentLog).order_by(AppointmentLog.found_at.desc()).limit(limit)
        )
        logs = self.session.exec(statement).all()

        return [
            {
                "id": log.id,
                "service_id": log.service_id,
                "office_id": log.office_id,
                "found_at": log.found_at.isoformat(),
                "data": log.data,
            }
            for log in logs
        ]


class BookingSessionRepository:
    """Repository for BookingSession operations"""

    def __init__(self, session: Session):
        self.session = session

    def create_session(
        self,
        user_id: int,
        state: str,
        service_id: int,
        office_id: int,
        date: str,
        captcha_token: str,
        expires_at: datetime,
        watch_id: int | None = None,
        message_id: int | None = None,
    ) -> BookingSession:
        """Create a new booking session"""
        # Delete any existing session for this user first
        self.delete_session(user_id)

        session = BookingSession(
            user_id=user_id,
            state=state,
            service_id=service_id,
            office_id=office_id,
            date=date,
            captcha_token=captcha_token,
            expires_at=expires_at,
            watch_id=watch_id,
            message_id=message_id,
        )
        self.session.add(session)
        self.session.commit()
        self.session.refresh(session)
        return session

    def get_session(self, user_id: int) -> BookingSession | None:
        """Get booking session for a user"""
        return self.session.get(BookingSession, user_id)

    def update_session(
        self,
        user_id: int,
        state: str | None = None,
        timestamp: int | None = None,
        name: str | None = None,
        email: str | None = None,
        office_id: int | None = None,
        message_id: int | None = None,
    ) -> BookingSession | None:
        """Update booking session"""
        booking_session = self.get_session(user_id)
        if not booking_session:
            return None

        if state is not None:
            booking_session.state = state
        if timestamp is not None:
            booking_session.timestamp = timestamp
        if name is not None:
            booking_session.name = name
        if email is not None:
            booking_session.email = email
        if office_id is not None:
            booking_session.office_id = office_id
        if message_id is not None:
            booking_session.message_id = message_id

        booking_session.updated_at = datetime.utcnow()
        self.session.commit()
        self.session.refresh(booking_session)
        return booking_session

    def delete_session(self, user_id: int) -> bool:
        """Delete booking session"""
        session = self.get_session(user_id)
        if session:
            self.session.delete(session)
            self.session.commit()
            return True
        return False

    def is_user_in_booking(self, user_id: int) -> bool:
        """Check if user has an unexpired booking session (read-only)"""
        return self.get_active(user_id) is not None

    def get_active(self, user_id: int) -> Optional["BookingSessionRecord"]:
        """The user's booking session, or None when there is none or it has expired"""
        session = self.get_session(user_id)
        if session is None or session.expires_at <= when_module.utcnow():
            return None
        return BookingSessionRecord.from_row(session)

    def message_ids_in_booking(self, now: datetime) -> set[tuple[int, int]]:
        """(chat_id, message_id) of booking messages of unexpired sessions"""
        statement = select(BookingSession.user_id, BookingSession.message_id).where(
            BookingSession.expires_at > now, BookingSession.message_id.is_not(None)
        )
        return {
            (user_id, message_id)
            for user_id, message_id in self.session.exec(statement)
        }

    def pop_expired_sessions(self) -> list["BookingSessionRecord"]:
        """Delete expired sessions and return what they were"""
        statement = select(BookingSession).where(
            BookingSession.expires_at <= when_module.utcnow()
        )
        return self._pop(list(self.session.exec(statement)))

    def pop_all_sessions(self) -> list["BookingSessionRecord"]:
        """Delete every session and return what they were"""
        return self._pop(list(self.session.exec(select(BookingSession))))

    def _pop(self, rows: list[BookingSession]) -> list["BookingSessionRecord"]:
        records = [BookingSessionRecord.from_row(row) for row in rows]
        for row in rows:
            self.session.delete(row)
        self.session.commit()
        return records


@dataclass(frozen=True)
class BookingSessionRecord:
    user_id: int
    state: str
    service_id: int
    office_id: int
    date: str
    timestamp: int | None
    name: str | None
    email: str | None
    watch_id: int | None
    message_id: int | None
    expires_at: datetime

    @classmethod
    def from_row(cls, row: BookingSession) -> "BookingSessionRecord":
        return cls(
            user_id=row.user_id,
            state=row.state,
            service_id=row.service_id,
            office_id=row.office_id,
            date=row.date,
            timestamp=row.timestamp,
            name=row.name,
            email=row.email,
            watch_id=row.watch_id,
            message_id=row.message_id,
            expires_at=row.expires_at,
        )


class LimitReached(Exception):
    """The user already has MAX_OPEN_WATCHES open watches"""


@dataclass(frozen=True)
class LiveAlert:
    chat_id: int
    message_id: int
    kind: str  # "slots" | "empty" | "ended"
    sent_at: datetime | None
    shown: frozenset[Slot]
    render_hash: str | None


@dataclass(frozen=True)
class WatchRecord:
    id: int
    user_id: int
    service_id: int
    office_id: int | None
    when: WhenSpec
    status: str
    pause_reason: str | None
    end_reason: str | None
    ended_at: datetime | None
    last_checked_at: datetime | None
    snapshot: WatchSnapshot | None
    alerted: frozenset[Slot]
    live: LiveAlert | None
    interacted_at: datetime | None

    @property
    def is_open(self) -> bool:
        return self.status in OPEN_STATUSES


def _date_or_none(raw: str | None) -> date | None:
    return date.fromisoformat(raw) if raw else None


def _decode_when(row: Watch) -> WhenSpec:
    if row.when_kind not in WHEN_KINDS:
        raise ValueError(f"unknown when_kind {row.when_kind!r}")
    spec = WhenSpec(
        row.when_kind,
        within_days=row.within_days,
        date_from=_date_or_none(row.date_from),
        date_to=_date_or_none(row.date_to),
    )
    if spec.kind == "within" and not spec.within_days:
        raise ValueError("within watch without within_days")
    if spec.kind == "before" and spec.date_to is None:
        raise ValueError("before watch without date_to")
    if spec.kind == "between" and (spec.date_from is None or spec.date_to is None):
        raise ValueError("between watch without dates")
    return spec


def _decode(row: Watch) -> WatchRecord | None:
    try:
        live = None
        if row.alert_chat_id is not None and row.alert_message_id is not None:
            live = LiveAlert(
                chat_id=row.alert_chat_id,
                message_id=row.alert_message_id,
                kind=row.alert_kind or "slots",
                sent_at=row.alert_sent_at,
                shown=decode_slots(row.alert_shown_slots or "[]"),
                render_hash=row.alert_render_hash,
            )
        return WatchRecord(
            id=row.id,
            user_id=row.user_id,
            service_id=row.service_id,
            office_id=row.office_id,
            when=_decode_when(row),
            status=row.status,
            pause_reason=row.pause_reason,
            end_reason=row.end_reason,
            ended_at=row.ended_at,
            last_checked_at=row.last_checked_at,
            snapshot=snapshot_from_json(row.last_snapshot),
            alerted=decode_slots(row.alerted_slots or "[]"),
            live=live,
            interacted_at=row.alert_interacted_at,
        )
    except (ValueError, TypeError) as exc:
        logger.error(f"Skipping watch {row.id}: cannot decode row ({exc})")
        return None


class WatchRepository:
    """Repository for Watch operations; returns immutable WatchRecords"""

    def __init__(self, session: Session):
        self.session = session

    # reads

    def _records(self, statement) -> list[WatchRecord]:
        records = (_decode(row) for row in self.session.exec(statement))
        return [r for r in records if r is not None]

    def _open_row(self, user_id: int, service_id: int) -> Watch | None:
        statement = select(Watch).where(
            Watch.user_id == user_id,
            Watch.service_id == service_id,
            Watch.status.in_(OPEN_STATUSES),
        )
        return self.session.exec(statement).first()

    def find_open(self, user_id: int, service_id: int) -> WatchRecord | None:
        row = self._open_row(user_id, service_id)
        return None if row is None else _decode(row)

    def count_open(self, user_id: int) -> int:
        statement = (
            select(func.count())
            .select_from(Watch)
            .where(Watch.user_id == user_id, Watch.status.in_(OPEN_STATUSES))
        )
        return self.session.exec(statement).one()

    def get(self, watch_id: int) -> WatchRecord | None:
        row = self.session.get(Watch, watch_id)
        return None if row is None else _decode(row)

    def get_for_user(self, watch_id: int, user_id: int) -> WatchRecord | None:
        rec = self.get(watch_id)
        return rec if rec is not None and rec.user_id == user_id else None

    def list_for_user(
        self, user_id: int, ended_since: datetime | None
    ) -> list[WatchRecord]:
        """Open watches by creation, then booked/deadline/gone ones ended since `ended_since`
        (newest first; None = no time limit)"""
        open_statement = (
            select(Watch)
            .where(Watch.user_id == user_id, Watch.status.in_(OPEN_STATUSES))
            .order_by(Watch.created_at, Watch.id)
        )
        ended_statement = (
            select(Watch)
            .where(
                Watch.user_id == user_id,
                Watch.status == "ended",
                Watch.end_reason.in_(("booked", "deadline", "gone")),
            )
            .order_by(Watch.ended_at.desc(), Watch.id.desc())
        )
        if ended_since is not None:
            ended_statement = ended_statement.where(Watch.ended_at >= ended_since)
        return self._records(open_statement) + self._records(ended_statement)

    def list_active(self) -> list[WatchRecord]:
        statement = select(Watch).where(Watch.status == "active").order_by(Watch.id)
        return self._records(statement)

    def list_paused(self) -> list[WatchRecord]:
        statement = select(Watch).where(Watch.status == "paused").order_by(Watch.id)
        return self._records(statement)

    def counts(self) -> dict[str, int]:
        by_status = dict(
            self.session.exec(
                select(Watch.status, func.count()).group_by(Watch.status)
            ).all()
        )
        users = self.session.exec(
            select(func.count(func.distinct(Watch.user_id))).where(
                Watch.status.in_(OPEN_STATUSES)
            )
        ).one()
        return {
            "active": by_status.get("active", 0),
            "paused": by_status.get("paused", 0),
            "ended": by_status.get("ended", 0),
            "users_with_open": users,
        }

    # writes

    def _row(self, watch_id: int) -> Watch:
        row = self.session.get(Watch, watch_id)
        if row is None:
            raise KeyError(f"watch {watch_id} not found")
        return row

    def _save(self, row: Watch) -> WatchRecord:
        row.updated_at = when_module.utcnow()
        self.session.add(row)
        self.session.commit()
        self.session.refresh(row)
        return _decode(row)

    @staticmethod
    def _apply_when(row: Watch, when: WhenSpec) -> None:
        row.when_kind = when.kind
        row.within_days = when.within_days
        row.date_from = when.date_from.isoformat() if when.date_from else None
        row.date_to = when.date_to.isoformat() if when.date_to else None

    @staticmethod
    def _reactivate(row: Watch) -> None:
        row.status = "active"
        row.pause_reason = None
        row.end_reason = None
        row.ended_at = None
        row.alerted_slots = "[]"
        row.last_snapshot = None
        row.last_checked_at = None

    def _check_limit(self, user_id: int) -> None:
        if self.count_open(user_id) >= MAX_OPEN_WATCHES:
            raise LimitReached(user_id)

    def create_or_update(
        self, user_id: int, service_id: int, office_id: int | None, when: WhenSpec
    ) -> tuple[WatchRecord, bool]:
        """Upsert the open watch of (user, service); True when an open watch was updated"""
        row = self._open_row(user_id, service_id)
        updated = row is not None
        if row is None:
            self._check_limit(user_id)
            row = Watch(user_id=user_id, service_id=service_id, when_kind=when.kind)
        row.office_id = office_id
        self._apply_when(row, when)
        self._reactivate(row)
        return self._save(row), updated

    def set_when(self, watch_id: int, when: WhenSpec) -> WatchRecord:
        """Change time and (re)activate. Reopening an ended watch whose service already has
        an open watch updates that open watch instead (its office becomes the ended one's);
        the returned record says which. The ended watch then keeps its live alert: when the
        returned id differs, the caller closes that alert as outdated, or clears it when it
        is the message being reused."""
        row = self._row(watch_id)
        if row.status == "ended":
            current = self._open_row(row.user_id, row.service_id)
            if current is not None:
                current.office_id = row.office_id
                row = current
            else:
                self._check_limit(row.user_id)
        self._apply_when(row, when)
        self._reactivate(row)
        return self._save(row)

    def set_office(self, watch_id: int, office_id: int | None) -> WatchRecord:
        row = self._row(watch_id)
        if (
            row.status == "ended"
            and self._open_row(row.user_id, row.service_id) is None
        ):
            self._check_limit(row.user_id)
        row.office_id = office_id
        row.last_snapshot = None
        row.last_checked_at = None
        return self._save(row)

    def set_status(
        self,
        watch_id: int,
        status: str,
        *,
        pause_reason: str | None = None,
        end_reason: str | None = None,
    ) -> WatchRecord:
        row = self._row(watch_id)
        row.status = status
        row.pause_reason = pause_reason if status == "paused" else None
        row.end_reason = end_reason if status == "ended" else None
        row.ended_at = when_module.utcnow() if status == "ended" else None
        return self._save(row)

    def pause_all_for_user(self, user_id: int, reason: str = "blocked") -> int:
        result = self.session.exec(
            update(Watch)
            .where(Watch.user_id == user_id, Watch.status == "active")
            .values(
                status="paused", pause_reason=reason, updated_at=when_module.utcnow()
            )
        )
        self.session.commit()
        return result.rowcount

    def resume_blocked(self, user_id: int) -> int:
        result = self.session.exec(
            update(Watch)
            .where(
                Watch.user_id == user_id,
                Watch.status == "paused",
                Watch.pause_reason == "blocked",
            )
            .values(status="active", pause_reason=None, updated_at=when_module.utcnow())
        )
        self.session.commit()
        return result.rowcount

    def record_check(self, watch_id: int, snapshot: WatchSnapshot) -> bool:
        """Store a successful check; a failed one (ok=False) changes nothing"""
        if not snapshot.ok:
            return False
        row = self._row(watch_id)
        row.last_snapshot = snapshot_to_json(snapshot)
        row.last_checked_at = snapshot.checked_at
        self._save(row)
        return True

    def set_live_alert(
        self,
        watch_id: int,
        chat_id: int,
        message_id: int,
        kind: str,
        shown: frozenset[Slot],
        alerted: frozenset[Slot],
        render_hash: str | None,
    ) -> WatchRecord:
        row = self._row(watch_id)
        row.alert_chat_id = chat_id
        row.alert_message_id = message_id
        row.alert_kind = kind
        row.alert_sent_at = when_module.utcnow()
        row.alert_shown_slots = encode_slots(shown)
        row.alerted_slots = encode_slots(alerted)
        row.alert_render_hash = render_hash
        row.alert_interacted_at = None
        return self._save(row)

    def update_live_alert(
        self,
        watch_id: int,
        kind: str,
        shown: frozenset[Slot],
        alerted: frozenset[Slot],
        render_hash: str | None,
    ) -> WatchRecord:
        row = self._row(watch_id)
        row.alert_kind = kind
        row.alert_shown_slots = encode_slots(shown)
        row.alerted_slots = encode_slots(alerted)
        row.alert_render_hash = render_hash
        return self._save(row)

    def clear_live_alert(
        self,
        watch_id: int,
        reset_alerted: bool,
        alerted: frozenset[Slot] | None = None,
    ) -> WatchRecord:
        row = self._row(watch_id)
        row.alert_chat_id = None
        row.alert_message_id = None
        row.alert_kind = None
        row.alert_sent_at = None
        row.alert_shown_slots = "[]"
        row.alert_render_hash = None
        row.alert_interacted_at = None
        if reset_alerted:
            row.alerted_slots = "[]"
        elif alerted is not None:
            row.alerted_slots = encode_slots(alerted)
        return self._save(row)

    def set_alerted(self, watch_id: int, alerted: frozenset[Slot]) -> WatchRecord:
        row = self._row(watch_id)
        row.alerted_slots = encode_slots(alerted)
        return self._save(row)

    def mark_interaction(
        self, chat_id: int, message_id: int, at: datetime
    ) -> int | None:
        """Record a tap on a live alert; the watch id, or None if no live alert matches"""
        result = self.session.exec(
            update(Watch)
            .where(Watch.alert_chat_id == chat_id, Watch.alert_message_id == message_id)
            .values(alert_interacted_at=at)
            .returning(Watch.id)
        )
        watch_id = result.scalars().first()
        self.session.commit()
        return watch_id

    def clear_interaction(self, watch_id: int, seen: datetime | None) -> bool:
        """Clear the interaction only if it is still the one the caller saw"""
        condition = (
            Watch.alert_interacted_at.is_(None)
            if seen is None
            else Watch.alert_interacted_at == seen
        )
        result = self.session.exec(
            update(Watch)
            .where(Watch.id == watch_id, condition)
            .values(alert_interacted_at=None)
        )
        self.session.commit()
        return result.rowcount > 0


@dataclass(frozen=True)
class PendingRetireRecord:
    id: int
    user_id: int
    chat_id: int
    message_id: int
    text: str
    not_before: datetime
    attempts: int


class PendingRetireRepository:
    """Messages waiting to lose their buttons (see src/watches/alert_ops.py)"""

    def __init__(self, session: Session):
        self.session = session

    def _find(self, chat_id: int, message_id: int) -> PendingRetire | None:
        statement = select(PendingRetire).where(
            PendingRetire.chat_id == chat_id, PendingRetire.message_id == message_id
        )
        return self.session.exec(statement).first()

    def add(
        self,
        user_id: int,
        chat_id: int,
        message_id: int,
        text: str,
        not_before: datetime,
    ) -> None:
        """Queue a message; re-adding the same message replaces text and time"""
        row = self._find(chat_id, message_id)
        if row is None:
            row = PendingRetire(
                user_id=user_id,
                chat_id=chat_id,
                message_id=message_id,
                text=text,
                not_before=not_before,
            )
        row.user_id = user_id
        row.text = text
        row.not_before = not_before
        row.attempts = 0
        self.session.add(row)
        self.session.commit()

    @staticmethod
    def _record(row: PendingRetire) -> PendingRetireRecord:
        return PendingRetireRecord(
            id=row.id,
            user_id=row.user_id,
            chat_id=row.chat_id,
            message_id=row.message_id,
            text=row.text,
            not_before=row.not_before,
            attempts=row.attempts,
        )

    def get(self, retire_id: int) -> PendingRetireRecord | None:
        row = self.session.get(PendingRetire, retire_id)
        return None if row is None else self._record(row)

    def due(self, now: datetime) -> list[PendingRetireRecord]:
        statement = (
            select(PendingRetire)
            .where(PendingRetire.not_before <= now)
            .order_by(PendingRetire.id)
        )
        return [self._record(r) for r in self.session.exec(statement)]

    def list_for_user(self, user_id: int) -> list[PendingRetireRecord]:
        """Every queued message of the user, due or not"""
        statement = (
            select(PendingRetire)
            .where(PendingRetire.user_id == user_id)
            .order_by(PendingRetire.id)
        )
        return [self._record(r) for r in self.session.exec(statement)]

    def touch(self, chat_id: int, message_id: int, not_before: datetime) -> bool:
        """Postpone a queued message (never brings it forward)"""
        row = self._find(chat_id, message_id)
        if row is None:
            return False
        if row.not_before < not_before:
            row.not_before = not_before
            self.session.commit()
        return True

    def discard(self, chat_id: int, message_id: int) -> bool:
        result = self.session.exec(
            delete(PendingRetire).where(
                PendingRetire.chat_id == chat_id,
                PendingRetire.message_id == message_id,
            )
        )
        self.session.commit()
        return result.rowcount > 0

    def reschedule(
        self, retire_id: int, not_before: datetime, attempts: int | None = None
    ) -> None:
        row = self.session.get(PendingRetire, retire_id)
        if row is None:
            return
        row.not_before = not_before
        if attempts is not None:
            row.attempts = attempts
        self.session.commit()

    def delete(self, retire_id: int) -> None:
        self.session.exec(delete(PendingRetire).where(PendingRetire.id == retire_id))
        self.session.commit()
