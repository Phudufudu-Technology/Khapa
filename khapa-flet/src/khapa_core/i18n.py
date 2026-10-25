"""Translations. Honest by design: only English is complete.

Afrikaans and isiZulu are partial drafts awaiting human review. The other eight languages have
no tables at all and fall back to English with a visible notice. Nothing here is machine-made.
"""

from __future__ import annotations

import re

from . import data

_PARAM = re.compile(r"\{(\w+)\}")


def lang_info(code: str) -> dict | None:
    return next((x for x in data.LANGS if x["code"] == code), None)


def translate(lang: str, key: str, **params) -> str:
    table = data.I18N.get(lang)
    s = (table or {}).get(key) or data.I18N["en"].get(key) or key
    if params:
        s = _PARAM.sub(lambda m: str(params[m.group(1)]) if m.group(1) in params else m.group(0), s)
    return s


def note_for(lang: str) -> str:
    """The visible 'not complete' notice for a language ('' for English)."""
    info = lang_info(lang)
    if not info or info["status"] == "source":
        return ""
    return data.I18N["en"]["lang.draft"] if info["status"] == "draft" else data.I18N["en"]["lang.pending"]


def coverage(lang: str) -> tuple[int, int]:
    """(translated keys, total keys) for a language."""
    total = len(data.I18N["en"])
    return len(data.I18N.get(lang, {})), total
