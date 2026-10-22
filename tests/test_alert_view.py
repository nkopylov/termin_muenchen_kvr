# ABOUTME: Tests for rendering alert messages (slots, none yet, failed, empty, final, ended, timed out).
# ABOUTME: Checks texts in both languages, buttons, HTML balance and escaping of city data.

import re
from dataclasses import replace
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from src.i18n import t
from src.repositories import WatchRecord
from src.ui import callbacks as cb
from src.watches.alert_view import (
    FinalState,
    RenderedAlert,
    render_alert,
    render_booking_timed_out,
    render_empty_now,
    render_ended,
    render_final,
    render_outdated,
)
from src.watches.slots import Slot, SlotTime, WatchSnapshot
from src.watches.when import PRESETS

pytestmark = pytest.mark.usefixtures("catalog")

BERLIN = ZoneInfo("Europe/Berlin")
D1, D2, D3, D4, D5 = (
    date(2026, 10, 29),
    date(2026, 11, 26),
    date(2026, 12, 3),
    date(2026, 12, 10),
    date(2026, 12, 17),
)
CHECKED = datetime(2026, 10, 22, 8, 30)  # naive UTC = 10:30 Berlin (CEST)


def ts(day: date, hh: int, mm: int) -> int:
    return int(
        datetime(day.year, day.month, day.day, hh, mm, tzinfo=BERLIN).timestamp()
    )


def rec(**kwargs) -> WatchRecord:
    base = WatchRecord(
        id=42,
        user_id=1,
        service_id=1063475,
        office_id=None,
        when=PRESETS["asap"],
        status="active",
        pause_reason=None,
        end_reason=None,
        ended_at=None,
        last_checked_at=None,
        snapshot=None,
        alerted=frozenset(),
        live=None,
        interacted_at=None,
    )
    return replace(base, **kwargs)


def buttons(markup):
    return [
        [(b.text, b.callback_data or b.url) for b in row]
        for row in markup.inline_keyboard
    ]


def balanced(text: str) -> bool:
    return sorted(re.findall(r"<([a-z]+)[^>]*>", text)) == sorted(
        re.findall(r"</([a-z]+)>", text)
    )


ANY_OFFICE_SNAPSHOT = WatchSnapshot(
    CHECKED,
    True,
    frozenset(
        {
            Slot(D1, 102526),
            Slot(D1, 10313237),
            Slot(D1, 102522),
            Slot(D2, 102522),
            Slot(D3, 54261),
            Slot(D4, 54261),
            Slot(D5, 54261),
        }
    ),
    (
        SlotTime(ts(D1, 9, 0), 102526),
        SlotTime(ts(D1, 9, 5), 102526),
        SlotTime(ts(D1, 9, 10), 102526),
        SlotTime(ts(D1, 9, 55), 10313237),
        SlotTime(ts(D1, 10, 55), 102522),
        SlotTime(ts(D1, 11, 0), 102522),
    ),
)


class TestSlotsAlert:
    def test_any_office_layout(self):
        alert = render_alert(rec(), ANY_OFFICE_SNAPSHOT, "en", initial=False)

        assert isinstance(alert, RenderedAlert)
        assert alert.kind == "slots"
        assert alert.text == (
            "🎉 <b>Free slots</b>\n"
            "Address registration (Anmeldung) · Any office · as soon as possible\n\n"
            "📅 Thu 29.10: 09:00, 09:05, 09:10 (Forstenrieder Allee), "
            "09:55 (Ruppertstraße · 2), 10:55 (Orleansplatz)\n"
            "Also free: 26.11, 03.12 and 2 more days"
        )
        rows = buttons(alert.markup)
        assert rows[:3] == [
            [("📅 Book Thu 29.10", "b1:42:20261029")],
            [("📅 Book Thu 26.11", "b1:42:20261126")],
            [("📅 Book Thu 03.12", "b1:42:20261203")],
        ]
        website, stop = rows[3]
        assert website == (
            "🌐 Website",
            (
                "https://stadt.muenchen.de/buergerservice/terminvereinbarung.html"
                "#/services/1063475/locations/102526"
            ),
        )
        assert stop == ("⏹ Stop watching", cb.watch_stop(42))
        assert len(alert.render_hash) == 40

    def test_single_office_has_no_office_names(self):
        snap = WatchSnapshot(
            CHECKED,
            True,
            frozenset({Slot(D1, 10461)}),
            (SlotTime(ts(D1, 8, 0), 10461), SlotTime(ts(D1, 8, 30), 10461)),
        )
        alert = render_alert(
            rec(service_id=10339028, office_id=10461), snap, "ru", initial=True
        )
        assert "📅 Чт 29.10: 08:00, 08:30\n" not in alert.text
        assert alert.text.endswith("📅 Чт 29.10: 08:00, 08:30")
        assert "ВНЖ, срочно: работа и семья · Servicestelle" in alert.text
        assert buttons(alert.markup)[0] == [
            ("📅 Записаться: Чт 29.10", "b1:42:20261029")
        ]

    def test_two_days_lists_the_other(self):
        snap = WatchSnapshot(
            CHECKED,
            True,
            frozenset({Slot(D1, 1), Slot(D2, 1)}),
            (SlotTime(ts(D1, 8, 0), 1),),
        )
        alert = render_alert(rec(office_id=1), snap, "en", initial=False)
        assert alert.text.endswith("\nAlso free: 26.11")

    def test_three_more_days_without_overflow(self):
        snap = WatchSnapshot(
            CHECKED,
            True,
            frozenset({Slot(D1, 1), Slot(D2, 1), Slot(D3, 1)}),
            (SlotTime(ts(D1, 8, 0), 1),),
        )
        assert render_alert(rec(office_id=1), snap, "ru", initial=False).text.endswith(
            "\nЕщё свободно: 26.11, 03.12"
        )

    def test_overflow_plural_ru(self):
        alert = render_alert(rec(), ANY_OFFICE_SNAPSHOT, "ru", initial=False)
        assert alert.text.endswith("Ещё свободно: 26.11, 03.12 и ещё 2 дня")

    def test_missing_times(self):
        snap = WatchSnapshot(CHECKED, True, frozenset({Slot(D1, 1)}))
        alert = render_alert(rec(office_id=1), snap, "en", initial=False)
        assert "📅 Thu 29.10: times on the website" in alert.text

    def test_updated_existing_prefix(self):
        alert = render_alert(
            rec(), ANY_OFFICE_SNAPSHOT, "en", initial=True, updated_existing=True
        )
        assert alert.text.startswith(t("alert.updated_existing", "en") + "\n\n🎉")

    def test_hash_changes_with_content_only(self):
        a = render_alert(rec(), ANY_OFFICE_SNAPSHOT, "en", initial=False)
        b = render_alert(rec(), ANY_OFFICE_SNAPSHOT, "en", initial=False)
        fewer = replace(
            ANY_OFFICE_SNAPSHOT, earliest_times=ANY_OFFICE_SNAPSHOT.earliest_times[:2]
        )
        c = render_alert(rec(), fewer, "en", initial=False)
        assert a.render_hash == b.render_hash != c.render_hash

    def test_city_names_are_escaped(self, catalog):
        catalog["offices"].append({"id": 7, "name": "A&B <Amt>"})
        snap = WatchSnapshot(
            CHECKED, True, frozenset({Slot(D1, 7)}), (SlotTime(ts(D1, 8, 0), 7),)
        )
        catalog["services"].append({"id": 77, "name": "X <y> & z"})
        catalog["relations"].append({"serviceId": 77, "officeId": 7, "public": True})
        alert = render_alert(
            rec(service_id=77, office_id=None), snap, "en", initial=False
        )
        assert "X &lt;y&gt; &amp; z" in alert.text
        assert "(A&amp;B &lt;Amt&gt;)" in alert.text
        assert balanced(alert.text)


