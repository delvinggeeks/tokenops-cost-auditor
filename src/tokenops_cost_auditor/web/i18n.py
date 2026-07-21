"""UI strings as translation keys (R-DESIGN-TOKENS-2 §6).

The catalogue is a value sheet, exactly like a mood: components reference
KEYS, locales supply VALUES, and shipping a second language means shipping a
second sheet — zero component changes. English ships alone; Indic locales are
BACKLOG (they arrive as full reviewed sheets, never as partial merges that
leave a screen half-translated).

Missing-key policy: return the key itself. A raw ``kit.foo.bar`` on screen is
visibly broken and greppable; a raised KeyError inside a template is a 500 on
a page that was otherwise fine. The test suite asserts every key used in
templates resolves, so an unresolvable key cannot ship — the fallback exists
for the gap between typing and testing, not as a way of life.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

LOCALES = Path(__file__).parent / "locales"
DEFAULT = "en"


@lru_cache(maxsize=8)
def catalogue(locale: str = DEFAULT) -> dict[str, str]:
    data: dict[str, str] = json.loads((LOCALES / f"{locale}.json").read_text(encoding="utf-8"))
    return data


def t(key: str, /, locale: str = DEFAULT, **kwargs: object) -> str:
    text = catalogue(locale).get(key)
    if text is None:
        return key
    return text.format(**kwargs) if kwargs else text
