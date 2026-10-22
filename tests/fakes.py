# ABOUTME: Test doubles at the Telegram boundary: a recording bot, real Update objects bound to it,
# ABOUTME: a handler context whose background tasks tests can await, and city API data builders.

import asyncio
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from itertools import count
from typing import Any

from telegram import Chat, Message, Update
from telegram import User as TgUser

DEFAULT_USER_ID = 4242

_update_ids = count(1)
_query_ids = count(1)


@dataclass
class Call:
    method: str
    kwargs: dict[str, Any]

    def __getattr__(self, name: str) -> Any:
        try:
            return self.kwargs[name]
        except KeyError as exc:
            raise AttributeError(name) from exc


class FakeBot:
    """Records Bot API calls; send/edit return real Message objects with incrementing ids."""

    defaults = None
    username = "termin_test_bot"

    def __init__(self, first_message_id: int = 1000) -> None:
        self.calls: list[Call] = []
        self._next_id = count(first_message_id)
        self._failures: dict[str, deque[BaseException]] = defaultdict(deque)
        self._gates: dict[str, asyncio.Event] = {}

    # test controls

    def fail_next(self, method: str, exc: BaseException) -> None:
        """The next call of `method` raises `exc` (queued; one failure per call)."""
        self._failures[method].append(exc)

    def gate(self, method: str) -> asyncio.Event:
        """Calls of `method` wait until the returned event is set."""
        event = asyncio.Event()
        self._gates[method] = event
        return event

    def calls_of(self, method: str) -> list[Call]:
        return [c for c in self.calls if c.method == method]

    @property
    def sent(self) -> list[Call]:
        return self.calls_of("send_message")

    @property
    def edits(self) -> list[Call]:
        return self.calls_of("edit_message_text")

    # Bot API surface

    async def _call(self, method: str, kwargs: dict[str, Any]) -> None:
        if (gate := self._gates.get(method)) is not None:
            await gate.wait()
        if self._failures[method]:
            raise self._failures[method].popleft()
        self.calls.append(Call(method, kwargs))

    def _message(
        self, chat_id: int, message_id: int, text: str | None, markup
    ) -> Message:
        message = Message(
            message_id=message_id,
            date=datetime.now(UTC),
            chat=Chat(id=chat_id, type=Chat.PRIVATE),
            text=text,
            reply_markup=markup,
        )
        message.set_bot(self)
        return message

    async def send_message(
        self, chat_id, text, parse_mode=None, reply_markup=None, **kwargs
    ):
        message_id = next(self._next_id)
        await self._call(
            "send_message",
            {
                "chat_id": chat_id,
                "text": text,
                "parse_mode": parse_mode,
                "reply_markup": reply_markup,
                "message_id": message_id,
                **kwargs,
            },
        )
        return self._message(chat_id, message_id, text, reply_markup)

    async def edit_message_text(
        self,
        text,
        chat_id=None,
        message_id=None,
        parse_mode=None,
        reply_markup=None,
        **kwargs,
    ):
        await self._call(
            "edit_message_text",
            {
                "chat_id": chat_id,
                "message_id": message_id,
                "text": text,
                "parse_mode": parse_mode,
                "reply_markup": reply_markup,
                **kwargs,
            },
        )
        return self._message(chat_id, message_id, text, reply_markup)

    async def edit_message_reply_markup(
        self, chat_id=None, message_id=None, reply_markup=None, **kwargs
    ):
        await self._call(
            "edit_message_reply_markup",
            {
                "chat_id": chat_id,
                "message_id": message_id,
                "reply_markup": reply_markup,
                **kwargs,
            },
        )
        return self._message(chat_id, message_id, None, reply_markup)

    async def delete_message(self, chat_id, message_id, **kwargs):
        await self._call(
            "delete_message", {"chat_id": chat_id, "message_id": message_id, **kwargs}
        )
        return True

    async def answer_callback_query(
        self, callback_query_id, text=None, show_alert=None, **kwargs
    ):
        await self._call(
            "answer_callback_query",
            {
                "callback_query_id": callback_query_id,
                "text": text,
                "show_alert": show_alert,
                **kwargs,
            },
        )
        return True

    async def set_my_commands(self, commands, scope=None, language_code=None, **kwargs):
        await self._call(
            "set_my_commands",
            {
                "commands": list(commands),
                "scope": scope,
                "language_code": language_code,
                **kwargs,
            },
        )
        return True


