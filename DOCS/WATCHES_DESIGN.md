# Watches: Technical Design

Status: approved requirements R1–R16 (owner), design for implementation on `feature/watches`, revision 2 (critic
issues resolved, see section 12).
Scope: replaces subscriptions + global date range with **watches**, adds onboarding/search, a persistent reply
keyboard, an alert-message lifecycle with no overlapping interactive messages, and keeps in-bot booking.

## 0. Facts this design relies on (verified against the live API and the code on 2026-10-22)

| Fact | Consequence |
|---|---|
| `available-calendar/` needs a captcha token for **all** offices now (Bürgerbüro too) | Every check, immediate check and booking step needs a token |
| One call accepts many `officeIds` of **one** service; mixing services, or **one office not related to the service**, → `400 invalidLocationAndServiceCombination` for the whole call | Group per service; query only offices in the service's current public relations; per-office fallback (7 step 5) |
| A bad/expired token → `400 {"errors":[{"errorCode":"captchaInvalid"}]}` (also `captchaExpired`, `captchaMissing`) | Error codes must reach the caller: invalidate token, re-solve, retry once |
| Range ≤ 365 days works, 400 days → `400` | Cap every query end at `today + 364` and reject typed dates beyond that |
| `availableDays[].providerIDs` lists offices with slots that day; `offices[].appointments` filled for **one day only** and possibly for only some of that day's offices | Slot identity is **(day, office)**; times may need one extra call per day (1.4) |
| Popular ids all present; 1063475/1063441/1063453 have 7 public offices, two of them named "Bürgerbüro Ruppertstraße" | Office labels must be disambiguated |
| Captcha token TTL 300 s | Shared token cache, refreshed at 280 s, fetched right before each call |
| PTB 22.8 processes updates one at a time (`concurrent_updates` not set); no `job-queue` extra installed; no rate limiter | Slow work (captcha + HTTP) runs in background tasks (3.2 `background`); no `conversation_timeout`; add `python-telegram-bot[rate-limiter]` |
| `register_user` stores `start=today`, `end=today+180` for every new user; `/setdates` "6 months" preset also gives 180 days; `/setdates` accepts unpadded dates (`2026-1-5`) and stores them raw | Migration v2 is written in Python and treats a 180-day range as "asap" (2) |

Definitions used below: **slot** = `Slot(day: date, office_id: int)`; **slot time** = `SlotTime(ts: int, office_id: int)`;
**today** = current date in `Europe/Berlin`; DB timestamps are naive UTC (existing convention).

---

## 1. Data model

### 1.1 `Watch` (new table `watches`, `src/db_models.py`)

```python
class Watch(SQLModel, table=True):
    __tablename__ = "watches"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.user_id", index=True)
    service_id: int = Field(index=True)
    office_id: Optional[int] = None            # None = all public offices of the service

    # "when"
    when_kind: str = Field(max_length=8)       # "asap" | "within" | "before" | "between"
    within_days: Optional[int] = None          # 14 | 30 | 90, only for "within"
    date_from: Optional[str] = Field(default=None, max_length=10)  # ISO, only "between"
    date_to: Optional[str] = Field(default=None, max_length=10)    # ISO; "before": exclusive deadline, "between": inclusive end

    # lifecycle
    status: str = Field(default="active", max_length=8, index=True)  # "active" | "paused" | "ended"
    pause_reason: Optional[str] = Field(default=None, max_length=8)  # "user" | "blocked", only when paused
    end_reason: Optional[str] = Field(default=None, max_length=8)    # "deadline" | "booked" | "stopped" | "gone"
    created_at: NaiveDatetime = Field(default_factory=datetime.utcnow)
    updated_at: NaiveDatetime = Field(default_factory=datetime.utcnow)
    ended_at: Optional[NaiveDatetime] = None

    # last check
    last_checked_at: Optional[NaiveDatetime] = None
    last_snapshot: Optional[str] = None        # JSON of WatchSnapshot (1.4)

    # alert lifecycle (R11)
    alerted_slots: str = "[]"                  # JSON list of slot keys already alerted (6.2)
    alert_chat_id: Optional[int] = None        # live alert message; both None = no live alert
    alert_message_id: Optional[int] = Field(default=None, index=True)
    alert_kind: Optional[str] = Field(default=None, max_length=8)   # "slots" | "empty" | "ended"
    alert_sent_at: Optional[NaiveDatetime] = None
    alert_shown_slots: str = "[]"              # JSON list of slot keys rendered in the live alert
    alert_render_hash: Optional[str] = Field(default=None, max_length=40)  # sha1(text + markup json)
    alert_interacted_at: Optional[NaiveDatetime] = None
```

Lifecycle fields live on `Watch` (strict 1:1, no join). Slot key format: `"YYYY-MM-DD@<office_id>"`, lists sorted.

"Open" watch = status `active` or `paused`.

- **Uniqueness: at most one open watch per `(user_id, service_id)`.** Choosing the same service again updates that
  watch's office and time (upsert, 3.2) and the result message carries `alert.updated_existing`. This removes the
  "same slot in two live alerts" overlap. Enforced in `WatchRepository`, not by a DB constraint.
- **Limit: 5 open watches per user** (paused counts). Enforced in `WatchRepository` in the same transaction:
  `create_or_update` (when it creates) and `set_when`/`set_office` on an **ended** watch raise `LimitReached` when
  `count_open >= 5`. Migrated users above 5 are grandfathered (they cannot add or reopen until ≤ 4 open).
- `kind = "ended"` live alert: the S17/S17g message of an ended watch (alerted = ∅). Reopening the watch
  (`set_when`) closes it as `outdated` like any live alert, so old Extend buttons never stay live.

### 1.2 Changes to existing tables, new table

