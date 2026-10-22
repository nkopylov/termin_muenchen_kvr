# ABOUTME: English message catalog, split into one module per bot area.
# ABOUTME: Every area module must be listed in AREAS to be loaded.

from src.i18n.locales.en import (
    alert,
    booking,
    categories,
    commands,
    common,
    find,
    help,
    keyboard,
    language,
    settings,
    start,
    stop,
    watch,
    watches,
)

AREAS = (
    common,
    commands,
    language,
    start,
    help,
    stop,
    categories,
    booking,
    keyboard,
    watch,
    alert,
    find,
    watches,
    settings,
)