def _user(user_id: int, language_code: str | None) -> TgUser:
    return TgUser(
        id=user_id,
        first_name="Test",
        is_bot=False,
        username="tester",
        language_code=language_code,
    )


def make_callback_update(
    data: str,
    user_id: int = DEFAULT_USER_ID,
    message_id: int = 1,
    *,
    bot: FakeBot | None = None,
    chat_id: int | None = None,
    chat_type: str = Chat.PRIVATE,
    message_text: str = "",
    language_code: str | None = "en",
) -> Update:
    chat = Chat(id=user_id if chat_id is None else chat_id, type=chat_type)
    message = Message(
        message_id=message_id, date=datetime.now(UTC), chat=chat, text=message_text
    )
    from telegram import CallbackQuery

    query = CallbackQuery(
        id=str(next(_query_ids)),
        from_user=_user(user_id, language_code),
        chat_instance="ci",
        data=data,
        message=message,
    )
    update = Update(update_id=next(_update_ids), callback_query=query)
    _bind(update, bot or FakeBot())
    return update


def make_text_update(
    text: str,
    user_id: int = DEFAULT_USER_ID,
    chat_type: str = Chat.PRIVATE,
    *,
    bot: FakeBot | None = None,
    message_id: int = 1,
    chat_id: int | None = None,
    language_code: str | None = "en",
) -> Update:
    from telegram import MessageEntity

    chat = Chat(id=user_id if chat_id is None else chat_id, type=chat_type)
    entities = None
    if text.startswith("/"):
        command = text.split()[0]
        entities = [MessageEntity(MessageEntity.BOT_COMMAND, 0, len(command))]
    message = Message(
        message_id=message_id,
        date=datetime.now(UTC),
        chat=chat,
        text=text,
        from_user=_user(user_id, language_code),
        entities=entities,
    )
    update = Update(update_id=next(_update_ids), message=message)
    _bind(update, bot or FakeBot())
    return update


def _bind(update: Update, bot: FakeBot) -> None:
    update.set_bot(bot)
    for obj in (update.message, update.callback_query):
        if obj is not None:
            obj.set_bot(bot)
    if update.callback_query is not None and update.callback_query.message is not None:
        update.callback_query.message.set_bot(bot)


class FakeApplication:
    def __init__(self, bot: FakeBot) -> None:
        self.bot = bot
        self.tasks: list[asyncio.Task] = []

    def create_task(self, coroutine, update=None, *, name=None):
        task = asyncio.get_running_loop().create_task(coroutine, name=name)
        self.tasks.append(task)
        return task


class FakeContext:
    """Stands in for CallbackContext: bot, user_data and an application that tracks tasks."""

    def __init__(
        self, bot: FakeBot | None = None, user_data: dict | None = None
    ) -> None:
        self.bot = bot or FakeBot()
        self.user_data: dict = {} if user_data is None else user_data
        self.chat_data: dict = {}
        self.application = FakeApplication(self.bot)
        self.error: BaseException | None = None

    async def drain(self) -> None:
        """Await every background task, including ones started by other tasks."""
        while pending := [t for t in self.application.tasks if not t.done()]:
            await asyncio.gather(*pending, return_exceptions=True)


@dataclass
class Recorder:
    """Async callable that records its calls (stand-in for analytics track_event)."""

    calls: list[tuple[str, dict]] = field(default_factory=list)

    async def __call__(self, event_name, user_id=None, **properties):
        self.calls.append((event_name, {"user_id": user_id, **properties}))


def calendar(
    days: dict[str, list[int]] | None = None,
    times: dict[str, list[tuple[int, int]]] | None = None,
) -> dict:
    """available-calendar response: `days` maps ISO day -> provider office ids,
    `times` maps ISO day -> (timestamp, office_id) appointments."""
    days = days or {}
    times = times or {}
    available = []
    for day in sorted(days):
        by_office: dict[int, list[int]] = defaultdict(list)
        for ts, office_id in times.get(day, []):
            by_office[office_id].append(ts)
        available.append(
            {
                "date": day,
                "providerIDs": ",".join(str(o) for o in days[day]),
                "offices": [
                    {"officeId": str(o), "appointments": sorted(ts_list)}
                    for o, ts_list in by_office.items()
                ],
            }
        )
    return {"availableDays": available}
