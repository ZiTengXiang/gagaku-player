import wave
from fractions import Fraction

import numpy as np
import pytest

from gagaku import render, score

SHORT = """mode: 平調
tempo: 90
[笙]   乙 - 一 - |
[篳篥] 四 一 舌 - |
[竜笛] 干 責五 六 - |
[琵琶] ク - 丄 - |
[筝]   閑三 - 早四 - |
[鞨鼓] 正 . 諸来 - |
[鉦鼓] 金 . クレイ . |
[太鼓] . . 図 百 |
"""


def test_render_mix_is_stereo_finite_and_normalised():
    sc = score.parse(SHORT)
    data = render.render(sc, reverb=0.2)
    assert data.ndim == 2 and data.shape[1] == 2
    assert np.all(np.isfinite(data))
    assert 0.5 < np.max(np.abs(data)) <= 0.9
    # 4拍 @90BPM = 約2.7秒 + 余韻
    assert len(data) / render.SR == pytest.approx(4 * 60 / 90 + 4.5, abs=0.1)
    for ev in sc.events:
        assert ev.end_sec > ev.start_sec


def test_ma_mode_inserts_gaps_and_sustains_notes():
    src = "tempo: 60\nbeats: 2\n{ma}[篳篥] 六 - | 四 . | 一 - |\n[笙] 乙 - | - - | 乙 - |\n"
    plain = score.parse(src.format(ma=""))
    ma = score.parse(src.format(ma="ma: 1/2\n"))
    assert ma.ma_beats == Fraction(1, 2)
    render.render(plain, reverb=0)
    render.render(ma, reverb=0)
    get = lambda sc, part: [(e.symbol, round(e.start_sec, 3), round(e.end_sec, 3)) for e in sc.events if e.part == part]
    assert get(plain, "hichiriki") == [("六", 0, 2), ("四", 2, 3), ("一", 4, 6)]
    # 小節の終わりごとに 0.5 拍(=0.5秒)の間。六は間のあいだ延びる。四の後は休みなので延ばさない
    assert get(ma, "hichiriki") == [("六", 0, 2.5), ("四", 2.5, 3.5), ("一", 5.0, 7.0)]
    # 小節線をまたぐ笙の乙は、またいだ間のぶんだけ延びる
    assert get(ma, "sho")[0] == ("乙", 0, 5.0)
    with pytest.raises(score.ScoreError):
        score.parse("ma: -1\n[笙]\n乙\n")


def test_mute_silences_parts():
    sc = score.parse(SHORT)
    keys = {e.part for e in sc.events}
    data = render.render(sc, mute=keys, reverb=0)
    assert np.max(np.abs(data)) == 0


def test_write_wav(tmp_path):
    sc = score.parse("[笙]\n乙\n")
    data = render.render(sc, reverb=0)
    path = tmp_path / "out.wav"
    render.write_wav(path, data)
    with wave.open(str(path)) as w:
        assert (w.getnchannels(), w.getsampwidth(), w.getframerate()) == (2, 2, render.SR)
        assert w.getnframes() == len(data)


def _min_level_near(w, t, sr):
    win = int(0.005 * sr)
    rms = np.sqrt(np.convolve(w ** 2, np.ones(win) / win, mode="same"))
    steady = rms[int((t - 0.5) * sr)]
    return rms[int((t - 0.12) * sr):int((t + 0.12) * sr)].min() / steady


def test_repeated_notes_have_clear_break():
    from gagaku import instruments as I, synth
    f = I.hz("E5")
    same = [synth.PhraseNote(0, 1, f), synth.PhraseNote(1, 2, f)]
    moving = [synth.PhraseNote(0, 1, f), synth.PhraseNote(1, 2, I.hz("F#5"))]
    for phrase in (synth.hichiriki_phrase, synth.ryuteki_phrase):
        assert _min_level_near(phrase(same), 1.0, synth.SR) < 0.01     # 同じ譜字の間はほぼ無音を挟む
        assert _min_level_near(phrase(moving), 1.0, synth.SR) > 0.3    # 違う音へはつないで動く


@pytest.mark.parametrize("beat_sec", [1.0, 0.5])
def test_biwa_sweep_lands_on_the_beat(beat_sec):
    from gagaku import instruments as I
    span = I.BIWA_PICKUP_BEATS * beat_sec
    # 着地型: 直前の時間を弦の数で等分し、最後の弦(目的の音)が拍頭ちょうど(0)に来る
    for n in (2, 3, 4):
        t = I.Biwa.sweep_times(n, beat_sec)
        assert t[-1] == 0
        assert t == pytest.approx([-span * (n - 1 - k) / n for k in range(n)])
    # 曲の頭などで前に時間がないときは縮める
    assert I.Biwa.sweep_times(4, beat_sec, max_pre=0.0) == pytest.approx([0, 0, 0, 0])


def test_biwa_sweep_is_placed_before_the_onset():
    sc = score.parse("tempo: 60\n[琵琶] . . 丄 - |\n")
    from gagaku import instruments as I
    for ev in sc.events:
        ev.start_sec, ev.end_sec, ev.beat_sec = float(ev.beat), float(ev.beat + ev.dur), 1.0
    (start, _), = I.INSTRUMENTS["biwa"].render_part(sc.events, sc.mode)
    assert start == pytest.approx(2.0 - 0.75 * I.BIWA_PICKUP_BEATS)   # 4本: 0.75拍前から弾き始める
    render.render(sc, reverb=0)   # 曲全体のレンダリングでも問題なく置ける


def test_kakko_roll_is_slower_and_follows_tempo():
    from gagaku import instruments as I
    slow = I.Kakko.roll_times("片来", 3.0, 1.0)           # tempo=60, 3拍
    fast = I.Kakko.roll_times("片来", 1.5, 0.5)           # tempo=120, 3拍
    assert slow[1] == pytest.approx(0.22 / I.KAKKO_ROLL_SPEED)
    assert [t / 1.0 for t in slow] == pytest.approx([t / 0.5 for t in fast])   # 拍で見ると同じ
    assert all(b > a for a, b in zip(slow, slow[1:]))
