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


def test_biwa_four_string_sweep_rhythm():
    from gagaku import instruments as I, synth
    b = I.INSTRUMENTS["biwa"]
    base = len(b.render("丄", 0, 4.0, "平調", beat_sec=1e-9))
    n = len(b.render("丄", 0, 4.0, "平調", beat_sec=1.0))
    last_stroke_beats = (n - base) / synth.SR
    assert last_stroke_beats == pytest.approx(float(Fraction(3, 4)), abs=1e-3)