class TestInitialStates:
    @pytest.mark.parametrize("lang", ["en", "ru"])
    def test_none_yet(self, lang):
        alert = render_alert(rec(), WatchSnapshot(CHECKED, True), lang, initial=True)
        assert alert.kind == "empty"
        assert alert.markup is None
        assert alert.text == t("alert.none_yet", lang, summary=_summary(lang))

    @pytest.mark.parametrize("lang", ["en", "ru"])
    def test_check_failed(self, lang):
        alert = render_alert(rec(), WatchSnapshot(CHECKED, False), lang, initial=True)
        assert alert.kind == "empty"
        assert alert.text == t("alert.check_failed", lang, summary=_summary(lang))

    def test_checker_render_of_empty_is_empty_now(self):
        alert = render_alert(rec(), WatchSnapshot(CHECKED, True), "en", initial=False)
        assert alert == render_empty_now(rec(), CHECKED, "en")


def _summary(lang):
    return {
        "en": "Address registration (Anmeldung) · Any office · as soon as possible",
        "ru": "Регистрация по адресу (Anmeldung) · Любое отделение · как можно скорее",
    }[lang]


class TestOtherRenders:
    def test_empty_now_shows_berlin_time(self):
        alert = render_empty_now(rec(), CHECKED, "en")
        assert alert.kind == "empty" and alert.markup is None
        assert "(as of 10:30)" in alert.text
        assert len(alert.render_hash) == 40

    @pytest.mark.parametrize("final", list(FinalState))
    @pytest.mark.parametrize("lang", ["en", "ru"])
    def test_final_states(self, final, lang):
        text = render_final(rec(), final, lang)
        if final is FinalState.OUTDATED:
            assert text == render_outdated(lang) == t("alert.outdated", lang)
        else:
            assert text == t(f"alert.final_{final}", lang, summary=_summary(lang))
        assert balanced(text)

    def test_final_state_values(self):
        assert [f.value for f in FinalState] == [
            "booked",
            "stopped",
            "paused",
            "deadline",
            "gone",
            "outdated",
        ]

    def test_ended_deadline(self):
        alert = render_ended(rec(status="ended", end_reason="deadline"), "en")
        assert alert.kind == "ended"
        assert alert.text == t("alert.deadline", "en", summary=_summary("en"))
        assert buttons(alert.markup) == [
            [("🔁 Extend", "f1:edit:42"), ("🔎 New search", "f1:home")]
        ]

    def test_ended_gone_offers_any_office(self):
        alert = render_ended(rec(status="ended", end_reason="gone", office_id=1), "ru")
        assert alert.text.startswith("⚠️ <b>Поиск завершён</b>")
        assert buttons(alert.markup) == [
            [("🏢 Любое отделение", "f1:any:42"), ("🔎 Новый поиск", "f1:home")]
        ]

    def test_ended_gone_without_public_offices(self):
        alert = render_ended(
            rec(status="ended", end_reason="gone", service_id=5, office_id=1), "en"
        )
        assert buttons(alert.markup) == [[("🔎 New search", "f1:home")]]

    @pytest.mark.parametrize("lang", ["en", "ru"])
    def test_booking_timed_out(self, lang):
        assert render_booking_timed_out(lang) == t("alert.booking_timed_out", lang)
