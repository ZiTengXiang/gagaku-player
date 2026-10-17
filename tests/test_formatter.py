from pathlib import Path

import pytest

from gagaku import formatter, score

EXAMPLES = sorted((Path(__file__).resolve().parent.parent / "examples").glob("*.gaku"))
EXTRA = {
    "fractions": "tempo: 60\n[琵琶]\n丄 - ク:1/2 七:1/2 丄:3/2 一:5/2 . | 一:1/2 .:1/2 七 - - |\n"
                 "[笙]\n乙:2 tempo=80 一:2 | 乙 - - - |\n",
    "old_style": "[筝]\n閑三 - 早四 - |\n[筝]\n閑五:2 . . |\n",
}


def signature(sc):
    ev = sorted((e.part, e.beat, e.dur, e.symbol, e.octave) for e in sc.events)
    return ev, sorted(sc.tempo_changes), sc.part_lengths, sc.mode, sc.tempo, sc.title


def sources():
    yield from ((p.name, p.read_text(encoding="utf-8")) for p in EXAMPLES)
    yield from EXTRA.items()


@pytest.mark.parametrize("name, src", list(sources()))
def test_format_keeps_music_and_is_idempotent(name, src):
    once = formatter.format_text(src)
    assert signature(score.parse(once)) == signature(score.parse(src))
    assert formatter.format_text(once) == once


def test_columns_line_up_in_monospace():
    text = formatter.format_text(EXAMPLES[0].read_text(encoding="utf-8"))
    rows = [ln for ln in text.splitlines() if ln.startswith("[")]
    system = rows[:8]
    bar_cols = [[formatter.text_width(r[:i]) for i, ch in enumerate(r) if ch == "|"] for r in system]
    assert all(cols == bar_cols[0] for cols in bar_cols)


@pytest.mark.parametrize("beats", [2, 3, 5, 7])
def test_rebar_by_beats_keeps_music(beats):
    src = EXAMPLES[0].read_text(encoding="utf-8")
    rebarred = f"beats: {beats}\n" + src
    out = formatter.format_text(rebarred)
    assert signature(score.parse(out))[0] == signature(score.parse(src))[0]
    sc = score.parse(out)
    # 譜面の | も指定した拍数ごとに入れ直されている
    for part, lines in sc.bar_lines.items():
        inner = [b for b in lines if 0 < b < sc.part_lengths[part]]
        assert all(b % beats == 0 for b in inner), (part, inner)
    assert formatter.format_text(out) == out


def test_examples_exist():
    assert len(EXAMPLES) >= 3
