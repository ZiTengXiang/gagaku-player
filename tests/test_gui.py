from pathlib import Path

import pytest

tk = pytest.importorskip("tkinter")
EXAMPLES = Path(__file__).resolve().parent.parent / "examples"


@pytest.fixture
def app():
    try:
        root = tk.Tk()
        root.destroy()
    except tk.TclError:
        pytest.skip("画面がない環境")
    from gagaku import gui
    a = gui.App(str(EXAMPLES / "wakatake_sojo.gaku"))
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


def test_beats_box_rebars_text(app):
    app.beats_var.set("3")
    app._set_beats()
    from gagaku import score
    sc = score.parse(app.text.get("1.0", "end-1c"))
    assert sc.beats_per_bar == 3
    assert all(b1 - b0 == 3 for b0, b1 in sc.bars())
