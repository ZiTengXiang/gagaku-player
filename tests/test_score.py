from fractions import Fraction

import pytest

from gagaku import score


def notes(sc, part):
    return [(e.symbol, e.beat, e.dur) for e in sc.events if e.part == part]


def test_header_and_basic_tokens():
    sc = score.parse("title: t\nmode: 双調\ntempo: 72\n[篳篥]\n六 - 四:1/2 .:1/2 一:2 |\n")
    assert (sc.title, sc.mode, sc.tempo) == ("t", "双調", 72.0)
    assert notes(sc, "hichiriki") == [
        ("六", Fraction(0), Fraction(2)),
        ("四", Fraction(2), Fraction(1, 2)),
        ("一", Fraction(3), Fraction(2)),
    ]
    assert sc.part_lengths["hichiriki"] == 5


def test_inline_section_header_and_aliases():
    sc = score.parse("[竜笛] 〒 責六 六' |\n[笙] 凡 - |\n")
    assert [e.symbol for e in sc.events if e.part == "ryuteki"] == ["干", "責六", "六"]
    assert [e.octave for e in sc.events if e.part == "ryuteki"] == [0, 0, 1]
    assert [e.symbol for e in sc.events if e.part == "sho"] == ["凢"]


def test_tempo_change_and_seconds():
    sc = score.parse("tempo: 60\n[笙]\n乙 - tempo=120 一 - \n")
    conv = score.beat_to_sec_fn(sc)
    assert conv(Fraction(0)) == 0
    assert conv(Fraction(2)) == pytest.approx(2.0)
    assert conv(Fraction(4)) == pytest.approx(3.0)


def test_bars_follow_bar_lines():
    sc = score.parse("[笙]\n乙 - - | 一 - - - - | 工 |\n")
    assert sc.bars() == [(0, 3), (3, 8), (8, 9)]


@pytest.mark.parametrize("src, line", [
    ("[笙]\n乙 X\n", 2),
    ("[尺八]\n六\n", 1),
    ("[竜笛]\n- 六\n", 2),
    ("mode: 平調x\n[笙]\n乙\n", 1),
])
def test_errors_report_line(src, line):
    with pytest.raises(score.ScoreError) as ei:
        score.parse(src)
    assert ei.value.line == line


def test_extend_with_beat_count():
    sc = score.parse("[篳篥]\n六 -:2 四:1/2 -:1/2 一 -:3/2 |\n")
    assert notes(sc, "hichiriki") == [
        ("六", Fraction(0), Fraction(3)),
        ("四", Fraction(3), Fraction(1)),
        ("一", Fraction(4), Fraction(5, 2)),
    ]
    with pytest.raises(score.ScoreError):
        score.parse("[篳篥]\n-:2 六\n")
    with pytest.raises(score.ScoreError):
        score.parse("[篳篥]\n. -:2\n")


def test_beats_header_rebars_ignoring_bar_lines():
    src = "beats: 3\n[笙]\n乙 - - - | 一 - - - |\n"
    sc = score.parse(src)
    assert sc.beats_per_bar == 3
    assert sc.bars() == [(0, 3), (3, 6), (6, 9)]   # 8拍を3拍ずつ(最後の小節は余り)
    with pytest.raises(score.ScoreError):
        score.parse("拍子: 0\n[笙]\n乙\n")


def test_biwa_simultaneous_strings():
    sc = score.parse("[琵琶]\nク+一:2 丄+乚 |\n")
    assert notes(sc, "biwa") == [("一+ク", Fraction(0), Fraction(2)), ("乚+丄", Fraction(2), Fraction(1))]
    with pytest.raises(score.ScoreError) as ei:
        score.parse("[琵琶]\n下+十\n")          # どちらも2弦
    assert "同じ弦" in str(ei.value)
    with pytest.raises(score.ScoreError):
        score.parse("[琵琶]\n下+X\n")


def test_length_warning():
    sc = score.parse("[笙]\n乙 - - -\n[篳篥]\n六 -\n")
    assert any("揃っていません" in w for w in sc.warnings)