| Table | Change |
|---|---|
| `users` | add `booking_name VARCHAR(255) NULL`, `booking_email VARCHAR(255) NULL`, `nav_message_id INTEGER NULL` (current nav screen, 3.2 `screens`), `ui_version INTEGER NOT NULL DEFAULT 0` (model: `sa_column_kwargs={"server_default": "0"}` so fresh and migrated schemas match; 0 = old UI, 1 = new chat command list set, 2 = reply keyboard delivered). `start_date`/`end_date` stay but are never read or written again |
| `booking_sessions` | add `watch_id INTEGER NULL` (NULL for `book_<date>_<oid>_<sid>` buttons), `message_id INTEGER NULL` (latest booking message that carries buttons). `captcha_token` is written `""` (column is NOT NULL) and never read: every booking step fetches a token (8) |
| `service_subscriptions` | unchanged, no longer read except by `/stop` (deletes the user's rows) |
| `pending_retires` (new) | `id PK`, `user_id INT index`, `chat_id INT`, `message_id INT`, `text TEXT` (rendered final/outdated HTML), `not_before DATETIME index`, `attempts INT DEFAULT 0`, `created_at DATETIME`. Unique `(chat_id, message_id)`. Messages that still carry buttons and must be stripped/finalized, but could not be yet (6.3) |

`ServiceSubscription` model stays so `create_all` keeps the table. Rows are kept for rollback safety; dropping them
is a later migration v3 (not in scope).

### 1.3 "When" (`src/watches/when.py`, pure)

```python
ASAP_HORIZON_DAYS = 180
MAX_QUERY_DAYS = 364          # API rejects ranges ≥ ~400 days; 364 keeps us safely inside
PRESETS = {"asap": WhenSpec("asap"), "2w": WhenSpec("within", 14),
           "1m": WhenSpec("within", 30), "3m": WhenSpec("within", 90)}

@dataclass(frozen=True)
class WhenSpec:
    kind: Literal["asap", "within", "before", "between"]
    within_days: int | None = None
    date_from: date | None = None
    date_to: date | None = None

@dataclass(frozen=True)
class Window:
    start: date
    end: date            # inclusive

def today_berlin() -> date
def effective_window(spec: WhenSpec, today: date) -> Window | None   # None = deadline passed
def parse_user_date(text: str, today: date) -> date | None
def parse_date_range(text: str, today: date) -> tuple[date, date] | None
def validate_before(d: date, today: date) -> DateError | None
def validate_between(a: date, b: date, today: date) -> DateError | None
def migrated_when(start_raw: str | None, end_raw: str | None, today: date) -> WhenSpec   # section 2
class DateError(StrEnum): FORMAT, PAST, TOO_FAR, ORDER
```

Date parsing (`parse_user_date`, whole stripped text must be one token):

| Form | Example | Rule |
|---|---|---|
| ISO, padding optional | `2026-11-15`, `2026-1-5` | `strptime("%Y-%m-%d")` |
| `D.M.YYYY` | `15.11.2026`, `5.1.2027` | |
| `D.M.YY` | `15.11.26` | year `2000 + YY` |
| `D.M` | `15.11` | first occurrence on or after `today − 30 days`: a date passed up to 30 days ago stays in the past (a typo gets PAST, a range may start in the past), today stays today, older dates roll to next year |

Invalid calendar dates (31.02, month 13) → None. `parse_date_range` finds date tokens with
`DATE_TOKEN = r"\d{4}-\d{1,2}-\d{1,2}|\d{1,2}\.\d{1,2}(?:\.\d{2,4})?"` and requires **exactly two** (any text between
them is ignored, so `2026-11-15 - 2026-12-01`, `1.11 bis 15.11`, `с 01.11.2026 до 15.11.2026` all work); each token
goes through `parse_user_date`.

Window rules (all clipped to `end ≤ today + MAX_QUERY_DAYS`):

| kind | window | ends (→ `None`) when |
|---|---|---|
| asap | `[today, today+180]` | never |
| within N | `[today, today+N]` | never |
| before D | `[today, D−1]` | `today ≥ D` |
| between A..B | `[max(A, today), B]` | `today > B` |

Validation: `before D` needs `today < D ≤ today+364` (else PAST / TOO_FAR); `between A B` needs `A ≤ B`,
`B ≥ today`, `B ≤ today+364` (ORDER / PAST / TOO_FAR). A in the past is accepted and clipped.

### 1.4 Snapshot (`src/watches/slots.py`, pure)

```python
BOOK_BUTTON_DAYS = 3

class Slot(NamedTuple): day: date; office_id: int
class SlotTime(NamedTuple): ts: int; office_id: int

@dataclass(frozen=True)
class WatchSnapshot:
    checked_at: datetime                   # naive UTC
    ok: bool                               # False: query failed, nothing else is meaningful
    slots: frozenset[Slot] = frozenset()
    earliest_times: tuple[SlotTime, ...] = ()   # all times of the earliest day, sorted by ts

    @property
    def earliest_day(self) -> date | None
    def days(self) -> list[date]           # sorted distinct days

def slot_key(s: Slot) -> str; def parse_slot_key(k: str) -> Slot
def encode_slots(s: frozenset[Slot]) -> str; def decode_slots(raw: str) -> frozenset[Slot]
def snapshot_to_json(s: WatchSnapshot) -> str; def snapshot_from_json(raw: str | None) -> WatchSnapshot | None
def top_days(slots: frozenset[Slot], n: int = BOOK_BUTTON_DAYS) -> frozenset[date]   # n earliest distinct days
def prune_past(slots: frozenset[Slot], today: date) -> frozenset[Slot]
def slots_in_scope(calendar: dict, office_ids: set[int], window: Window) -> frozenset[Slot]
def calendar_times(calendar: dict, day: date, office_ids: set[int]) -> tuple[SlotTime, ...] | None
    # None unless the calendar carries an `appointments` entry for `day` for EVERY office in
    # providerIDs(day) ∩ office_ids; the caller then fetches that day (7 step 6)
def times_for_offices(times: tuple[SlotTime, ...], office_ids: set[int]) -> tuple[SlotTime, ...]
```

Counting for users: "**N free days**, earliest Thu 29.10" (distinct days). The total number of time slots is not
knowable without one call per day, so R10's "N free slots" is shown as free days.

### 1.5 Status and end reasons

```
            create / change time / extend / any office
                     │
      ┌──── pause ──▶ paused ── resume ───┐       pause_reason "user" (button) | "blocked" (Forbidden)
      ▼                                   │
   active ◀───────────────────────────────┘
      │ deadline passed (checker) → ended/deadline  (paused watches end silently)
      │ office/service no longer public (checker) → ended/gone
      │ booking succeeded (booking) → ended/booked
      │ Stop (My watches / alert)   → ended/stopped
      ▼
    ended ── "Extend"/"Search again" (f1:edit) → active, end fields cleared
    ended/gone ── "Any office" (f1:any) → when step (S8) for an any-office watch of the service; the ended
                  watch is kept as it is, nothing changes before a time is chosen
```

`Forbidden` on any send/edit → all the user's **active** watches become `paused` with `pause_reason="blocked"`.
The next update from that user resumes exactly those (3.2 `presence`) and tells them once (`watch.resumed`).
My watches shows "paused" for both reasons; blocked pauses never reach the user while blocked anyway.

---

## 2. Migration v2 (`src/database.py::_run_migrations`)

Runs after `SQLModel.metadata.create_all` (which creates `watches`, `pending_retires` and, on a fresh DB, all new
columns), in the same `engine.begin()` transaction as the version bump. The data step is **Python**, not SQL,
because stored dates are not reliably ISO.

```python
if version < 2:
    _add_column_if_missing(conn, "users", "booking_name", "VARCHAR(255)")
    _add_column_if_missing(conn, "users", "booking_email", "VARCHAR(255)")
    _add_column_if_missing(conn, "users", "nav_message_id", "INTEGER")
    _add_column_if_missing(conn, "users", "ui_version", "INTEGER NOT NULL DEFAULT 0")
    _add_column_if_missing(conn, "booking_sessions", "watch_id", "INTEGER")
    _add_column_if_missing(conn, "booking_sessions", "message_id", "INTEGER")
    _migrate_subscriptions_to_watches(conn, today_berlin(), datetime.utcnow())
    conn.exec_driver_sql("PRAGMA user_version = 2")
```

`_add_column_if_missing` reads `PRAGMA table_info(<table>)` and runs `ALTER TABLE ... ADD COLUMN` only if absent.

`_migrate_subscriptions_to_watches(conn, today, now) -> int`:
1. `SELECT s.user_id, s.service_id, s.office_id, u.start_date, u.end_date FROM service_subscriptions s JOIN users u
   USING (user_id) ORDER BY 1, 2, 3`.
2. Group by `(user_id, service_id)`. Distinct non-NULL offices: exactly one → `office_id` = it; several → `None`
   (any office; one watch per service, 1.1); none → `None`.
3. `when = migrated_when(start_date, end_date, today)`:
   - either value missing/empty or not parseable by `strptime("%Y-%m-%d")` (accepts unpadded) → asap;
   - `start > end` → asap;
   - `(end − start).days == 180` → asap (the signup default and the "6 months" preset both produce exactly this; asap
     is the same horizon, rolling, and never ends with a deadline message). No `subscribed_at` comparison
     (local vs UTC dates differ by a day);
   - `validate_between(start, end, today)`: PAST → asap; TOO_FAR → `end = today + 364`; ok → `between(start, end)`.
   - `start > today + 364` → `between(start, end)` kept as stored; `effective_window` is then empty
     (`start > end`), so the checker and the immediate check skip the watch until its start is within the query
     horizon (the old `/setdates` had no upper bound, so these users asked only for those far dates).
   Dates are written back as ISO (`date.isoformat()`).
4. Skip the group when an open watch for `(user_id, service_id)` already exists; else INSERT (status active,
   `alerted_slots`/`alert_shown_slots` `'[]'`, timestamps `now`).

- Idempotent twice over: `user_version` guard plus the open-watch check.
- `users.start_date/end_date`, `service_subscriptions` rows: untouched. Old code still runs against this DB
  (rollback-safe; `ui_version` has a server default, so old INSERTs work).
- Users with more than 5 services keep all of them (grandfathered).
- Fresh DB: v1 and v2 run on empty tables, final `user_version` = 2.

Defensive decoding: `WatchRepository` builds `WatchRecord`s through `_decode(row) -> WatchRecord | None`; a row whose
dates/JSON fail to decode is logged (`logger.error`, watch id) and skipped by `list_active`/`list_for_user`, so one bad
row never stops the checker.

---

## 3. Module layout

`F` = foundation, `A`–`D` = streams (section 10). Every new file starts with the two `ABOUTME:` lines.

### 3.1 Foundation: pure logic (`src/watches/`)

| File | Public API |
|---|---|
| `when.py` | 1.3 |
| `slots.py` | 1.4 |
| `alert_decision.py` | 6.1 (`Interaction`, `AlertAction`, `AlertDecision`, `interaction_state`, `decide_alert`) |
| `labels.py` | `POPULAR_SERVICE_IDS: tuple[int, ...]` (R4 order); `service_label(service_id, lang) -> str` (localized short name for popular ids, else German name, ≤ 60 chars, never HTML-escaped); `office_label(office_id, service_id: int \| None = None, lang=None) -> str` (city name; same-name office choices of that service get ` · 1`, ` · 2` by id order, offices sharing a booking queue are labelled as their group's lowest id; unknown id → `watch.office_fallback`); `where_label(rec, lang)` / `where_text(service_id, office_id, lang)` (the office name when the service has only one office choice, else `watch.where_any` for any office); `only_office(service_id) -> int \| None`; `when_label(spec, lang)`; `day_label(d, lang) -> "Thu 29.10"`; `date_label(d) -> "15.11.2026"`; `ago_label(delta, lang)`; `watch_summary(rec, lang) -> "<service> · <where> · <when>"`; `watch_state(rec, lang) -> str` |
| `alert_view.py` | `render_alert(rec, snapshot, lang, *, initial: bool, updated_existing: bool = False) -> RenderedAlert`; `render_final(rec, final: FinalState, lang) -> str`; `render_outdated(lang) -> str`; `render_empty_now(rec, as_of: datetime, lang) -> RenderedAlert`; `render_ended(rec, lang) -> RenderedAlert` (S17 deadline / S17g gone); `render_booking_timed_out(lang) -> str`. `RenderedAlert(text, markup, kind, render_hash)`. `FinalState = StrEnum("booked","stopped","paused","deadline","gone","outdated")` |
| `alert_ops.py` | `alert_lock(watch_id) -> asyncio.Lock` (per-watch, process-local); `async close_live_alert(bot, watch_id, final: FinalState, lang, *, by_user: bool) -> None` (caller holds the lock, 6.3); `queue_retire(user_id, chat_id, message_id, text, not_before)`; `async process_pending_retires(bot, now) -> int` (6.3) |
| `availability.py` | `CallResult(ok: bool, data: dict \| None, error: ApiError \| None)`, `ApiError = StrEnum("token","combination","other")`; `watch_office_ids(rec) -> list[int]` (watch office plus the public offices sharing its booking queue, or all **public** offices of the service); `public_office_ids(service_id) -> frozenset[int]` (public relations, without offices whose `disabledByServices` lists the service: the website hides them and they return no days); `office_choices(service_id) -> list[int]` (public offices with each `sharedBookingOfficeIds` group collapsed to its lowest id, as the website lists them); `booking_group(service_id, office_id) -> list[int]` (these office indexes are built once per catalog with `services_manager.per_catalog`); `async fetch_calendar(service_id, office_ids, start, end, slots_day=None) -> CallResult`; `async fetch_day_times(service_id, office_ids, day) -> tuple[SlotTime, ...] \| None` (with the per-office combination fallback); `async snapshot_for_watch(rec, today) -> WatchSnapshot`. Every call gets `captcha_token.get_token(min_ttl=30)` **right before** the HTTP request (`asyncio.to_thread`); on `ApiError.token` it calls `captcha_token.invalidate()`, gets a new token and retries once |

### 3.2 Foundation: data access, services, UI, wiring

| File | Public API / change |
|---|---|
| `src/db_models.py` | 1.1, 1.2 |
| `src/database.py` | migration v2 (section 2) |
| `src/repositories.py` | `WatchRecord` (frozen dataclass: id, user_id, service_id, office_id, when: WhenSpec, status, pause_reason, end_reason, ended_at, last_checked_at, snapshot: WatchSnapshot \| None, alerted: frozenset[Slot], live: LiveAlert \| None, interacted_at). `LiveAlert(chat_id, message_id, kind, sent_at, shown: frozenset[Slot], render_hash)`. `LimitReached(Exception)`. `WatchRepository(session)`: `create_or_update(user_id, service_id, office_id, when) -> tuple[WatchRecord, bool]` (bool = updated existing open watch; creates only below the limit); `find_open(user_id, service_id)`; `count_open(user_id) -> int`; `get(watch_id)`; `get_for_user(watch_id, user_id)`; `list_for_user(user_id, ended_since: datetime \| None) -> list[WatchRecord]` (open first by created_at, then ended with reason booked/deadline/gone since `ended_since`); `list_active()`; `set_when(watch_id, when)` (→ active, clears end/pause fields, alerted=∅; limit check when reopening); `set_office(watch_id, office_id \| None)` (limit check when the watch is ended); `set_status(watch_id, status, *, pause_reason=None, end_reason=None)`; `pause_all_for_user(user_id, reason="blocked") -> int`; `resume_blocked(user_id) -> int`; `record_check(watch_id, snapshot)`; `set_live_alert(watch_id, chat_id, message_id, kind, shown, alerted, render_hash)` (also clears `alert_interacted_at`); `update_live_alert(watch_id, kind, shown, alerted, render_hash)`; `clear_live_alert(watch_id, reset_alerted: bool, alerted: frozenset[Slot] \| None = None)` (**always** clears `alert_interacted_at`); `set_alerted(watch_id, alerted)`; `mark_interaction(chat_id, message_id, at) -> int \| None`; `clear_interaction(watch_id, seen: datetime \| None) -> bool` (`UPDATE … WHERE alert_interacted_at IS :seen`); `counts() -> dict[str, int]`. `PendingRetireRepository`: `add(...)` (upsert on chat/message), `due(now) -> list`, `touch(chat_id, message_id, not_before)`, `discard(chat_id, message_id)`, `reschedule(id, not_before)`, `delete(id)`. `UserRepository`: `set_booking_contact`, `clear_booking_contact`, `set_ui_version(user_id, v)`, `get_nav_message_id`, `set_nav_message_id(user_id, mid \| None)`, `delete_user_cascade(user_id) -> None` (one session: pending_retires, watches, booking_sessions, service_subscriptions, then the user row; `appointment_logs` has no user column). `BookingSessionRepository`: `create_session(..., watch_id=None, message_id=None)`, `update_session(..., office_id=None, message_id=None)`, `is_user_in_booking` becomes **read-only** (`expires_at > now`, no delete), `get_active(user_id) -> BookingSessionRecord \| None` (None when expired), `pop_expired_sessions() -> list[BookingSessionRecord]` (returns then deletes), `pop_all_sessions() -> list[BookingSessionRecord]` |
| `src/munich_api_client.py` | add `get_result(endpoint, params) -> ApiResponse` and `post_result(endpoint, data) -> ApiResponse`, `ApiResponse(data: dict \| None, status: int \| None, error_codes: tuple[str, ...])` parsed from `errors[].errorCode` of 4xx bodies; `get`/`post` unchanged |
| `src/services_manager.py` | office fallback label via `t("watch.office_fallback")` (the `buttons` area goes away); `refresh_catalog() -> bool` (re-fetches the payload, replaces caches only on success; `post_init` runs it in a thread, the checker every 6 h, or every minute while no catalog is loaded); `get_full_payload`/`get_services` only read the cache, never fetch (they run on the event loop); `catalog_loaded() -> bool` |
| `src/services/captcha_token.py` | `async get_token(min_ttl: float = 30.0) -> str \| None` (cached token if ≥ `min_ttl` s left, else solves a new one under an `asyncio.Lock`; TTL 280 s; None on failure); `invalidate() -> None`; `is_token_error(codes) -> bool` (`captchaInvalid`, `captchaExpired`, `captchaMissing`) |
| `src/ui/telegram_safe.py` | `EditOutcome = StrEnum("ok","not_modified","gone","forbidden","failed")`; `async safe_edit_text(bot, chat_id, message_id, text, markup=None, parse_mode="HTML") -> EditOutcome`; `async safe_strip_markup(bot, chat_id, message_id) -> EditOutcome`; `async safe_delete(bot, chat_id, message_id) -> bool`; `async safe_send(bot, chat_id, text, markup=None, silent=False) -> tuple[Message \| None, EditOutcome]`; `async safe_answer(query, text=None, show_alert=False) -> bool` (swallows "Query is too old…" / "query id is invalid"); `classify(exc) -> EditOutcome` ("message is not modified" → not_modified; "message to edit not found", "message can't be edited", "message to delete not found" → gone; `Forbidden` → forbidden; `RetryAfter` (after the limiter's retries), network, else → failed). Never raises Telegram errors |
| `src/ui/background.py` | `user_lock(user_id) -> asyncio.Lock`; `run_for_user(context, update, user_id, coro) -> None` (`context.application.create_task(_locked(coro), update=update)`; per-user lock keeps one user's slow tasks in order; exceptions go to the error handler) |
| `src/ui/callbacks.py` | builders + `parse(data) -> Cb \| None` for section 4, `assert len(data.encode()) <= 64` in every builder; patterns `FIND_RE`, `WATCH_RE`, `SETTINGS_RE`, `BOOK_DAY_RE`, `BOOK_RE`, `NAV_RE = r"^(f1\|w1\|s1):\|^lang:\|^language$"` |
| `src/ui/keyboard.py` | `MenuAction = StrEnum("find","watches","settings","help")`; `main_keyboard(lang) -> ReplyKeyboardMarkup`; `menu_action(text) -> MenuAction \| None`; `MENU_FILTER: filters.BaseFilter` (`filters.Text(all labels of all languages)`) |
| `src/ui/commands_menu.py` | `BOT_COMMANDS = ("start","find","watches","settings","help","language","stop")`; `bot_commands(lang)`; `async set_default_commands(bot)`; `async set_chat_commands(bot, chat_id, lang)` (moved from `language.py`, which imports them) |
| `src/ui/screens.py` | `async show_screen(update, context, text, markup, parse_mode="HTML") -> Message` — nav screens only. Pointer = `users.nav_message_id`. Callback update: if the stored id differs from the pressed message, `safe_strip_markup` the stored one; edit the pressed message ("not modified" ignored); store its id. Message/command update: send new, `safe_strip_markup` the stored one, store the new id. `forget_nav_message(user_id, message_id=None)` (clears the pointer if it equals `message_id` or unconditionally); `async retire_nav_message(bot, user_id)` |
| `src/handlers/interaction_tracker.py` | `async record_interaction(update, context)` (group -2, every callback): `WatchRepository.mark_interaction(chat_id, message_id, now)` and `PendingRetireRepository.touch(chat_id, message_id, now + INTERACTION_LOCK)`; never answers the query |
| `src/handlers/presence.py` | `async on_presence(update, context)` (group -3, private message/callback updates from a registered user with a language): (1) `resume_blocked(user_id) > 0` → send `watch.resumed` (`{count}`); (2) `ui_version < 2` and the update is not `/start` or a `lang:` callback → `set_chat_commands` if `ui_version < 1`, send `keyboard.upgrade` with `main_keyboard(lang)`, `set_ui_version(2)`. One indexed query per update; never stops other groups |
| `src/handlers/errors.py` | `async on_error(update, context)`: `logger.error(..., exc_info=context.error)`, `track_event("handler_error", error_type=...)` |
| `src/commands/language.py` | only `GATE_FREE_CALLBACK_PREFIXES += ("b1:", "s1:del")` and import of the moved command helpers |
| `pyproject.toml`, `uv.lock` | `python-telegram-bot[rate-limiter]>=22.8` (Dockerfile installs from `pyproject.toml`, no change; docker-compose unchanged) |
| `telegram_bot.py` | final wiring (3.4) |
| catalogs | areas `keyboard`, `watch`, `alert` filled (en+ru); areas `find`, `watches`, `settings`, `checker` created with `MESSAGES = {}`; all registered in both `AREAS` |
| stubs | every stream entry point in 3.3 created with its final signature and body `raise NotImplementedError` so wiring imports work |

### 3.3 Stream modules

**A — setup flow**

| File | Public API |
|---|---|
| `src/commands/find.py` | `async find_command(update, context)` (/find, /menu, /subscribe, reply "Find"); `build_find_screen(lang) -> tuple[str, InlineKeyboardMarkup]`; `async find_callback(update, context)` (all `f1:`); `async show_categories(update, context)`; `async show_category_page(update, context, category_id: str, page: int)`; `async show_service_step(update, context, service_id: int)` (limit check skipped when the user already has an open watch for the service → office step or when step); `async show_when_step(update, context, service_id: int, office_id: int \| None)` |
| `src/handlers/text_input.py` | `async on_text(update, context)`: pending typed-date answer → if the text contains no digit, clear `AWAIT_KEY` and search; else date handler; no pending answer → search. `clear_pending_input(context) -> None`; `AWAIT_KEY = "await_date"` (user_data: `{"kind": "before"\|"range", "service_id", "office_id", "watch_id" \| None, "prompt_msg_id"}`) |
| `src/services/service_search.py` | `normalize(text) -> str`; `SYNONYMS: dict[str, tuple[int, ...]]`; `search_services(query, services, limit=8) -> list[dict]` (pure) |
| `src/services/immediate_check.py` | `async start_watch_check(update, context, user_id, service_id, office_id, when, *, target_message_id: int \| None) -> None` and `async start_recheck(update, context, watch_id, when, *, target_message_id: int \| None) -> None`. Foreground: edit `target_message_id` to S11, or when None (typed-date path) **send** a new S11 below the user's text and strip the prompt's buttons; then `run_for_user(...)` the background part (6.4). Never blocks the update queue on the network |

**B — navigation**

| File | Public API |
|---|---|
| `src/handlers/menu_keyboard.py` | `async menu_text(update, context)` (dispatch on `menu_action`; clears `AWAIT_KEY`) |
| `src/commands/watches.py` | `async watches_command(update, context)` (/watches, /myservices, /status, /setdates, reply "My watches"); `async watches_callback(update, context)` (all `w1:`); `build_watches_screen(user_id, lang, now) -> tuple[str, InlineKeyboardMarkup]` |
| `src/commands/settings.py` | `async settings_command(update, context)`; `async settings_callback(update, context)` (all `s1:`) |
| `src/commands/help.py` | `async help_command(update, context)` |
| `src/commands/start.py` | `async start_command(update, context)`; `async send_onboarding(bot, chat_id, user_id, lang, returning: bool)` (sets `ui_version = 2`) |
| `src/commands/stop.py` | `async stop_command(update, context)` (confirmation); deletion from `settings_callback` (`s1:dely`) via `async delete_user_data(bot, user_id, lang) -> None` (9.5), then `context.user_data.clear()` |
| `src/commands/language.py` | `language_choice_callback` → onboarding (first choice, `ui_version = 2`) or Settings + keyboard refresh (change); `menu.not_registered` replaced by `start.not_registered` |
| `src/handlers/fallback_callbacks.py` | `async fallback_callback(update, context)` (catch-all, section 9) |
| `src/services/announcement.py` | `async announce_reply_keyboard(bot) -> int` (9.3) |
| deleted | `src/commands/{menu,subscribe,myservices,setdates,status}.py`, `src/handlers/buttons.py` |

**C — checker + alert lifecycle**

| File | Public API |
|---|---|
| `src/services/appointment_checker.py` | `check_and_notify(application)` (loop), `run_check_cycle(bot, today, now) -> CycleResult` (one pass, testable), `get_stats`, `set_bot_start_time`, `increment_bookings_started`, `increment_bookings_completed`, `send_health_alert`. Removes `get_user_date_range` and its own token globals |
| `src/services/alert_lifecycle.py` | `async apply_alert(bot, watch_id, snapshot, now, booking_active: Callable[[int], bool]) -> AlertAction`; `async end_watch_by_checker(bot, watch_id, reason: Literal["deadline","gone"], now, rejected_offices: frozenset[int] = frozenset()) -> bool`; `async cleanup_expired_bookings(bot) -> int` |
| `src/commands/stats.py` | admin `/stats` counting watches |
| `src/services/queue_manager.py` | `is_user_in_queue` unchanged in signature (now side-effect free through F's repository change) |
| deleted | `src/services/notification_service.py` |

**D — booking**

| File | Public API |
|---|---|
| `src/commands/booking.py` | `booking_conversation` (ConversationHandler, group 0); `async booking_orphan_callback(update, context)` (group 1, `b1:` and `UNVERSIONED_BOOKING_RE` callbacks outside a conversation); `async end_all_booking_sessions(bot) -> int` (post_init, 8.7) |
| `src/booking_api.py` | reserve step uses `post_result`; token error → `invalidate`, new token, retry once |

### 3.4 Handler wiring (`telegram_bot.py`, written by F)

Builder: `.rate_limiter(AIORateLimiter(max_retries=2))`; `application.add_error_handler(on_error)`.
`PRIVATE = filters.ChatType.PRIVATE` is added to every `CommandHandler` and `MessageHandler` below.

| Group | Handler | Notes |
|---|---|---|
| -3 | `TypeHandler(Update, on_presence)` | resume blocked pauses, deliver reply keyboard once |
| -2 | `CallbackQueryHandler(record_interaction)` | runs for every callback, never stops |
| -1 | `TypeHandler(Update, language_gate)` | unchanged |
| 0 | `booking_conversation` | only handler in group 0 (D rules in 8.5) |
| 1 | `CommandHandler`: start, find, watches, settings, help, language, stop, stats; aliases menu/subscribe → `find_command`, myservices/status/setdates → `watches_command` | |
| 1 | `CallbackQueryHandler(language_choice_callback, "^lang:")`, `(language_menu_callback, "^language$")` | |
| 1 | `CallbackQueryHandler(find_callback, FIND_RE)`, `(watches_callback, WATCH_RE)`, `(settings_callback, SETTINGS_RE)`, `(booking_orphan_callback, BOOK_RE \| UNVERSIONED_BOOKING_RE)` | |
| 1 | `MessageHandler(PRIVATE & MENU_FILTER, menu_text)` | before the search catch-all |
| 1 | `MessageHandler(PRIVATE & filters.TEXT & ~filters.COMMAND, on_text)` | search / typed date |
| 1 | `CallbackQueryHandler(fallback_callback)` | catch-all, last |

Every callback handler calls `safe_answer(query)` first (D's toasts call it with text instead).

`post_init`, in order: `set_bot_start_time`; `set_default_commands`; `await end_all_booking_sessions(bot)` (8.7);
then **one** task `startup_sequence(application)` that awaits `announce_reply_keyboard(bot)` and then runs
`check_and_notify(application)`, so no push for a migrated watch precedes the announcement or the command-list update.

---

## 4. Callback data and reply keyboard

### 4.1 Callback data (ids ≤ 10 digits; longest ≈ 34 bytes)

| Data | Owner | Action |
|---|---|---|
| `f1:home` | A | Find screen |
| `f1:all` | A | categories |
| `f1:cat:<cat_id>:<page>` | A | category page (cat ids = `CATEGORY_KEYWORDS` keys) |
| `f1:svc:<sid>` | A | service chosen |
| `f1:off:<sid>:<oid>` | A | office chosen, `oid` 0 = any |
| `f1:when:<sid>:<oid>:<p>` | A | `p` ∈ `asap,2w,1m,3m` → create/update + immediate check |
| `f1:date:<sid>:<oid>:<m>` | A | `m` ∈ `b` (before), `r` (range) → typed-date prompt |
| `f1:edit:<wid>` | A | when step for an existing watch (Change time, Extend, Search again) |
| `f1:ewhen:<wid>:<p>` | A | preset for existing watch |
| `f1:edate:<wid>:<m>` | A | typed date for existing watch |
| `f1:any:<wid>` | A | ended/gone watch: when step (S8) for the service with any office (limit checked first); the time choice creates/updates the open watch, the ended one is not changed |
| `f1:x` | A | cancel typed-date prompt |
| `w1:list` | B | My watches |
| `w1:pause:<wid>` / `w1:resume:<wid>` | B | pause / resume |
| `w1:stop:<wid>` / `w1:stopy:<wid>` / `w1:stopn:<wid>` | B | stop: ask / yes / no |
| `s1:home` | B | Settings |
| `s1:forget` | B | forget saved booking details |
| `s1:del` / `s1:dely` / `s1:deln` | B | delete data: ask / yes / no |
| `b1:<wid>:<yyyymmdd>` | D | Book a day (conversation entry) |
| `b1:t:<oid>:<ts>` | D | pick time |
| `b1:me` / `b1:chg` / `b1:ok` / `b1:x` | D | saved contact yes / change / confirm / cancel |
| `lang:<code>`, `language` | B | unchanged |

Versioning: the digit in the prefix is the scheme version. An incompatible change gets a new prefix (`f2:`); old
prefixes then fall through to `fallback_callback`. Regexes: `FIND_RE=r"^f1:"`, `WATCH_RE=r"^w1:"`,
`SETTINGS_RE=r"^s1:"`, `BOOK_DAY_RE=r"^b1:\d+:\d{8}$"`, `BOOK_RE=r"^b1:"`.

Double tap guard (A): `f1:when`/`f1:ewhen`: if `context.user_data["checking"] == pressed message id` (set in the
foreground, cleared in the background task's `finally`), or the pressed message is already the watch's live alert
and the `WhenSpec` is unchanged → `safe_answer` and return.

### 4.2 Reply keyboard

Catalog area `keyboard` (F): `keyboard.find` "🔎 Find a Termin" / "🔎 Найти запись", `keyboard.watches`
"👀 My watches" / "👀 Мои поиски", `keyboard.settings` "⚙️ Settings" / "⚙️ Настройки", `keyboard.help` "❓ Help" / "❓ Помощь",
`keyboard.upgrade` (one short line: "The menu is now at the bottom of the chat.").
Layout 2×2, `resize_keyboard=True`, `is_persistent=True`.

Matching: `menu_action(text)` compares `text.strip()` against a dict built at import from `t(key, lang)` for every
supported language, so a Russian label works for an English user and vice versa (keyboards survive a language
switch). `MENU_FILTER = filters.Text(list(that dict))`. A test asserts the labels are unique across actions.

The keyboard is attached on: onboarding welcome, `/start`, language change confirmation, the announcement (9.3), and
the one-time `keyboard.upgrade` line from `presence` for any user still below `ui_version` 2. Every one of these
sets `ui_version = 2`.

---

## 5. Screens

Conventions: all text via `t()`; HTML parse mode; service/office/user-supplied strings pass through `html.escape`.
"Nav screen" = edited in place when reached by a button, sent via `show_screen` otherwise (old nav message stripped).
Screens shown on an alert or booking message (S19 from an alert, S25–S29) use `telegram_safe` directly and never
become the nav pointer. Key names are listed without values; values are written by the owning stream in en and ru.

| # | Screen | Trigger / handler | Text keys | Buttons |
|---|---|---|---|---|
| S1 | Language picker | `/start` new user, gate | unchanged | unchanged |
| S2 | Welcome (2 lines) | after first language choice / `/start` (B `send_onboarding`) | `start.welcome` / `start.welcome_back` | reply keyboard |
| S3 | Find: "What do you need?" + type-to-search hint | S2 follow-up (new users, returning users with 0 open watches; returning users with watches get S18 instead), `/find`, reply Find, `f1:home` (A) | `find.title` | 8 popular (1/row, so long labels are not cut, emoji + `watch.svc_<id>`, missing ids skipped) → `f1:svc`; `find.btn_all` → `f1:all` |
| S4 | Search results | plain text (A `on_text`) | `find.results` (`{query}`), `find.nothing` | ≤ 8 services (popular label or truncated German name) → `f1:svc`; `find.btn_all` |
| S5 | Categories | `f1:all` | `find.categories` | `categories.<id> (n)` 2/row → `f1:cat:<id>:0`; `find.btn_back` → `f1:home` |
| S6 | Category page | `f1:cat` | `find.category_page` (`{category}`, `{first}`, `{last}`, `{total}`) | 10 services → `f1:svc`; prev/next; back → `f1:all` |
| S7 | Office | `f1:svc` when > 1 office choice (`office_choices`: offices sharing a booking queue are one choice, as on the city website) | `find.where` (`{service}`) | `find.btn_any_office` → `f1:off:<sid>:0`; ≤ 10 offices sorted by label, 2/row → `f1:off`; back → `f1:home` |
| S8 | When | `f1:off`, `f1:svc` with 1 office, `f1:edit`, `f1:any` | `find.when` (`{service}`, `{where}`: the office name when the service has only one), `find.when_edit` (open watch) / `find.when_again` (ended watch), `find.when_existing` (hint when the service already has an open watch) | `find.btn_asap`, `find.btn_2w`, `find.btn_1m`, `find.btn_3m` (2/row), `find.btn_before`, `find.btn_between`, back |
| S9 | Typed date prompt | `f1:date`, `f1:edate` | `find.ask_before`, `find.ask_range` (examples: `15.11`, `15.11.2026`, `2026-11-15`) | `find.btn_cancel` → `f1:x` |
| S9e | Typed date error | `on_text` while awaiting, text with digits | `find.date_format`, `find.date_past`, `find.date_too_far`, `find.date_order` | `find.btn_cancel` (previous prompt stripped by `show_screen`) |
| S10 | Limit reached | `f1:svc` for a new service / creation / reopen with 5 open (`LimitReached`) | `find.limit`; `find.limit_over` (`{open}`, `{limit}`, `{count}` to stop) for grandfathered users above 5, whose My watches header is `watches.header_over` | `keyboard.watches` text → `w1:list` |
| S11 | Checking… | creation (A) | `find.checking` (`{service}`) | none |
| S12 | Alert, slots | S11 result or checker push (render: F) | `alert.slots` (`{summary}`, `{day}`, `{times}`, `{more}`), `alert.updated_existing` prefix after an upsert | ≤ 3 `alert.btn_book` (`{day}`) → `b1:<wid>:<day>` (earliest first, 1 per row); `alert.btn_website` (url); `alert.btn_stop` → `w1:stop:<wid>` |
| S13 | Alert, none yet | S11 result with no slots | `alert.none_yet` (`{summary}`) | none |
| S13f | Alert, check failed | S11 when token/query failed | `alert.check_failed` (`{summary}`) | none |
| S14 | Alert, gone empty | checker | `alert.empty_now` (`{summary}`, `{time}` HH:MM Berlin) | none |
| S15 | Alert, outdated | retire, change time | `alert.outdated` | none |
| S16 | Alert, final | close_live_alert | `alert.final_booked`, `alert.final_stopped`, `alert.final_paused`, `alert.final_deadline`, `alert.final_gone` (`{summary}`) | none |
| S17 | Deadline ended | checker, **silent** send, registered as live alert kind `ended` | `alert.deadline` (`{summary}`) | `alert.btn_extend` → `f1:edit:<wid>`; `alert.btn_new_search` → `f1:home` |
| S17g | Office/service gone | checker, silent, live kind `ended` | `alert.gone` (`{summary}`) | `alert.btn_any_office` → `f1:any:<wid>` (only if the service still has public offices); `alert.btn_new_search` → `f1:home` |
| S18 | My watches | `/watches`, reply, `w1:list` (B) | `watches.header` (`{count}`, `{limit}`), `watches.line` (`{n}`, `{summary}`, `{state}`, `{checked}`), `watches.empty` | per open watch one row: `watches.btn_time` (`{n}`) → `f1:edit`, `watches.btn_pause`/`btn_resume`, `watches.btn_stop`; per recent ended (booked/deadline/gone, last 7 days, max 3): `watches.btn_again` (`{n}`) → `f1:edit`; last row `watches.btn_new` → `f1:home` (if < 5 open). Empty: `watches.btn_find` → `f1:home` |
| S19 | Stop confirm | `w1:stop` (on My watches or on the alert itself) | `watches.stop_confirm` (`{summary}`) | `watches.btn_stop_yes` → `w1:stopy`, `watches.btn_stop_no` → `w1:stopn` |
| S20 | Settings | `/settings`, reply, `s1:home` | `settings.text` (`{language}`, `{contact}`), `settings.contact_none` | `language.btn_menu` → `language`; `settings.btn_forget` (only if saved); `settings.btn_delete` → `s1:del` |
| S21 | Delete confirm | `/stop`, `s1:del` | `stop.confirm` | `stop.btn_yes` → `s1:dely`, `stop.btn_no` → `s1:deln` (→ Settings, or plain "kept" text when started by /stop) |
| S22 | Deleted | `s1:dely` | `stop.done` | confirm message deleted; new message with `ReplyKeyboardRemove` |
| S23 | Language changed | `lang:<code>` (change) | `language.changed` | picker message → S20 in new language; new message `language.changed` with new reply keyboard |
| S24 | Help | `/help`, reply | `help.text` (how it works in 4 lines + commands) | `keyboard.find` → `f1:home`, `keyboard.watches` → `w1:list` |
| S25 | Book: fetching | `b1:<wid>:<day>` (D) | `booking.fetching_slots` | none |
| S26 | Book: times | D | `booking.select_time` (`{date}`) | ≤ 12 times, 2/row, "09:00" or "09:00 · <office>" when > 1 office → `b1:t`; `booking.btn_cancel` → `b1:x` |
| S26g | Book: day gone | D | `booking.day_gone` (`{date}`) ("I'll send the updated list") | none |
| S27 | Book: saved contact | `b1:t` with saved contact | `booking.use_saved` (`{time}`, `{office}`, `{name}`, `{email}`) | `booking.btn_yes_book` → `b1:me`, `booking.btn_change` → `b1:chg`, cancel |
| S28 | Book: name / email / confirm | existing texts | existing keys | existing, with `b1:ok`/`b1:x` |
| S29 | Book: success / failed / error | D | `booking.success` (+ `booking.watch_finished`), `booking.failed` (+ "I'll send updated slots"), `booking.error` | `watches` → `w1:list` |
| S30 | Booking timed out | checker cleanup (C) | `alert.booking_timed_out` | none |
| S31 | Announcement | post_init (B) | `start.announce` | reply keyboard |
| S32 | Keyboard upgrade line | `presence` (F) | `keyboard.upgrade` | reply keyboard |
| S33 | Resumed after block | `presence` (F) | `watch.resumed` (`{count}`) | none |

S12 layout (values illustrative):

```
🎉 Free slots: Wohnsitzanmeldung
Any office · as soon as possible

📅 Thu 29.10: 09:00, 09:05, 09:10 (Forstenrieder Allee), 09:55 (Ruppertstraße · 2), 10:55 (Orleansplatz)
Also free: 26.11, 03.12 and 4 more days
[📅 Book Thu 29.10]
[📅 Book 26.11]
[📅 Book 03.12]
[🌐 Website] [⏹ Stop watching]
```

Times: first 5 of `earliest_times`; office name appended only for any-office watches. Website button URL:
`config.get_booking_url_for_service(service_id, office_of_first_time_or_watch_office)`.

Typed date input: `on_text` checks `AWAIT_KEY` first. Text without any digit → `clear_pending_input` + search (the
prompt's buttons are stripped). Any menu tap, command, or `f1:`/`w1:`/`s1:` callback clears it too (`menu_text`,
command handlers via `clear_pending_input(context)` in `text_input.py`, and `find_callback`). A valid typed date
calls `start_watch_check`/`start_recheck` with `target_message_id=None`: a **new** S11 is sent below the user's text
and becomes the live alert; the prompt is stripped and forgotten as nav. The pending state is in
`context.user_data` (lost on restart; the next text then becomes a search, acceptable).

Search (`service_search`): `normalize` = casefold, `ä→a ö→o ü→u ß→ss ё→е`, then `ae→a oe→o ue→u` (applied to both
sides, so "fuehrerschein", "führerschein", "fuhrerschein" match), split on non-alphanumerics. A service matches when
every query token (≥ 2 chars) is a substring of its normalized name or a synonym phrase maps to it. Order: synonym
hits (popular order), then popular, then names starting with the first token, then shorter names. Query > 60 chars
truncated; < 2 chars → `find.nothing`. Unregistered user (no `users` row) → `start.not_registered` in the Telegram client's language (`client_language`), like every other entry point.

---

## 6. Alert lifecycle

### 6.1 Pure decision (`src/watches/alert_decision.py`)

```python
INTERACTION_LOCK = timedelta(minutes=10)

class Interaction(StrEnum): NONE = "none"; ACTIVE = "active"; RELEASED = "released"
class AlertAction(StrEnum): NOOP = "noop"; DEFER = "defer"; PUSH = "push"; EDIT = "edit"; EDIT_EMPTY = "edit_empty"

@dataclass(frozen=True)
class AlertDecision:
    action: AlertAction
    silent: bool = False            # PUSH without notification sound
    retire_previous: bool = False   # queue old live alert for "Outdated" after sending
    alerted: frozenset[Slot] | None = None   # new alerted set; None = unchanged
    clear_interaction: bool = False

def interaction_state(booking_active: bool, interacted_at: datetime | None, now: datetime) -> Interaction
    # ACTIVE if booking_active or (interacted_at and now - interacted_at < INTERACTION_LOCK)
    # RELEASED if interacted_at set and older than the lock; else NONE

def decide_alert(alerted: frozenset[Slot], current: frozenset[Slot], live_kind: str | None,
                 shown: frozenset[Slot], render_changed: bool, interaction: Interaction) -> AlertDecision
```

`booking_active` = the user has a non-expired booking session (`is_user_in_queue`, read-only) — all of that user's
watches are deferred during booking, as today. `render_changed` = `render_alert(...).render_hash != live.render_hash`.
The caller passes `alerted` already pruned with `prune_past(alerted, today)`.

### 6.2 State × event table

Live state: **N** none, **S** slots alert, **E** empty alert. `new_top = top_days(current) − days(alerted)` — days that
would get a Book button and were never alerted. Only those push; every other change is a silent in-place edit.
`merged = alerted ∪ current`.

| # | Interaction | Live | Current | Condition | Action | After |
|---|---|---|---|---|---|---|
| 1 | ACTIVE | any | any | – | DEFER | nothing changes |
| 2 | NONE/RELEASED | any | ≠ ∅ | `new_top ≠ ∅` | PUSH (sound) + retire previous if live | live = new S, shown = current, alerted = merged, interaction cleared (conditional) |
| 3 | NONE | S | ≠ ∅ | `new_top = ∅`, `current ≠ shown` or `render_changed` | EDIT in place (no push) | shown = current, alerted = merged |
| 4 | NONE | S | ≠ ∅ | `new_top = ∅`, same render | NOOP | – |
| 5 | RELEASED | S | ≠ ∅ | `new_top = ∅`, `current ≠ shown` or `render_changed` | PUSH **silent** + retire previous | live = new S, shown = current, alerted = merged, interaction cleared (conditional) |
| 6 | RELEASED | S | ≠ ∅ | `new_top = ∅`, same render | NOOP | interaction cleared (conditional) |
| 7 | NONE/RELEASED | N | ≠ ∅ | `new_top = ∅` | NOOP (message deleted by user; no repeat) | alerted = merged |
| 8 | NONE/RELEASED | S | ∅ | – | EDIT_EMPTY (S14) | live kind = E, shown = ∅, **alerted = ∅**, interaction cleared (conditional) |
| 9 | NONE/RELEASED | E or N | ∅ | – | NOOP | alerted = ∅ |

Consequences:
- Flapping `{A,B} → {A} → {A,B}`: second step row 3 (edit, alerted stays {A,B}), third step `new_top = ∅` → row 3
  edit, no push. alerted is reset only in rows 8/9 (nothing left), as R11 says.
- A new day at the far end of a rolling window, or a second office on an already-alerted day → row 3 (silent edit).
  A new earlier day, or a new day among the 3 Book days → row 2 (push).
- Invariant: live kind E ⇒ alerted = ∅, so any slots after E hit row 2 (push + retire "No free slots").
- Row 5: after an interaction ends, a change goes to a new message (R11), silently when nothing important was added.
- Row 8: going empty edits in place even after an ended interaction; a fresh message saying "nothing" would be noise.

Query failure (`snapshot.ok is False`): no decision, no state change, `last_checked_at` not updated.

### 6.3 Applying a decision (`alert_lifecycle.apply_alert`, C) and Telegram errors

`apply_alert(bot, watch_id, snapshot, now, booking_active)` does everything under `alert_lock(watch_id)`:
1. Re-read the watch; missing or not `active` → return NOOP (deleted by `/stop`, paused, ended meanwhile).
2. `interaction = interaction_state(booking_active(rec.user_id), rec.interacted_at, now)` — computed **inside** the
   lock from the re-read record.
3. Render, `decide_alert(...)`, execute:

| Step | Outcome | Handling |
|---|---|---|
| PUSH: `safe_send` | ok | `set_live_alert(new, ...)`; if `retire_previous` and an old live existed: `queue_retire(old, render_outdated, not_before=now)` |
| | forbidden | `pause_all_for_user(reason="blocked")`; track `user_blocked_bot` |
| | failed | leave state unchanged; next cycle retries |
| EDIT / EDIT_EMPTY | ok / not_modified | `update_live_alert(...)` |
| | gone | `clear_live_alert(reset_alerted=False, alerted=decision.alerted)` → row 7/9 later |
| | forbidden | as PUSH |
| | failed | unchanged |
| clear interaction | – | `clear_interaction(watch_id, seen=rec.interacted_at)`: no-op if a newer tap was recorded meanwhile |

Retires are never done inline. **Every** message that must lose its buttons and could not be edited now goes into
`pending_retires`:
- PUSH's old live alert (always queued, processed after all pushes of the cycle);
- `close_live_alert` edits that fail with `failed`, or are checker-initiated while the message is in use (below).

`process_pending_retires(bot, now)` (F, called by C at the start and end of every cycle): for each due row
(`not_before ≤ now`, ordered by id): if the message is the booking message of the user's active
booking session (`get_active`) → `reschedule(not_before = session.expires_at)`; else `safe_edit_text(text, no markup)`:
ok / not_modified / gone / forbidden → delete row; failed → `attempts += 1`, `not_before = now + 2^attempts min`;
`attempts ≥ 6` → delete row with `logger.warning`. `record_interaction` pushes `not_before` to `now + 10 min` on any
tap on a queued message, so the user's current message is never edited under them. D `discard`s a row when a Book
tap takes over that message (8.1).

`close_live_alert(bot, watch_id, final, lang, *, by_user)` (caller holds `alert_lock`): no live → return. `by_user=True`
(Stop, Pause, change time, booked, delete data — the user acted): `safe_edit_text` to S16/S15 now; failed →
`queue_retire(not_before=now)`. `by_user=False` (checker deadline/gone): if the interaction is ACTIVE or the message
is in a booking session → `queue_retire(not_before = interacted_at + 10 min or session.expires_at)`; else edit now
(failed → queue). Then `clear_live_alert(reset_alerted=True)` in both cases.

Rate limits: `AIORateLimiter(max_retries=2)` (30 msg/s overall, PTB-managed `RetryAfter` handling) covers
bursts from a popular service; the announcement runs before the checker (3.4), so they never overlap.

### 6.4 Where alerts are created, detached, interacted with

Writers of the live-alert fields (`set_live_alert`, `update_live_alert`, `clear_live_alert`, `set_alerted`) always
hold `alert_lock(watch_id)`. `mark_interaction`/`clear_interaction` are single conditional UPDATEs and need no lock.

| Event | Who | Effect on lifecycle |
|---|---|---|
| Watch created / time changed / extended / any office | A | foreground: S11 on the target (edit) or new message; background (`run_for_user`): `create_or_update`/`set_when` (S10 on `LimitReached`), mark the watch as running an immediate check (the checker's `apply_alert` leaves it alone meanwhile), `snapshot_for_watch` **without** the lock (handlers that take `alert_lock` must never wait for the city), then under `alert_lock(watch_id)`: re-read; paused/ended meanwhile → target gets that final text and nothing else happens; else close previous live with `outdated` (`by_user=True`) unless it is the target message, `record_check`, edit target to S12/S13/S13f, `set_live_alert` (alerted = shown = slots), `forget_nav_message(user_id, target)` |
| Book tapped on the live alert | D | under `alert_lock`: `clear_live_alert(reset_alerted=True)` (also clears `alert_interacted_at`), edit to S25; message now belongs to booking; booking session → DEFER |
| Book tapped on a queued (outdated-pending) message | D | under `alert_lock`: `PendingRetireRepository.discard(chat, msg)`, edit to S25 |
| Booking ends without success | D | session deleted; next cycle: live N, alerted ∅ → row 2 (new alert) |
| Booking succeeds | D | under lock: watch ended/booked; `close_live_alert(booked, by_user=True)` (no-op when detached) |
| Stop tapped on alert | B | interaction recorded (group -2); S19 shown in place; "No" re-renders S12 from `rec.snapshot`; "Yes" → under lock ended/stopped + `close_live_alert(stopped, by_user=True)` |
| Pause | B | under lock: paused (`pause_reason="user"`) + `close_live_alert(paused, by_user=True)`; resume → active, next cycle row 2 if slots |
| Deadline / gone | C | `end_watch_by_checker` (7 step 2) |
| Any callback on a live alert / queued message | F tracker | `alert_interacted_at = now` / `not_before = now + 10 min` |

---

## 7. Checker loop (C)

`check_and_notify` keeps the outer loop, stats, analytics events, `MAX_CONSECUTIVE_FAILURES` and health alerts; each
iteration calls `run_check_cycle(bot, today_berlin(), utcnow())`:

0. `process_pending_retires(bot, now)`; every 6 h `services_manager.refresh_catalog()`.
1. `cleanup_expired_bookings(bot)` **every cycle** (one indexed query): `pop_expired_sessions()`; for each with
   `message_id`, `safe_edit_text(user_id, message_id, render_booking_timed_out(lang))`.
2. Ends, for active watches (skipped while that user's booking is active; skipped entirely when the catalog has no
   relations, i.e. failed to load):
   - `effective_window(rec.when, today) is None` → `end_watch_by_checker(deadline)`;
   - `office_id` not in `public_office_ids(service_id)`, or the service has no public office → `end_watch_by_checker(gone)`.
   `end_watch_by_checker` under lock: `set_status(ended, reason)`, `close_live_alert(deadline|gone, by_user=False)`,
   send S17/S17g **silently** and register it as live alert kind `ended`. Paused watches past their deadline end
   without any message.
3. Group remaining active watches by `service_id`. Per group: `office_ids` = union of `watch_office_ids` (public
   offices only, by construction of step 2), query window = `[min start, min(max end, today+364)]`. One
   `fetch_calendar` per service per cycle serves every watch and user on it (stricter than R15's grouping).
4. (no cycle-wide token) `availability` fetches the token right before each call (3.1). A token that cannot be solved
   → that call fails as `other`; failure counters and health alerts as today.
5. Per group: `res = await fetch_calendar(...)`.
   - `ApiError.token` after the built-in retry → counted as a failure.
   - `ApiError.combination` → query each office alone (≤ 10 calls), drop offices that fail with `combination` for this
     cycle (`logger.warning` with ids), merge the successful `availableDays`. Not counted as a failure if at least
     one office succeeded, or if every office was rejected. A watch whose every office was rejected ends with
     `end_watch_by_checker(gone, rejected_offices)` (skipped while that user's booking is active), so it is not
     queried again; watches with some offices left keep running on those.
   - other failure → failure counters, skip group.
   Log `AppointmentLog` when `availableDays` is non-empty (as today).
6. Per watch: `window = effective_window`, `slots = slots_in_scope(calendar, offices, window)`; earliest day `d`;
   times = `calendar_times(calendar, d, offices)`; if None → day-times cache keyed `(service_id, d)`: one
   `fetch_day_times(service, group offices with slots on d, d)` per key per cycle, then
   `times_for_offices(cached, watch offices)`. A failed day-times fetch → the watch's snapshot is `ok=False` this
   cycle (no render without times, no flip-flopping edits). Build `WatchSnapshot`, `record_check`.
7. `await apply_alert(bot, rec.id, snapshot, now, booking_active=is_user_in_queue)`.
8. `process_pending_retires(bot, now)` (old alerts of this cycle's pushes are retired after all pushes).

The token cache is shared with A and D (`captcha_token`), so the checker no longer keeps its own globals.

---

## 8. Booking (D)

8.1 Entry `b1:<wid>:<yyyymmdd>` (fast, no network before returning):
`safe_answer`; `get_for_user(wid, user)`; not open → `safe_answer(toast booking.watch_ended)`, END. Under
`alert_lock(wid)`: pressed message is the live alert → `clear_live_alert(reset_alerted=True)`; else
`PendingRetireRepository.discard(chat, msg)`; edit to S25. Create session (`watch_id`, `office_id = rec.office_id or 0`,
`message_id`, `captcha_token=""`). Return `SELECTING_TIME` (via `stop_others`). Background (`run_for_user`):
`times = fetch_day_times(service, watch_office_ids(rec), day)` (fresh token inside availability, never one stored at
notification time); none → S26g, delete session; else `increment_bookings_started`, S26.

8.2 Entry `book_<date>_<oid>_<sid>` (`book_office_day`, `BOOK_OFFICE_DAY_RE`; buttons that name no watch): same flow with offices `{oid}`; `watch_id` = the user's
open watch for `sid` when its office is any or covers `oid` (so a success ends it as booked), else None.
Day times use the per-office combination fallback (7 step 5), like the checker.

8.3 `b1:t:<oid>:<ts>`: `update_session(timestamp, office_id=oid)`. Saved contact on the user → S27; else ask name
(existing). `b1:chg` → ask name → email → confirm (existing validation). `b1:me`/`b1:ok` → book.

8.4 Booking (background via `run_for_user`, message edited to `booking.booking_in_progress` first):
`token = await get_token(min_ttl=60)`; `book_appointment_complete(...)` in `asyncio.to_thread`; the reserve step
retries once with a new token on a token error (`booking_api`). Success → `set_booking_contact(name, email)`,
`increment_bookings_completed`, if `watch_id`: under lock `set_status(ended, end_reason="booked")` +
`close_live_alert(booked, by_user=True)`; S29 with `booking.watch_finished`. Failure/error → S29 failed (watch stays
active; alerted was reset at tap, so the next cycle sends current slots). Name/email are `html.escape`d in every HTML
message. The success text no longer names "Ausländerbehörde" (any city office sends the email).

8.5 Conversation rules (group 0):
- `allow_reentry=True` so another Book tap restarts. No `conversation_timeout` (needs the job-queue extra); expiry is
  handled by the DB session (next bullet, and C's cleanup).
- Every state handler first loads `BookingSessionRepository.get_active(user_id)`. None (expired, cleaned up, deleted
  by `/stop`) → return `END` **without** `ApplicationHandlerStop`, so group 1 handles the update (typed text becomes a
  search or a typed date; a stale `b1:` callback reaches `booking_orphan_callback`).
- With a live session, every state handler and the entry point stop group 1 by raising
  `ApplicationHandlerStop(next_state)` (decorator `stop_others(fn)`); otherwise a typed name would also run search.
- Text states use `PRIVATE & filters.TEXT & ~filters.COMMAND & ~MENU_FILTER`.
- Fallbacks, all of which delete the session, strip the buttons of `session.message_id`, and **return** `END` without
  stopping, so group 1 then handles the same update:
  `MessageHandler(filters.COMMAND | MENU_FILTER)` and `CallbackQueryHandler(pattern=NAV_RE)`
  (`f1:`, `w1:`, `s1:`, `lang:`, `language`).
- Whenever a new booking message with buttons is sent (ask email, confirm), strip the markup of
  `session.message_id` and store the new id (no stacked Cancel buttons).
- `context.user_data.clear()` is removed everywhere; booking code pops only its own keys (`BOOKING_KEYS`), so
  `lang`, `await_date` and `checking` survive.

8.6 `booking_orphan_callback` (group 1): `b1:t`, `b1:me`, `b1:chg`, `b1:ok`, `b1:x`, `time_*`, `confirm_booking`,
`cancel_booking` outside a conversation (restart, expired) → delete any session, edit to `booking.session_cleared`.

8.7 `end_all_booking_sessions(bot)` (post_init, before the checker starts): `pop_all_sessions()`; for each with
`message_id` → `safe_edit_text(booking.session_cleared, no buttons)`. In-memory conversation state is empty after a
restart, so the DB must match: no deferred watches, no live booking buttons, a typed name after restart is a search
on a clean slate.

---

## 9. Retirement

9.1 Commands: `/setdates`, `/status`, `/myservices` → My watches; `/menu`, `/subscribe` → Find. Not listed in
command menus. Status screen, global date range, inline main menu and every "subscription" text are removed.

9.2 Callbacks without a scheme prefix (`fallback_callback`, B), edit in place:

| Old data | Goes to |
|---|---|
| `main_menu`, `categories` | Find (S3) |
| `cat:<id>`, `catpage:<id>:<p>` | `show_category_page(id, p)` (unknown id → categories) |
| `srv:<sid>`, `addsub:<sid>` | `show_service_step(sid)` |
| `selectoffice:<sid>:<oid>` | `show_when_step(sid, oid)` |
| `myservices`, `unsub:*`, `unsub_all`, `unsub_all_confirm`, `status`, `setdates`, `setdates:*`, `show_stats` | My watches (S18), no data changed |
| anything else | Find (S3) |

9.3 Existing users: `announce_reply_keyboard(bot)` (startup sequence, before the checker): for users with a chosen language
and `ui_version < 1`: `set_chat_commands`; with open watches → send S31 with the reply keyboard, `ui_version = 2`;
without → `ui_version = 1` (they get the keyboard through `presence` on their next update). Users without a language
(reset by migration v1) and with open watches get the language picker (`ui_version = 1`); their first choice runs
onboarding with S31 instead of `start.welcome` (`send_onboarding`: first welcome + open watches), `ui_version = 2`.
Idempotent.
`Forbidden` → `ui_version = 2`, `pause_all_for_user("blocked")`. Pacing by the rate limiter.

9.4 Removed in the integration step only (streams must not remove keys from `common`, `menu`, `buttons`): catalog
areas `menu`, `subscribe`, `myservices`, `setdates`, `status`, `buttons`, `notify` (en+ru, and their `AREAS`
entries); unused `common.*` keys; `SubscriptionRepository` (`delete_user_cascade` deletes `service_subscriptions` rows,
and its tests); `UserRepository.set_date_range`; `src/migrate_db.py` untouched. Update `CLAUDE.md`, `README.md`,
`DOCS/I18N.md` (Russian terms: watch = "поиск", My watches = "Мои поиски"). `tests/test_i18n_keys_used.py` must stay
green before and after.

9.5 `delete_user_data(bot, user_id, lang)` (B): (1) for each open watch, under its lock,
`close_live_alert(stopped, by_user=True)`; (2) the user's active booking session message → `booking.session_cleared`
edit; (3) `UserRepository.delete_user_cascade(user_id)` (pending_retires, watches, booking_sessions,
service_subscriptions, user — children before the user row; no ORM cascade); (4) the caller clears
`context.user_data`. A cycle already running finds nothing on its re-read (6.3 step 1) and sends nothing.

---

## 10. Work split

### 10.0 Foundation (one agent, first; all tests green at the end)

Owns every file in 3.1/3.2, the stubs in 3.3, `tests/fakes.py`, additions to `tests/conftest.py`, the
migration/registration assertions in `tests/test_language.py` (`user_version` 2, routing tests against group 1),
and the dependency change. Catalog areas filled: `keyboard`, `watch` (popular labels `watch.svc_<id>`,
when/where/state/ago/day labels, weekday short names, `office_fallback`, `resumed`), `alert` (all S12–S17g, S30).
Empty registered areas: `find`, `watches`, `settings`, `checker`. Does not change any existing screen behaviour, so
old tests keep passing.

Before the streams start, F splits `tests/test_business_logic.py` by owner (contents moved unchanged):
`TestServicesManager` → `tests/test_services_manager.py` (F); `TestAppointmentChecker`, `TestQueueManager`,
`TestStatsTracking` → `tests/test_queue_and_stats.py` (C); `TestNotificationService`, `TestNotificationFormatting` →
`tests/test_notification_legacy.py` (C, deleted with `notification_service.py`); `TestBookingHelpers` →
`tests/test_booking_helpers.py` (D). Warning carried to C and D: `TestNotificationService` and `TestBookingHelpers`
assert on values they build themselves (they test nothing in `src/`); C deletes them, D replaces them with tests of
the real validation in `booking.py`.

### 10.1 Streams (disjoint ownership; no stream edits `src/i18n/locales/*/__init__.py`, `telegram_bot.py`,
`src/repositories.py`, `src/db_models.py`, `src/database.py`, `src/munich_api_client.py`, `src/services_manager.py`,
`pyproject.toml`, `uv.lock`, or anything under `src/watches/`, `src/ui/`)

| Stream | Files owned | Catalog areas | Tests owned | Consumes from F |
|---|---|---|---|---|
| **A** setup | `src/commands/find.py`, `src/handlers/text_input.py`, `src/services/service_search.py`, `src/services/immediate_check.py` | `find`, `categories` | `test_find_flow.py`, `test_service_search.py`, `test_text_input.py`, `test_immediate_check.py` | `WatchRepository` (create_or_update, find_open, count_open, get_for_user, set_when, set_office, set_live_alert, record_check), `LimitReached`, `when.*`, `availability.snapshot_for_watch/public_office_ids`, `render_alert`, `close_live_alert`, `alert_lock`, `run_for_user`, `show_screen`, `forget_nav_message`, `safe_answer`/`safe_edit_text`/`safe_send`/`safe_strip_markup`, `callbacks`, `labels`, `services_manager` |
| **B** navigation | `src/commands/{start,stop,help,language,watches,settings}.py`, `src/handlers/{menu_keyboard,fallback_callbacks,language_picker}.py`, `src/services/announcement.py`; deletes `src/commands/{menu,subscribe,myservices,setdates,status}.py`, `src/handlers/buttons.py` | `start`, `stop`, `help`, `language`, `commands`, `common` (additions only), `watches`, `settings` | `test_i18n_commands.py` (rewrite; keep the `/stats` refusal test), `test_language.py` (after F), `test_watches_screen.py`, `test_settings.py`, `test_menu_keyboard.py`, `test_fallback_callbacks.py`, `test_announcement.py`, `test_stop.py`, `test_categories.py` (moved `TestCategoryIds`); deletes `test_i18n_buttons.py`, `test_i18n_setdates_status.py` | `WatchRepository` (list_for_user, set_status, count_open, get_for_user), `UserRepository` (contact, ui_version, delete_user_cascade), `BookingSessionRepository.get_active`, `close_live_alert`, `alert_lock`, `render_alert`, `labels`, `keyboard`, `commands_menu`, `show_screen`, `safe_*`, `callbacks`; A's `build_find_screen`, `show_category_page`, `show_service_step`, `show_when_step`, `clear_pending_input` (stub signatures) |
| **C** checker | `src/services/{appointment_checker,alert_lifecycle,queue_manager}.py`, `src/commands/stats.py`; deletes `src/services/notification_service.py` | `checker` | `test_alert_lifecycle.py`, `test_checker_cycle.py`, `test_stats.py`, `test_queue_and_stats.py` (drop date-range tests); deletes `test_i18n_notify.py`, `test_notification_legacy.py` | `decide_alert`, `interaction_state`, `slots.*`, `when.effective_window`, `availability.*`, `render_*`, `close_live_alert`, `alert_lock`, `process_pending_retires`, `queue_retire`, `telegram_safe`, `WatchRepository`, `BookingSessionRepository.pop_expired_sessions`, `services_manager.refresh_catalog` |
| **D** booking | `src/commands/booking.py`, `src/booking_api.py` | `booking` | `test_booking_flow.py`, `test_i18n_booking.py`, `test_booking_watch.py`, `test_booking_helpers.py` (rewrite) | `WatchRepository` (get_for_user, clear_live_alert, set_status), `PendingRetireRepository.discard`, `UserRepository` contact, `BookingSessionRepository` (watch_id, message_id, office_id, get_active, pop_all_sessions), `captcha_token`, `munich_api_client.post_result`, `availability.fetch_day_times/watch_office_ids`, `close_live_alert`, `alert_lock`, `run_for_user`, `labels`, `telegram_safe`, `MENU_FILTER`, `callbacks` (`NAV_RE`); C's `increment_bookings_*` (existing) |

Cross-stream calls only go through signatures fixed by F's stubs; tests of the caller monkeypatch the callee.

### 10.2 Integration (after A–D, one agent)

Section 9.4 removals, full `pytest`, `ruff format`, `ruff check --fix`, docs updates, manual smoke test with a test
bot (onboarding → search → watch → alert → book cancel → stop; restart mid-booking).

---

## 11. Test plan

Shared fixtures (F, `tests/conftest.py` + `tests/fakes.py`):
- `db` — in-memory engine patched into `database._engine` (existing pattern).
- `catalog` — patches `services_manager` caches with the 8 popular services (real ids/names), 1-office and
  7-office relations including two offices named "Bürgerbüro Ruppertstraße", plus non-popular services per category.
- `FakeBot` — records `send_message`, `edit_message_text`, `edit_message_reply_markup`, `delete_message`,
  `set_my_commands`; returns messages with incrementing ids; `fail_next(method, exc)` to raise
  `BadRequest("Message is not modified")`, `BadRequest("Message to edit not found")`, `Forbidden("bot was blocked by the user")`, `RetryAfter`;
  `gate(method) -> asyncio.Event` to hold a call until released (race tests).
- `make_callback_update(data, user_id, message_id)`, `make_text_update(text, user_id, chat_type="private")`,
  `FakeContext(bot, user_data)` whose `application.create_task` runs tasks the test can await (`await ctx.drain()`).
- `today` — patches `when.today_berlin`; `clock` — fixed `utcnow`.
- `calendar(days={"2026-10-29": [102526, 10489]}, times={"2026-10-29": [(ts, 102526), ...]})` — builds API-shaped dicts.
- `fake_availability` / `fake_token` — patch `availability.fetch_calendar`, `fetch_day_times`, `captcha_token.get_token`
  with recorded calls; `fake_api` patches `MunichAPIClient.get_result` to return scripted `ApiResponse`s (error codes)
  (the city API is an external system; these are stubs, assertions target our logic).
- `events` — `track_event` recorder per module (existing pattern).

| Stream | What to test |
|---|---|
| F | `when`: every kind × today before/at/after boundaries, 364-day clip, parse formats (ISO padded/unpadded, D.M.YYYY, D.M.YY, D.M before/after today), invalid (31.02, 2026-13-01, text), ranges with `-`, `–`, `..`, `bis`, `до` between ISO dates, one/three tokens → None, each `DateError`; `migrated_when` for each rule. `slots`: scope filtering, key round-trip, snapshot JSON round-trip, `calendar_times` None when one relevant office lacks appointments, `top_days`, `prune_past`. `decide_alert`: one test per row of 6.2, `{A,B}→{A}→{A,B}` no push, far-horizon addition → EDIT, earlier day → PUSH, E⇒alerted ∅; `interaction_state` at 9:59 / 10:00. Migration v2: future range → between (end clipped), past → asap, NULL/empty → asap, unpadded dates → ISO, reversed → asap, 180-day default range still running → asap, several offices of one service → one any-office watch, rerun → no duplicates, `user_version` 2, fresh DB, columns added once, `ui_version` server default present on both schemas; bad watch row skipped by `list_active`. `WatchRepository`: each method, `LimitReached` on create/reopen (Extend, Search again, any office) at 5 open, upsert per service, conditional `clear_interaction`, `clear_live_alert` clears interaction. `is_user_in_booking` deletes nothing. `delete_user_cascade` leaves no rows in any table. `captcha_token`: cache hit, refresh under min_ttl, single solve under concurrent calls, failure → None; with a fake clock, a token near expiry mid-cycle is re-solved before the next call. `availability`: `captchaInvalid` once → invalidate + one retry ok; `invalidLocationAndServiceCombination` → `ApiError.combination`. `telegram_safe.classify` for each error text; `safe_answer` swallows "query is too old". `callbacks`: every builder ≤ 64 bytes with 10-digit ids, parse round-trip. `keyboard`: both-language matching, unique labels. `show_screen`: edit on callback, strip previous pointer when a different message is pressed, send + strip otherwise, pointer survives `user_data.clear()` (stored in DB). `render_*` en/ru; HTML balanced; escaped names. `close_live_alert` by_user/checker × ok/gone/not_modified/failed/ACTIVE → queued. `process_pending_retires`: due/not due, booking message rescheduled, touched by a tap, RetryAfter then next run edits to Outdated, attempts cap. Interaction tracker marks the matching live alert and touches queued rows. `presence`: keyboard line once for `ui_version < 2` (e.g. unprefixed `myservices` callback, then `/find` sends nothing more), not on `/start`; blocked pauses resumed with `watch.resumed`. `test_i18n_keys_used.py`: every literal `t("area.key"` in `src/**/*.py` exists in en and ru. Wiring: group chat text is ignored; post_init runs the announcement before the checker. Live e2e: `fetch_calendar` for 1063475 with all 7 offices and a real token → `providerIDs` ⊆ offices. i18n parity tests stay green |
| A | Find screen: popular order, missing ids skipped, en/ru labels. Search: synonyms from R5 in en/ru/de, umlaut variants, ≤ 8 results, nothing found, < 2 chars, HTML escaping of the echoed query, unregistered user. Browse: categories, paging, unknown category. Service step: 1 office → when, 7 offices → office step with Any first, 2/row, ≤ 10, disambiguated labels; limit at 5 open for a new service, no limit screen for a service already watched. Presets create/update the watch with the right `WhenSpec`; same service again updates (office and time) with `alert.updated_existing`; typed before/range: valid → new S11 message below the text becomes live alert, prompt stripped; each error; text without digits while awaiting → search results; cancel; menu tap clears pending state; edit of existing watch; `f1:any` on a gone watch. Immediate check: runs in background (handler returns before the fake API is released), slots → S12 registered as live (alerted = shown = slots), none → S13, failure → S13f, change time closes previous alert as outdated, nav pointer forgotten; double tap → one check. Edits happen on the pressed message |
| B | Onboarding after first language pick: picker deleted, S2 with reply keyboard, S3 as nav, `ui_version` 2; `/start` returning user with/without watches; reply-keyboard taps in both languages route correctly and clear pending date input; My watches: lines/states (no slots yet, N free days earliest, paused, ended booked/deadline/gone), checked-ago, no user id/interval/total users, buttons per watch, empty state, 5-limit hides New; pause/resume/stop (from list and from alert, "No" re-renders the alert); Settings: language, forget contact, delete flow incl. ReplyKeyboardRemove, finalized alerts, booking session row gone, `user_data` cleared, a cycle running afterwards sends nothing; `/stop` confirmation; Help; command lists en/ru (7 commands); every unprefixed callback in 9.2 lands on the right screen without crashing; announcement idempotent, levels 1/2, sets chat commands, sends only to users with open watches, handles Forbidden |
| C | `run_check_cycle` with fake availability: one calendar call per service for many watches/users; office/window filtering per watch; non-public office → watch ended `gone` with S17g, never in the query; combination error → per-office fallback still produces snapshots for the other watches; day-times fetched once per `(service, day)` and filtered per watch; day-times failure → no edit; each 6.2 row end-to-end through `apply_alert` with `FakeBot` (push first, old alert retired at cycle end), silent flag on row 5; every error in 6.3; deferral during booking and within 10 min of interaction, then new message after release; race: `FakeBot.send_message` gated while a Book tap is processed → the tapped message is never edited to Outdated and the fresh interaction survives; interaction recorded between snapshot and `apply_alert` → DEFER; deadline end (silent S17 registered as live, final edit; ACTIVE → queued; paused ends silently; Extend later retires S17); token failure → health alert after 5 failures, token errors retried first; expired booking session with `message_id` → S30 edit and row deleted in the same cycle even though the user's watches were processed; `/stats` counts watches |
| D | Book tap: handler returns before the fake API is released; times fetched with a fresh token; live alert detached under the lock, alerted reset, interaction cleared (tap Book, cancel after 1 min, next cycle sends a new alert); tap on a queued message discards its retire; ended watch → toast; no times → S26g and session gone; multi-office time labels; saved contact offered (S27) and used, Change path, contact saved only after success; success ends watch (booked) and calls `close_live_alert`; failure keeps watch active; reserve retried once on `captchaInvalid`; `book_<date>_<oid>_<sid>` buttons work without a watch; menu tap/command/`f1:`/`w1:`/`s1:` callback mid-booking cancels and lets group 1 handle it (registered `Application` test; `f1:date` during ASKING_NAME then the typed date is handled by `text_input`); expired/deleted session + typed text → search results; live session: typed name is not searched; previous booking message buttons stripped; `user_data["lang"]` survives booking end; orphan callbacks; `end_all_booking_sessions` edits and deletes all; HTML escaping of name/email |

---

## 12. Decisions (review round 1)

Accepted and folded into the sections above unless marked **Rejected**.

| Issue | Decision |
|---|---|
| Booking conversation stuck in text states (8.5) | Accepted (a) NAV_RE fallback, (b) DB-session check before stopping. **Rejected** `conversation_timeout`: needs the job-queue extra; (b) plus C's cleanup gives the same result without a scheduler |
| alert_lock races / stale interaction (6.3, 6.4) | Accepted: decision computed inside the lock from the re-read watch; all live-alert writers hold the lock; retires queued and re-checked; conditional interaction clear. `record_interaction` stays lock-free (single conditional UPDATEs) |
| Retire failures / rate limits | Accepted: `pending_retires` table with retry, `AIORateLimiter(max_retries=2)` via the `rate-limiter` extra, pushes before retires in each cycle |
| Sequential update processing | Accepted: `safe_answer` first, slow work in `run_for_user` background tasks with a per-user lock, error handler registered. Chose background tasks over `block=False` so conversation states never enter WAITING |
| `is_user_in_booking` deletes (both critics) | Accepted: read-only; cleanup every cycle |
| Restart leaves booking sessions | Accepted: `end_all_booking_sessions` in post_init before the checker |
| Nav pointer not persisted / wiped | Accepted: `users.nav_message_id`; booking stops calling `user_data.clear()`; stale pointer stripped when another nav message is pressed |
| Book tap does not clear interaction | Accepted: `clear_live_alert` (and `set_live_alert`) always clear `alert_interacted_at` |
| Reply keyboard never reaches some users | Accepted with one column instead of two: `ui_version` levels 0/1/2 and the `presence` handler |
| Flapping slots push repeatedly (rows 3/8) | Accepted: alerted grows by union, reset only when empty |
| S17 untracked; checker end ignores interaction | Accepted: S17 is live kind `ended`; checker-initiated closes queue when in use |
| Forbidden pause indistinguishable | Accepted: `pause_reason`, resumed by `presence` with a one-line note |
| Typed date blocks search; unclear target message | Accepted: no digit → search; typed path sends a new S11 |
| Group chats; post_init ordering | Accepted: `ChatType.PRIVATE`; one startup task awaits the announcement, then runs the checker |
| Catalog keys used in code may vanish | Accepted: `test_i18n_keys_used.py` (F) plus freeze of `common`/`menu`/`buttons` removals until integration |
| Double tap on a preset | Accepted: `checking` marker and live+unchanged guard |
| Migration SQL mishandles unpadded/reversed dates | Accepted: Python data step via `migrated_when`; defensive decoding |
| Default 180-day signup range becomes "between" | Accepted: exactly 180 days → asap. Owner delegated judgement; this matches what those users actually chose (nothing) and avoids deadline messages on dates they never picked |
| Stale office breaks the whole service query | Accepted: query only public offices; non-public watch office → end `gone` with S17g ("Any office" / "New search") rather than silently widening the search; per-office fallback on `combination`; catalog refresh every 6 h |
| Token errors indistinguishable from network errors | Accepted: `ApiResponse.error_codes`, invalidate + retry once, also in reserve |
| One token per cycle expires mid-cycle | Accepted: token fetched right before each call |
| Far-horizon / second-office additions push | Accepted: only `new_top` (new days among the 3 Book days) pushes |
| `apply_alert` signature / deleted watch | Accepted: `apply_alert(bot, watch_id, snapshot, now, booking_active)` |
| `/stop` cascade incomplete | Accepted: 9.5 and `delete_user_cascade` |
| Two open watches for one service | Accepted: one open watch per `(user, service)`; migration merges several offices into one any-office watch (superset of what the user chose; owner delegated judgement) |
| Limit bypass through Extend / Search again | Accepted: enforced in the repository; no limit screen for a service already watched |
| Partial `appointments`, per-office-set cache, failed day-times | Accepted: stricter `calendar_times`, cache per `(service, day)`, failed fetch → snapshot not ok |
| Conversation vs 900 s TTL (second critic) | Accepted the DB-session check; **Rejected** `conversation_timeout` (same reason as the first row) |
| Unowned / shared files | Accepted: `services_manager.py` → F; F splits `test_business_logic.py`; removals frozen until integration; `menu.not_registered` → `start.not_registered` (B) |
| Midnight deadline push; range parsing | Accepted: S17/S17g sent silently; regex token range parsing; `D.M.YY`, `D.M` |
| Pause reason / `ui_version` default / announcement skips | Accepted: `pause_reason`; `server_default "0"`; `ui_version = 2` set by onboarding and language choice; `presence` covers skipped users |
