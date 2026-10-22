# ABOUTME: Russian message catalog, split into one module per bot area.
# ABOUTME: Every area module must be listed in AREAS to be loaded.

from src.i18n.locales.ru import (
    booking,
    buttons,
    categories,
    commands,
    common,
    help,
    language,
    menu,
    myservices,
    notify,
    setdates,
    start,
    status,
    stop,
    subscribe,
)

AREAS = (
    common,
    commands,
    language,
    start,
    help,
    menu,
    stop,
    subscribe,
    myservices,
    setdates,
    status,
    buttons,
    categories,
    booking,
    notify,
)
