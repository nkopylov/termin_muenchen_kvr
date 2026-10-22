# ABOUTME: Guards against code using catalog keys that do not exist (e.g. after an area is removed).
# ABOUTME: Scans every literal t("area.key", ...) call in src/ and checks both languages.

import re
from pathlib import Path

import pytest

from src import i18n

SRC = Path(__file__).resolve().parent.parent / "src"
LITERAL_KEY = re.compile(r"""\bt\(\s*["']([a-z_]+\.[a-z0-9_.]+)["']""")


def used_keys() -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    for path in sorted(SRC.rglob("*.py")):
        for key in LITERAL_KEY.findall(path.read_text(encoding="utf-8")):
            found.setdefault(key, []).append(str(path.relative_to(SRC.parent)))
    return found


def test_scanner_finds_keys():
    keys = used_keys()
    assert "alert.outdated" in keys
    assert "keyboard.upgrade" in keys


@pytest.mark.parametrize("lang", i18n.SUPPORTED_LANGUAGES)
def test_every_literal_key_exists(lang):
    missing = {
        key: files
        for key, files in used_keys().items()
        if key not in i18n.CATALOGS[lang]
    }
    assert missing == {}
