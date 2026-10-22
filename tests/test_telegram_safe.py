# ABOUTME: Tests for Telegram calls that never raise: error classification and each safe_* helper.
# ABOUTME: Uses the recording FakeBot and real telegram.error exception types.

from datetime import timedelta

import pytest
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest, Forbidden, NetworkError, RetryAfter, TimedOut
from telegram.warnings import PTBDeprecationWarning

from src.ui.telegram_safe import (
    EditOutcome,
    classify,
    safe_answer,
    safe_delete,
    safe_edit_text,
    safe_send,
    safe_strip_markup,
)
from tests.fakes import FakeBot, make_callback_update


def retry_after() -> RetryAfter:
    # PTB 22 warns about the future type of retry_after whenever RetryAfter is built
    with pytest.warns(PTBDeprecationWarning, match="retry_after"):
        return RetryAfter(timedelta(seconds=5))


MARKUP = InlineKeyboardMarkup([[InlineKeyboardButton("x", callback_data="f1:home")]])


@pytest.mark.parametrize(
    ("exc", "outcome"),
    [
        (
            BadRequest(
                "Message is not modified: specified new message content and reply markup "
                "are exactly the same"
            ),
            EditOutcome.NOT_MODIFIED,
        ),
        (BadRequest("Message to edit not found"), EditOutcome.GONE),
        (BadRequest("Message can't be edited"), EditOutcome.GONE),
        (BadRequest("Message to delete not found"), EditOutcome.GONE),
        (BadRequest("Message can't be deleted for everyone"), EditOutcome.GONE),
        (Forbidden("Forbidden: bot was blocked by the user"), EditOutcome.FORBIDDEN),
        (retry_after, EditOutcome.FAILED),
        (NetworkError("connection reset"), EditOutcome.FAILED),
        (TimedOut(), EditOutcome.FAILED),
        (BadRequest("Can't parse entities"), EditOutcome.FAILED),
    ],
)
def test_classify(exc, outcome):
    if exc is retry_after:
        exc = retry_after()
    assert classify(exc) is outcome


def test_outcome_values():
    assert [o.value for o in EditOutcome] == [
        "ok",
        "not_modified",
        "gone",
        "forbidden",
        "failed",
    ]


@pytest.mark.asyncio
class TestHelpers:
    async def test_edit_ok(self):
        bot = FakeBot()
        assert await safe_edit_text(bot, 1, 2, "<b>hi</b>", MARKUP) is EditOutcome.OK
        [call] = bot.edits
        assert (call.chat_id, call.message_id, call.text, call.parse_mode) == (
            1,
            2,
            "<b>hi</b>",
            "HTML",
        )
        assert call.reply_markup is MARKUP

    @pytest.mark.parametrize(
        ("exc", "outcome"),
        [
            (BadRequest("Message is not modified"), EditOutcome.NOT_MODIFIED),
            (BadRequest("Message to edit not found"), EditOutcome.GONE),
            (Forbidden("bot was blocked by the user"), EditOutcome.FORBIDDEN),
            (retry_after, EditOutcome.FAILED),
        ],
    )
    async def test_edit_errors_do_not_raise(self, exc, outcome):
        if exc is retry_after:
            exc = retry_after()
        bot = FakeBot()
        bot.fail_next("edit_message_text", exc)
        assert await safe_edit_text(bot, 1, 2, "t") is outcome

    async def test_strip_markup(self):
        bot = FakeBot()
        assert await safe_strip_markup(bot, 1, 2) is EditOutcome.OK
        [call] = bot.calls_of("edit_message_reply_markup")
        assert (call.chat_id, call.message_id, call.reply_markup) == (1, 2, None)
        bot.fail_next(
            "edit_message_reply_markup", BadRequest("Message is not modified")
        )
        assert await safe_strip_markup(bot, 1, 2) is EditOutcome.NOT_MODIFIED

    async def test_delete(self):
        bot = FakeBot()
        assert await safe_delete(bot, 1, 2) is True
        bot.fail_next("delete_message", BadRequest("Message to delete not found"))
        assert await safe_delete(bot, 1, 2) is False

    async def test_send(self):
        bot = FakeBot()
        message, outcome = await safe_send(bot, 1, "hi", MARKUP, silent=True)
        assert outcome is EditOutcome.OK
        assert message.message_id == bot.sent[0].message_id
        assert bot.sent[0].disable_notification is True
        assert bot.sent[0].parse_mode == "HTML"

    async def test_send_forbidden(self):
        bot = FakeBot()
        bot.fail_next("send_message", Forbidden("bot was blocked by the user"))
        assert await safe_send(bot, 1, "hi") == (None, EditOutcome.FORBIDDEN)

    async def test_answer(self):
        bot = FakeBot()
        update = make_callback_update("f1:home", bot=bot)
        assert (
            await safe_answer(update.callback_query, "toast", show_alert=True) is True
        )
        [call] = bot.calls_of("answer_callback_query")
        assert (call.text, call.show_alert) == ("toast", True)

    @pytest.mark.parametrize(
        "message",
        [
            "Query is too old and response timeout expired or query id is invalid",
            "query id is invalid",
        ],
    )
    async def test_answer_swallows_expired_queries(self, message):
        bot = FakeBot()
        bot.fail_next("answer_callback_query", BadRequest(message))
        update = make_callback_update("f1:home", bot=bot)
        assert await safe_answer(update.callback_query) is False

    async def test_answer_without_query(self):
        assert await safe_answer(None) is False
