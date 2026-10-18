import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load():
    spec = importlib.util.spec_from_file_location("build_mode_tables", ROOT / "tools" / "build_mode_tables.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_mode_pages_match_app_data():
    """docs/<調子>/ の対応表がアプリの音高データと一致している(tools/build_mode_tables.py の実行忘れ防止)。"""
    mod = _load()
    outs = mod.outputs()
    assert len(outs) == 12
    for path, mode, lang in outs:
        assert path.read_text(encoding="utf-8") == mod.page(mode, lang), path


def test_mode_scales():
    mod = _load()
    assert [d[0] for d in mod.degrees("平調")] == ["E", "F#", "G", "A", "B", "C#", "D"]
    assert [d[0] for d in mod.degrees("壱越調")] == ["D", "E", "F#", "G", "A", "B", "C"]
    assert [d[0] for d in mod.degrees("太食調")] == ["E", "F#", "G#", "A", "B", "C#", "D"]
    assert [d[0] for d in mod.degrees("盤渉調")] == ["B", "C#", "D", "E", "F#", "G#", "A"]
