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


def test_beats_box_rebars_text(app):
    app.beats_var.set("3")
    app._set_beats()
    from gagaku import score
    sc = score.parse(app.text.get("1.0", "end-1c"))
    assert sc.beats_per_bar == 3
    assert all(b1 - b0 == 3 for b0, b1 in sc.bars())
