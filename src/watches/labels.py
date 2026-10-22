# ABOUTME: Human-readable labels for watches: service and office names, time, dates, summary, state.
# ABOUTME: Returns plain text (never HTML-escaped); callers escape when inserting into HTML.

from datetime import date, timedelta

from src import services_manager
from src.i18n import t
from src.watches.availability import booking_group, office_choices
from src.watches.when import WhenSpec

POPULAR_SERVICE_IDS: tuple[int, ...] = (
    10339028,
    10339027,
    10502137,
    1063475,
    1063441,
    1063453,
    1071896,
    1064305,
)
MAX_SERVICE_LABEL = 60
OFFICE_PREFIX = "Bürgerbüro "
SEPARATOR = " · "
WITHIN_PRESET_KEYS = {14: "watch.when_2w", 30: "watch.when_1m", 90: "watch.when_3m"}


def service_label(service_id: int, lang: str | None) -> str:
    if service_id in POPULAR_SERVICE_IDS:
        return t(f"watch.svc_{service_id}", lang)
    info = services_manager.get_service_info(service_id)
    if info is None:
        return t("watch.service_fallback", lang, service_id=service_id)
    name = info["name"]
    if len(name) > MAX_SERVICE_LABEL:
        name = name[: MAX_SERVICE_LABEL - 1].rstrip() + "…"
    return name


def _office_names() -> dict[int, str]:
    payload = services_manager.get_full_payload()
    return {
        office["id"]: office.get("name", "") for office in payload.get("offices", [])
    }


def _short_office_name(name: str) -> str:
    return name.removeprefix(OFFICE_PREFIX)


def office_label(
    office_id: int, service_id: int | None = None, lang: str | None = None
) -> str:
    names = _office_names()
    if office_id not in names:
        return t("watch.office_fallback", lang, office_id=office_id)
    label = _short_office_name(names[office_id])
    if service_id is None:
        return label

    shown = min(booking_group(service_id, office_id))
    twins = sorted(
        oid
        for oid in {*office_choices(service_id), shown}
        if oid in names and _short_office_name(names[oid]) == label
    )
    if len(twins) > 1:
        label = f"{label}{SEPARATOR}{twins.index(shown) + 1}"
    return label


def only_office(service_id: int) -> int | None:
    """The office a service is offered at when it has exactly one."""
    choices = office_choices(service_id)
    return choices[0] if len(choices) == 1 else None


def where_text(service_id: int, office_id: int | None, lang: str | None) -> str:
    office_id = office_id if office_id is not None else only_office(service_id)
    if office_id is None:
        return t("watch.where_any", lang)
    return office_label(office_id, service_id, lang)


def where_label(rec, lang: str | None) -> str:
    return where_text(rec.service_id, rec.office_id, lang)


def date_label(d: date) -> str:
    return d.strftime("%d.%m.%Y")


def short_date_label(d: date) -> str:
    return d.strftime("%d.%m")


def day_label(d: date, lang: str | None) -> str:
    return t(
        "watch.day",
        lang,
        weekday=t(f"watch.wd_{d.weekday()}", lang),
        date=short_date_label(d),
    )


def when_label(spec: WhenSpec, lang: str | None) -> str:
    if spec.kind == "asap":
        return t("watch.when_asap", lang)
    if spec.kind == "within":
        key = WITHIN_PRESET_KEYS.get(spec.within_days)
        if key is not None:
            return t(key, lang)
        return t("watch.when_within", lang, count=spec.within_days)
    if spec.kind == "before":
        return t("watch.when_before", lang, date=date_label(spec.date_to))
    return t(
        "watch.when_between",
        lang,
        start=date_label(spec.date_from),
        end=date_label(spec.date_to),
    )


def ago_label(delta: timedelta, lang: str | None) -> str:
    minutes = int(delta.total_seconds() // 60)
    if minutes < 1:
        return t("watch.ago_now", lang)
    if minutes < 60:
        return t("watch.ago_minutes", lang, count=minutes)
    hours = minutes // 60
    if hours < 24:
        return t("watch.ago_hours", lang, count=hours)
    return t("watch.ago_days", lang, count=hours // 24)


def watch_summary(rec, lang: str | None) -> str:
    return SEPARATOR.join(
        (
            service_label(rec.service_id, lang),
            where_label(rec, lang),
            when_label(rec.when, lang),
        )
    )


def watch_state(rec, lang: str | None) -> str:
    if rec.status == "ended":
        return t(f"watch.state_{rec.end_reason or 'stopped'}", lang)
    if rec.status == "paused":
        return t("watch.state_paused", lang)
    if rec.snapshot is None:
        return t("watch.state_not_checked", lang)
    days = rec.snapshot.days()
    if not days:
        return t("watch.state_none", lang)
    return t("watch.state_slots", lang, count=len(days), day=day_label(days[0], lang))
