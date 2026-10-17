"""Score → ステレオ波形。"""
from __future__ import annotations

import wave

import numpy as np

from . import instruments, synth
from .score import Score, beat_to_sec_fn

SR = synth.SR


def ma_shift_fn(score: Score, conv):
    """「間(ま)あり」のときの時刻のずれ(秒)を返す関数。

    各小節の終わり(最後の小節を除く)に ma_beats 拍ぶんの間を挟む。拍 x にある
    音の頭・終わりは、x 以前にある間の合計だけ後ろへずれる。小節の終わりで鳴って
    いる音(そこで終わる音、またいでいる音)は終わりもずれるので、間のあいだ延びる。
    """
    if not score.ma_beats:
        return lambda x: 0.0
    gaps = []
    for _, b1 in score.bars()[:-1]:
        beat_len = conv(b1 + 1) - conv(b1)   # その位置のテンポでの1拍
        gaps.append((b1, float(score.ma_beats) * beat_len))
    return lambda x: sum(g for b, g in gaps if b <= x)


def render(
    score: Score,
    mute: set[str] | None = None,
    volumes: dict[str, float] | None = None,
    reverb: float = 0.25,
    progress=None,
) -> np.ndarray:
    """(N, 2) float32 配列を返す。event.start_sec / end_sec も埋める。"""
    mute = mute or set()
    volumes = volumes or {}
    conv = beat_to_sec_fn(score)
    shift = ma_shift_fn(score, conv)
    for ev in score.events:
        ev.beat_sec = conv(ev.beat + 1) - conv(ev.beat)  # その位置での1拍の秒数
        ev.start_sec = conv(ev.beat) + shift(ev.beat)
        ev.end_sec = conv(ev.beat + ev.dur) + shift(ev.beat + ev.dur)

    end = max((ev.end_sec for ev in score.events), default=0.0) + 4.5
    out = np.zeros((int(end * SR) + 1, 2))

    def mix(inst, start_sec, w):
        g = inst.gain * volumes.get(inst.key, 1.0)
        lg, rg = np.cos((inst.pan + 1) * np.pi / 4), np.sin((inst.pan + 1) * np.pi / 4)
        p = int(start_sec * SR)
        n = min(len(w), len(out) - p)
        if n > 0:
            out[p : p + n, 0] += w[:n] * g * lg
            out[p : p + n, 1] += w[:n] * g * rg

    cache: dict[tuple, np.ndarray] = {}
    total = len(score.events)
    done = 0
    by_part: dict[str, list] = {}
    for ev in score.events:
        by_part.setdefault(ev.part, []).append(ev)
    for part, evs in by_part.items():
        inst = instruments.INSTRUMENTS[part]
        if part in mute:
            done += len(evs)
            continue
        if inst.render_part is not None:
            # 笙・管: パート全体をフレーズ単位で合成
            for start_sec, w in inst.render_part(evs, score.mode):
                mix(inst, start_sec, w)
            done += len(evs)
            if progress:
                progress(done / max(1, total))
            continue
        for ev in evs:
            done += 1
            if progress and done % 20 == 0:
                progress(done / max(1, total))
            dur = ev.end_sec - ev.start_sec
            key = (ev.part, ev.symbol, ev.octave, round(dur, 3), round(ev.beat_sec, 3), score.mode)
            w = cache.get(key)
            if w is None:
                w = inst.render(ev.symbol, ev.octave, dur, score.mode, beat_sec=ev.beat_sec)
                if len(cache) < 400:
                    cache[key] = w
            mix(inst, ev.start_sec, w)

    if reverb > 0 and len(out) > 0:
        irl, irr = synth.make_ir(), synth.make_ir()
        wet = np.stack(
            [synth.convolve_ola(out[:, 0], irl), synth.convolve_ola(out[:, 1], irr)], axis=1
        )[: len(out)]
        out = out * (1 - reverb * 0.5) + wet * reverb
    peak = np.max(np.abs(out)) if len(out) else 0
    if peak > 0:
        out *= 0.89 / peak
    if progress:
        progress(1.0)
    return out.astype(np.float32)


def write_wav(path, data: np.ndarray):
    pcm = (np.clip(data, -1, 1) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
