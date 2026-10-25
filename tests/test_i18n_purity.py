import ast
import sys
from pathlib import Path

from khapa_core import data as D
from khapa_core import i18n

CORE = Path(__file__).parent.parent / "src" / "khapa_core"


def test_eleven_official_languages_are_registered():
    assert len(D.LANGS) == 11 and {x["code"] for x in D.LANGS} == {"en", "af", "zu", "xh", "st", "tn", "nso", "ts", "ss", "ve", "nr"}


def test_only_english_is_complete_and_nothing_else_is_fabricated():
    assert [x["code"] for x in D.LANGS if x["status"] == "source"] == ["en"]
    assert {x["code"] for x in D.LANGS if x["status"] == "draft"} == {"af", "zu"}
    assert set(D.I18N) == {"en", "af", "zu"}                          # no tables for the other eight
    en = D.I18N["en"]
    assert i18n.coverage("zu")[0] < i18n.coverage("af")[0] < len(en)
    assert i18n.coverage("xh") == (0, len(en))
    assert all(k in en for k in D.I18N["af"]) and all(k in en for k in D.I18N["zu"])


def test_untranslated_languages_show_a_visible_notice_and_english_text():
    assert i18n.note_for("en") == ""
    assert "waiting for human review" in i18n.note_for("af") and "waiting for human review" in i18n.note_for("zu")
    for code in ("xh", "st", "tn", "nso", "ts", "ss", "ve", "nr"):
        assert i18n.note_for(code) == "Not translated yet. Showing English."
        assert i18n.translate(code, "marks.title") == "Marks"


def test_parameters_and_missing_keys():
    assert i18n.translate("en", "sync.up", n=3) == "3 waiting to upload"
    assert i18n.translate("zu", "learner.hello", name="Sipho") == "Sawubona, Sipho"
    assert i18n.translate("en", "no.such.key") == "no.such.key"
    assert i18n.translate("en", "sync.up") == "{n} waiting to upload"


def _imports(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            yield from (a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            yield node.module.split(".")[0]


def test_core_is_standard_library_only_and_has_no_flet_import():
    allowed = set(sys.stdlib_module_names) | {"khapa_core"}
    seen = {}
    for f in CORE.glob("*.py"):
        for mod in _imports(f):
            seen.setdefault(mod, []).append(f.name)
    assert not (set(seen) - allowed), {m: seen[m] for m in set(seen) - allowed}
    assert not {"flet", "sqlalchemy", "pydantic"} & set(seen)
