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


def test_biwa_chord_renders_and_has_no_arpeggio():
    b = I.INSTRUMENTS["biwa"]
    w = b.render("一+ク", 0, 1.0, "平調")
    assert np.all(np.isfinite(w)) and np.max(np.abs(w)) > 0
    names, arp = b.staff_pitches("一+ク", 0, "平調")
    assert arp is False and len(names) == 2
    # 掻撥と違い、両方の弦を同時に鳴らす(先頭から両方の音が出ている)
    sweep = b.render("ク", 0, 1.0, "平調", beat_sec=1.0)
    assert len(w) <= len(sweep)


def test_hichiriki_meri_in_hyojo():
    h = I.INSTRUMENTS["hichiriki"]
    assert h._pitch("舌", 0, "平調") == pytest.approx(I.hz("F#4"))
    assert h._pitch("丄", 0, "平調") == pytest.approx(I.hz("F#5"))
    assert h._pitch("舌", 0, "双調") == pytest.approx(I.hz("G4"))
    assert h._pitch("凢", 0, "平調") == pytest.approx(I.hz("C#5"))     # メリ凢
    assert h._pitch("凢", 0, "双調") == pytest.approx(I.hz("C5"))


def test_hichiriki_meri_ornaments_in_hyojo():
    from gagaku import synth
    h = I.INSTRUMENTS["hichiriki"]
    syms = ["工", "六", "四", "舌"]
    notes = [synth.PhraseNote(i, i + 1.0, h._pitch(s, 0, "平調")) for i, s in enumerate(syms)]
    h._apply_meri(syms, notes, "平調")
    assert [n.dip for n in notes] == [0, 0, 40, 70]
    assert notes[1].sink_in == 45 and notes[2].sink_in == 0       # 工→六 の境目で沈む
    # 曲線: 四の頭はいったん正律より下がり、のちに戻る
    _, f, _, bounds = synth._phrase_curves(notes, start_bend=0, start_time=0.01, glide_time=0.01,
                                           kind="hichiriki")
    a = bounds[2][0]
    seg = f[a:a + synth._n(0.2)] / notes[2].freq
    assert seg.min() < 2 ** (-30 / 1200)
    assert f[a + synth._n(0.5)] / notes[2].freq == pytest.approx(1, abs=0.01)
    # 双調では装飾なし
    notes2 = [synth.PhraseNote(i, i + 1.0, 440.0) for i in range(len(syms))]
    h._apply_meri(syms, notes2, "双調")
    assert all(n.dip == 0 and n.sink_in == 0 for n in notes2)


def test_ryuteki_kan_sits_above_roku():
    r = I.INSTRUMENTS["ryuteki"]
    assert r._pitch("干", 0)[0] > r._pitch("六", 0)[0]


def test_reference_pitch():
    assert I.hz("A4") == pytest.approx(I.A4)
    assert I.hz("A5") == pytest.approx(2 * I.A4)
