import json
from pathlib import Path

import pytest

from gagaku import plugins

DOCS_PLUGINS = Path(__file__).resolve().parent.parent / "docs" / "plugins"


def fake_fetch(root: Path, tamper: str | None = None):
    """紹介サイトの代わりに docs/plugins/ から返す(tamper のファイルだけ書き換える)。"""
    def fetch(url):
        rel = url.split("/plugins/", 1)[1]
        data = (root / rel).read_bytes()
        if tamper and rel.endswith(tamper):
            data += b"\n# tampered\n"
        return data
    return fetch


def test_bundled_install_enable_and_disable(isolated_home):
    m = plugins.PluginManager()
    assert {"english", "ja-tooltip"} <= {p.id for p in m.bundled_catalog()}
    m.install_bundled("english")
    assert m.installed_info("english").version
    m.set_enabled("english", True)
    assert m.texts()["tb.new"] == "New"
    assert m.palette_label("biwa", "一") == "Ichi（一）"
    assert m.instrument_label("sho") == "Shō"
    m.set_enabled("english", False)
    assert m.texts() == {} and m.palette_label("biwa", "一") is None


def test_enabled_state_is_remembered(isolated_home):
    m = plugins.PluginManager()
    m.install_bundled("english")
    m.set_enabled("english", True)
    m2 = plugins.PluginManager()
    m2.load_enabled()
    assert "english" in m2.active
    m2.uninstall("english")
    assert plugins.PluginManager().installed() == [] and not m2.is_enabled("english")


def test_tooltip_has_reading_japanese_and_pitches(isolated_home):
    m = plugins.PluginManager()
    m.install_bundled("english")
    m.set_enabled("english", True)
    tip = m.palette_tooltip("biwa", "丄", "平調")
    assert "Reading: jō" in tip and "Japanese: 丄" in tip
    assert "Notes: E2, B2, E3, A3" in tip and "arpeggio" in tip
    assert "chord" in m.palette_tooltip("sho", "乞", "平調")
    assert "F#4" in m.palette_tooltip("hichiriki", "舌", "平調")      # 平調のメリ
    assert "Stroke:" in m.palette_tooltip("kakko", "諸来", "平調")


def test_japanese_tooltip_plugin_keeps_ui_and_adds_popups(isolated_home):
    m = plugins.PluginManager()
    m.install_bundled("ja-tooltip")
    m.set_enabled("ja-tooltip", True)
    assert m.texts() == {} and m.palette_label("biwa", "丄") is None   # 画面とボタンは日本語のまま
    tip = m.palette_tooltip("biwa", "丄", "平調")
    assert "読み: じょう" in tip and "4弦・開放" in tip
    assert "構成音: E2, B2, E3, A3" in tip and "A3 を拍頭に着地" in tip
    assert "和音" in m.palette_tooltip("sho", "乞", "平調")
    assert "F#4" in m.palette_tooltip("hichiriki", "舌", "平調")
    assert "打ち方:" in m.palette_tooltip("kakko", "諸来", "平調")
    m.set_enabled("ja-tooltip", False)
    assert m.palette_tooltip("biwa", "丄", "平調") is None


def test_later_enabled_plugin_wins_for_tooltips(isolated_home):
    m = plugins.PluginManager()
    for pid in ("english", "ja-tooltip"):
        m.install_bundled(pid)
    m.set_enabled("english", True)
    m.set_enabled("ja-tooltip", True)
    assert m.palette_tooltip("biwa", "一", "平調").startswith("読み")
    m.set_enabled("ja-tooltip", False)
    assert m.palette_tooltip("biwa", "一", "平調").startswith("Reading")


@pytest.mark.parametrize("query, ids", [("英語", {"english"}), ("english tooltip", {"english"}),
                                        ("柱", {"ja-tooltip"}), ("ポップアップ", {"english", "ja-tooltip"}),
                                        ("synthesizer", set())])
def test_search(query, ids):
    cat = plugins.PluginManager().bundled_catalog()
    assert {p.id for p in cat if p.matches(query)} == ids


def test_online_catalog_and_install_with_hash_check(isolated_home):
    m = plugins.PluginManager()
    url = "https://example.invalid/gagaku-player/plugins/index.json"
    cat = m.online_catalog(url, fetch=fake_fetch(DOCS_PLUGINS))
    info = next(p for p in cat if p.id == "english")
    assert info.source == "online" and info.files["plugin.py"]
    m.install_online(info, fetch=fake_fetch(DOCS_PLUGINS))
    m.set_enabled("english", True)
    assert m.texts()["menu.plugins"] == "Plugins"


def test_tampered_download_is_rejected(isolated_home):
    m = plugins.PluginManager()
    url = "https://example.invalid/gagaku-player/plugins/index.json"
    info = next(p for p in m.online_catalog(url, fetch=fake_fetch(DOCS_PLUGINS)) if p.id == "english")
    with pytest.raises(plugins.PluginError):
        m.install_online(info, fetch=fake_fetch(DOCS_PLUGINS, tamper="plugin.py"))
    assert m.installed() == []


def test_site_catalog_matches_bundled_files():
    """docs/plugins の一覧が同梱プラグインと一致している(tools/build_plugin_index.py の実行忘れ防止)。"""
    index = json.loads((DOCS_PLUGINS / "index.json").read_text(encoding="utf-8"))
    for entry in index["plugins"]:
        for name, digest in entry["files"].items():
            assert plugins.sha256_bytes((plugins.BUNDLED_DIR / entry["id"] / name).read_bytes()) == digest
            assert plugins.sha256_bytes((DOCS_PLUGINS / entry["path"] / name).read_bytes()) == digest


def test_merge_prefers_newer_version():
    a = plugins.PluginInfo(id="x", name="X", version="1.0.0", source="bundled")
    b = plugins.PluginInfo(id="x", name="X", version="1.2.0", source="online")
    assert plugins.PluginManager.merge_catalogs([a], [b])[0].version == "1.2.0"


def test_broken_plugin_does_not_crash(isolated_home):
    folder = plugins.plugins_dir() / "broken"
    folder.mkdir(parents=True)
    (folder / "plugin.json").write_text(json.dumps({"id": "broken", "name": "Broken", "version": "1"}))
    (folder / "plugin.py").write_text("raise RuntimeError('boom')\n")
    m = plugins.PluginManager()
    with pytest.raises(plugins.PluginError):
        m.set_enabled("broken", True)
    assert "broken" not in m.active
