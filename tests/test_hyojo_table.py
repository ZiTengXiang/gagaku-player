import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_hyojo_pages_match_app_data():
    """docs/hyojo の対応表がアプリの音高データと一致している(tools/build_hyojo_table.py の実行忘れ防止)。"""
    spec = importlib.util.spec_from_file_location("build_hyojo_table", ROOT / "tools" / "build_hyojo_table.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    data = mod.collect()
    for lang in ("ja", "en"):
        path = ROOT / "docs" / mod.TEXT[lang]["path"] / "index.html"
        assert path.read_text(encoding="utf-8") == mod.page(lang, data), path
