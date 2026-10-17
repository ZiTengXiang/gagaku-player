import numpy as np
import pytest

from gagaku import instruments as I


@pytest.mark.parametrize("key", list(I.INSTRUMENTS))
def test_every_palette_symbol_renders(key):
    inst = I.INSTRUMENTS[key]
    for sym in inst.palette:
        assert inst.canonical(sym) is not None, sym
        w = inst.render(inst.canonical(sym), 0, 0.6, "平調")
        assert np.all(np.isfinite(w)) and np.max(np.abs(w)) > 0, sym


@pytest.mark.parametrize("mode", I.MODES)
def test_staff_pitches_parse_in_every_mode(mode):
    from gagaku.staffview import note_step
    for key, inst in I.INSTRUMENTS.items():
        for sym in inst.palette:
            sp = inst.staff_pitches(inst.canonical(sym), 0, mode)
            if key in ("kakko", "shoko", "taiko"):
                assert sp is None
                continue
            names, _ = sp
            assert names and all(note_step(n) for n in names)


def test_hichiriki_meri_in_hyojo():
    h = I.INSTRUMENTS["hichiriki"]
    assert h._pitch("舌", 0, "平調") == pytest.approx(I.hz("F#4"))
    assert h._pitch("丄", 0, "平調") == pytest.approx(I.hz("F#5"))
    assert h._pitch("舌", 0, "双調") == pytest.approx(I.hz("G4"))


def test_ryuteki_kan_sits_above_roku():
    r = I.INSTRUMENTS["ryuteki"]
    assert r._pitch("干", 0)[0] > r._pitch("六", 0)[0]


def test_reference_pitch():
    assert I.hz("A4") == pytest.approx(I.A4)
    assert I.hz("A5") == pytest.approx(2 * I.A4)
