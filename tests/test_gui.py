from pathlib import Path

import pytest

tk = pytest.importorskip("tkinter")
EXAMPLES = Path(__file__).resolve().parent.parent / "examples"


@pytest.fixture
def app():
    import os
    import time
    from gagaku import gui
    # 1つのプロセスで Tk を何度も作ると、まれに初期化に失敗するので数回やり直す。
    # 画面のない環境(Linux の CI など)では作れないので飛ばす。
    last = None
    for _ in range(3):
        try:
            a = gui.App(str(EXAMPLES / "wakatake_sojo.gaku"))
            break
        except tk.TclError as e:
            last = e
            time.sleep(0.3)
    else:
        if os.environ.get("DISPLAY") is None and os.name != "nt":
            pytest.skip("画面がない環境")
        raise last
    a.withdraw()
    yield a
    a._dirty = False
    a.destroy()


def test_opening_a_file_redraws_the_visible_view(app):
    for view in app.views:
        app.left_tabs.select(view)
        app.update()
        app._dirty = False
        app.open_file(EXAMPLES / "tsukikage_oshiki.gaku")
        app.update()
        assert view.score is not None and view.score.title == "月影"
        app._dirty = False
        app.open_file(EXAMPLES / "wakatake_sojo.gaku")
        app.update()
        assert view.score.title == "若竹"


def test_score_pane_is_not_collapsed_after_slow_start(app):
    import time
    app._place_sash()               # まだ表示されていない(幅がほぼ0)状態で呼ばれても
    app.deiconify()
    app.geometry("1200x800+20+20")
    deadline = time.time() + 6
    while time.time() < deadline:   # 表示されたあとで境目が置かれる
        app.update()
        if app._body.sashpos(0) >= app.MIN_LEFT:
            break
        time.sleep(0.05)
    assert app._body.sashpos(0) >= app.MIN_LEFT
    app._body.sashpos(0, 0)         # 左端まで寄せても
    app._clamp_sash()
    assert app._body.sashpos(0) >= app.MIN_LEFT   # 譜面の欄は残る


def test_ma_toggle_writes_and_removes_header(app):
    from gagaku import score
    app.ma_len.set("0.5")
    app.ma_on.set(True)
    app._set_ma()
    text = app.text.get("1.0", "end-1c")
    assert "ma: 0.5" in text and score.parse(text).ma_beats == score.Fraction(1, 2)
    app.ma_on.set(False)
    app._set_ma()
    text = app.text.get("1.0", "end-1c")
    assert "ma:" not in text and score.parse(text).ma_beats == 0


def test_english_plugin_switches_ui_and_back(app):
    import tkinter as tk
    app.plugins.install_bundled("english")
    app.plugins.set_enabled("english", True)
    app.update()
    assert app.title().endswith("Gagaku Score Player")
    assert app.left_tabs.tab(0, "text") == "Score text"
    labels = {s: b.cget("text") for k, _, _, bs, _, _ in app._palette if k == "biwa" for b, s in bs}
    assert labels["一"] == "Ichi（一）"
    assert app._mixer_checks["sho"].cget("text") == "Shō"
    # パレットのボタンにポップアップの説明が付く
    assert "Reading" in app.plugins.palette_tooltip("biwa", "一", app._current_mode())
    app.plugins.set_enabled("english", False)
    app.update()
    assert app.title().endswith("雅楽譜プレイヤー")
    labels = {s: b.cget("text") for k, _, _, bs, _, _ in app._palette if k == "biwa" for b, s in bs}
    assert labels["一"] == "一"


def test_plugin_dialog_search_and_install(app):
    from tkinter import messagebox
    app.open_plugin_manager()
    dlg = app._plugin_dialog
    dlg.query.set("英語")
    dlg.update()
    assert dlg.tree.get_children() == ("english",)
    dlg.query.set("no-such-plugin")
    assert dlg.tree.get_children() == ()
    dlg.query.set("english")
    dlg.tree.selection_set("english")
    original = messagebox.askokcancel
    messagebox.askokcancel = lambda *a, **k: True
    try:
        dlg.install()
    finally:
        messagebox.askokcancel = original
    assert "english" in app.plugins.active
    dlg.toggle()                       # 有効 → 無効
    assert "english" not in app.plugins.active
    dlg.destroy()


def test_beats_box_rebars_text(app):
    app.beats_var.set("3")
    app._set_beats()
    from gagaku import score
    sc = score.parse(app.text.get("1.0", "end-1c"))
    assert sc.beats_per_bar == 3
    assert all(b1 - b0 == 3 for b0, b1 in sc.bars())
