"""numpy だけで動くシンセサイザ(加算合成・モード合成ベースの近似)。

管楽器はフレーズ単位で合成する(音と音を途切れさせず、塩梅や手移りでつなぐため)。
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import numpy as np

SR = 44100
_rng = np.random.default_rng(12345)


def _n(sec: float) -> int:
    return max(1, int(round(sec * SR)))


def _t(n: int) -> np.ndarray:
    return np.arange(n) / SR


def smoothstep(x: np.ndarray) -> np.ndarray:
    x = np.clip(x, 0, 1)
    return x * x * (3 - 2 * x)


def moving_average(x: np.ndarray, k: int) -> np.ndarray:
    """長さを保つ移動平均(累積和で計算するので窓が長くても速い)。"""
    if k <= 1:
        return x
    pad = np.concatenate([np.full(k // 2, x[0]), x, np.full(k - k // 2 - 1, x[-1])])
    c = np.cumsum(np.concatenate([[0.0], pad]))
    return (c[k:] - c[:-k]) / k


def env_asr(n: int, attack: float, release: float) -> np.ndarray:
    e = np.ones(n)
    a = min(_n(attack), n // 2)
    r = min(_n(release), n // 2)
    if a > 0:
        e[:a] = np.linspace(0, 1, a) ** 1.5
    if r > 0:
        e[-r:] *= np.linspace(1, 0, r) ** 1.5
    return e


def _spectral_noise(n: int, shape) -> np.ndarray:
    nfft = 1 << max(1, int(np.ceil(np.log2(max(n, 2)))))
    spec = np.fft.rfft(_rng.standard_normal(nfft))
    f = np.fft.rfftfreq(nfft, 1 / SR)
    out = np.fft.irfft(spec * shape(f), nfft)[:n]
    m = np.max(np.abs(out))
    return out / m if m > 0 else out


def bandpass_noise(n: int, center: float, width: float) -> np.ndarray:
    return _spectral_noise(n, lambda f: np.exp(-0.5 * ((f - center) / width) ** 2))


def lowpass_noise(n: int, cutoff: float) -> np.ndarray:
    return _spectral_noise(n, lambda f: 1 / (1 + (f / cutoff) ** 2))


def lowpass(x: np.ndarray, cutoff: float, order: int = 2) -> np.ndarray:
    """周波数領域の緩やかなローパス(高域の耳障りな成分を抑える)。"""
    n = len(x)
    nfft = 1 << int(np.ceil(np.log2(max(n, 2))))
    f = np.fft.rfftfreq(nfft, 1 / SR)
    h = 1 / np.sqrt(1 + (f / cutoff) ** (2 * order))
    return np.fft.irfft(np.fft.rfft(x, nfft) * h, nfft)[:n]


def resonate(x: np.ndarray, peaks, dry: float = 1.0, tail: float = 0.25) -> np.ndarray:
    """胴の共鳴。peaks = [(中心周波数, Q, ゲイン), ...] を周波数領域で掛ける。"""
    n = len(x)
    nfft = 1 << int(np.ceil(np.log2(n + _n(tail))))
    f = np.fft.rfftfreq(nfft, 1 / SR)
    h = np.full(len(f), dry, dtype=complex)
    for fc, q, g in peaks:
        # 2次共振のおおよその伝達関数(位相つき)
        h += g / (1 + 1j * q * (f / fc - fc / np.maximum(f, 1e-3)))
    y = np.fft.irfft(np.fft.rfft(x, nfft) * h, nfft)[:n]
    return y


# ================================================================ 笙

def sho_pipe(freq: float, length: float, attack: float, release: float) -> np.ndarray:
    """笙の竹1本。フリーリードの脈動波形(奇数・偶数倍音とも豊富、高域まで伸びる)。"""
    n = _n(length)
    t = _t(n)
    f0 = freq * 2 ** (_rng.uniform(-4, 4) / 1200)  # 竹ごとのわずかな狂い → うなり
    # 息圧によるごく遅い揺れ(笙はビブラートを掛けない)
    drift = 1 + 0.0007 * np.sin(2 * np.pi * _rng.uniform(0.2, 0.5) * t + _rng.uniform(0, 6))
    phase = 2 * np.pi * f0 * np.cumsum(drift) / SR + _rng.uniform(0, 2 * np.pi)
    out = np.zeros(n)
    duty = 0.32
    for k in range(1, 40):
        fk = f0 * k
        if fk > 11000:
            break
        amp = abs(np.sin(np.pi * k * duty)) / k ** 0.75
        amp *= 1 / (1 + (fk / 5500) ** 2)      # 高域の丸み
        amp *= 1.35 if k == 1 else 1.0          # 共鳴管で基音が支えられる
        out += amp * np.sin(k * phase)
    return out * env_asr(n, attack, release)


# ================================================================ 管楽器(フレーズ合成)

@dataclass
class PhraseNote:
    t0: float          # フレーズ先頭からの秒
    t1: float
    freq: float
    high: bool = False  # 竜笛の責など


def _phrase_curves(notes, *, start_bend, start_time, glide_time, kind):
    """フレーズ全体の 周波数カーブ・音量カーブ を作る。"""
    total = notes[-1].t1
    n = _n(total)
    t = _t(n)
    f = np.empty(n)
    amp = np.ones(n)
    bounds = []
    for nt in notes:
        a, b = _n(nt.t0) if nt.t0 > 0 else 0, min(n, _n(nt.t1))
        f[a:b] = nt.freq
        bounds.append((a, b))
    f[bounds[-1][1]:] = notes[-1].freq
    cents = np.zeros(n)

    # 出だしの塩梅(下からすくい上げる)
    sb = min(_n(start_time), bounds[0][1] - bounds[0][0])
    cents[:sb] += start_bend * (1 - smoothstep(np.linspace(0, 1, sb))) ** 1.3

    for i in range(1, len(notes)):
        prev, cur = notes[i - 1], notes[i]
        a, b = bounds[i]
        span = b - a
        if prev.freq == cur.freq and kind == "hichiriki":
            # 篳篥: 同じ譜字が続くときは、いったん息を止めて吹き直す(切れ目をはっきり)。
            # 前の音の終わりを短く消して無音を挟み、次の音は下からすくい上げて入る。
            pa, pb = bounds[i - 1]
            prev_span = pb - pa
            fo = max(1, min(_n(0.025), prev_span // 6))   # フェードアウト
            gap = max(1, min(_n(0.040), prev_span // 5))  # 無音
            fi = max(1, min(_n(0.045), span // 4))        # 吹き直しの立ち上がり
            s0 = max(0, a - gap - fo)
            amp[s0:a - gap] *= np.linspace(1, 0, a - gap - s0) ** 1.5
            amp[a - gap:a] = 0
            amp[a:a + fi] *= np.linspace(0, 1, fi) ** 1.2
            sb = max(1, min(_n(0.14), span // 2))
            cents[a:a + sb] += -70 * (1 - smoothstep(np.linspace(0, 1, sb))) ** 1.3
            continue
        if prev.freq == cur.freq:
            # 竜笛: 同じ音の連続は指打ちで切る(音量を一瞬落とす)
            d = min(_n(0.06), span // 3)
            dip = np.ones(2 * d)
            dip[:d] = np.linspace(1, 0.25, d)
            dip[d:] = np.linspace(0.25, 1, d)
            s = max(0, a - d)
            amp[s:s + 2 * d] *= dip[: len(amp[s:s + 2 * d])]
            continue
        g = min(_n(glide_time), int(span * 0.6))
        if g < 2:
            continue
        x = np.linspace(0, 1, g)
        interval = 1200 * np.log2(cur.freq / prev.freq)  # 目標から見た前の音のずれ = -interval
        if kind == "hichiriki":
            if interval > 0:
                # 上行: いったん前の音より下げてから押し上げる(塩梅)
                path = -interval - 45 * np.sin(np.pi * np.clip(x / 0.45, 0, 1)) * (x < 0.45)
                path = np.where(x < 0.45, path, -interval * (1 - smoothstep((x - 0.45) / 0.55)))
            else:
                # 下行: なめらかに下りて少し沈み、戻る
                path = -interval * (1 - smoothstep(x)) - 25 * np.sin(np.pi * np.clip((x - 0.5) / 0.5, 0, 1))
        else:
            # 竜笛: 指の動きによる速い移行 + わずかな押し上げ
            path = -interval * (1 - smoothstep(x)) - 12 * np.sin(np.pi * x)
        cents[a:a + g] += path

    # 長い音にのみ、遅れて小さな揺れ
    for (a, b) in bounds:
        span = b - a
        if span > _n(0.7):
            tt = np.arange(span) / SR
            depth = np.clip((tt - 0.45) / 0.6, 0, 1)
            if kind == "hichiriki":
                cents[a:b] += depth * 5 * np.sin(2 * np.pi * 4.6 * tt)
            else:
                cents[a:b] += depth * 7 * np.sin(2 * np.pi * 5.4 * tt)
            # 長い音は吹き込むにつれて膨らむ(雅楽の管の特徴)
            amp[a:b] *= 0.8 + 0.2 * smoothstep(tt / min(1.5, span / SR))
    f = f * 2 ** (cents / 1200)
    return t, f, amp, bounds


# 篳篥の太い管の鼻声: 1.2kHz / 2.7kHz 付近のフォルマント(低次倍音は控えめ)
_HICHI_GRID = np.linspace(0, SR / 2, 2206)
_HICHI_FORMANT = (1 + 1.0 * np.exp(-0.5 * ((_HICHI_GRID - 1200) / 380) ** 2)
                  + 0.7 * np.exp(-0.5 * ((_HICHI_GRID - 2700) / 600) ** 2)) / (1 + (_HICHI_GRID / 5000) ** 2)
# 音の高さが聞き取りやすいよう、基音を最も強くする(2倍音もやや支える)
_HICHI_LOW_BOOST = {1: 1.7, 2: 1.5, 3: 1.2}


def hichiriki_phrase(notes: list[PhraseNote]) -> np.ndarray:
    """篳篥: 大きく、鼻にかかった、ビリつくダブルリード。音と音を塩梅でつなぐ。"""
    t, f, amp, _ = _phrase_curves(notes, start_bend=-120, start_time=0.24,
                                   glide_time=0.20, kind="hichiriki")
    n = len(t)
    phase = 2 * np.pi * np.cumsum(f) / SR
    tone = np.zeros(n)
    fmin = min(nt.freq for nt in notes)
    for k in range(1, 30):
        if k * fmin > 10000:
            break
        w = np.interp(f * k, _HICHI_GRID, _HICHI_FORMANT)
        w = w * _HICHI_LOW_BOOST.get(k, 1.0)
        tone += w / k ** 0.65 * np.sin(k * phase)
    tone /= np.max(np.abs(tone)) + 1e-9
    # 強く吹くほど明るくビリつく
    drive = 0.8 + 1.4 * amp   # 歪ませすぎると基音が埋もれるので控えめに
    tone = np.tanh(tone * drive) / np.tanh(drive)
    breath = bandpass_noise(n, 2200, 1100) * 0.05 + lowpass_noise(n, 600) * 0.02
    env = env_asr(n, 0.035, 0.09)
    out = lowpass((tone + breath) * amp * env, 3800, order=2)
    return out * 0.36


def ryuteki_phrase(notes: list[PhraseNote]) -> np.ndarray:
    """竜笛: 息の多い鋭い横笛。責は倍音と息音が増す。"""
    t, f, amp, bounds = _phrase_curves(notes, start_bend=-60, start_time=0.10,
                                        glide_time=0.05, kind="ryuteki")
    n = len(t)
    phase = 2 * np.pi * np.cumsum(f) / SR
    high = np.zeros(n)
    for nt, (a, b) in zip(notes, bounds):
        high[a:b] = 1.0 if nt.high else 0.0
    high[bounds[-1][1]:] = high[bounds[-1][1] - 1] if bounds[-1][1] > 0 else 0
    # 責の切り替わりをなめらかに
    high = moving_average(high, _n(0.03))
    h2 = 0.28 + 0.30 * high
    h3 = 0.10 + 0.22 * high
    h4 = 0.03 + 0.08 * high
    tone = np.sin(phase) + h2 * np.sin(2 * phase + 0.3) + h3 * np.sin(3 * phase + 1.1) + h4 * np.sin(4 * phase)
    mean_f = float(np.mean([nt.freq for nt in notes]))
    breath = (bandpass_noise(n, mean_f, mean_f * 0.35) * 0.16
              + bandpass_noise(n, 4200, 2200) * (0.05 + 0.05 * high))
    # 出だしの「チフ」(息の当たる音)
    m = min(n, _n(0.05))
    chiff = np.zeros(n)
    chiff[:m] = bandpass_noise(m, 2500, 1200) * np.linspace(1, 0, m) ** 2 * 0.35
    env = env_asr(n, 0.05, 0.08)
    out = (tone * (0.85 + 0.15 * high) + breath) * amp * env + chiff
    return out * 0.27


# ================================================================ 撥弦楽器

def string_tone(
    freq: float,
    length: float,
    *,
    decay: float,
    hf_damp: float,
    brightness: float,
    pos: float,
    inharm: float = 0.0002,
    pitch_drop: float = 15.0,
    drop_time: float = 0.06,
) -> np.ndarray:
    """モード合成による弦の音。高次倍音ほど早く減衰し、撥/爪で強く弾いた直後は音高がわずかに高い。"""
    n = _n(length)
    t = _t(n)
    m = 2 ** (pitch_drop * np.exp(-t / drop_time) / 1200)
    cum = np.cumsum(m) / SR
    out = np.zeros(n)
    for k in range(1, 36):
        fk = k * freq * np.sqrt(1 + inharm * k * k)
        if fk > SR / 2.3:
            break
        a = abs(np.sin(np.pi * k * pos)) / k ** (1.5 - brightness)
        if a < 1e-4:
            continue
        tau = decay / (1 + hf_damp * (k - 1) ** 1.3)
        ph = _rng.uniform(0, 2 * np.pi)
        m_k = min(n, _n(tau * 2.5 * 7))  # 聞こえなくなるまでの区間だけ計算する
        tk, ck = t[:m_k], cum[:m_k]
        # 2つの偏波(わずかに周波数が違う) → 自然なゆらぎと二段減衰
        out[:m_k] += a * (0.7 * np.exp(-tk / tau) * np.sin(2 * np.pi * fk * ck + ph)
                          + 0.3 * np.exp(-tk / (tau * 2.5)) * np.sin(2 * np.pi * fk * 1.0006 * ck + ph))
    out *= env_asr(n, 0.0015, 0.06)
    p = np.max(np.abs(out))
    return out / p if p > 0 else out


BIWA_BODY = [(110, 3.5, 1.4), (230, 4.5, 1.1), (410, 5.0, 0.7), (850, 4.0, 0.35)]
KOTO_BODY = [(150, 3.0, 0.9), (320, 4.0, 0.8), (640, 5.0, 0.5), (1250, 4.0, 0.25)]


@lru_cache(maxsize=256)
def biwa_note(freq: float, length: float, strike: float = 1.0) -> np.ndarray:
    """楽琵琶: 太い絹弦を大きな撥で弾く。撥が撥面を打つ音と胴鳴りが混じる。"""
    s = string_tone(freq, length, decay=1.7, hf_damp=0.22, brightness=0.42, pos=0.09,
                    inharm=0.0003, pitch_drop=22, drop_time=0.05)
    # さわり風のわずかなビリつき(楽琵琶は薩摩琵琶ほど強くない)
    s = np.tanh(s * 1.6) / np.tanh(1.6)
    n = len(s)
    m = min(n, _n(0.05))
    hit = np.zeros(n)
    hit[:m] = (lowpass_noise(m, 700) * 0.9 + bandpass_noise(m, 2500, 1200) * 0.25) * np.exp(-np.arange(m) / (SR * 0.012))
    out = s + hit * 0.55 * strike
    out = resonate(out, BIWA_BODY, dry=0.8)
    return _frozen(out / (np.max(np.abs(out)) + 1e-9))


@lru_cache(maxsize=256)
def koto_note(freq: float, length: float) -> np.ndarray:
    """楽箏: 絹弦を爪で弾く。立ち上がりは明るく、高域はすぐ消え、中低域が長く残る。"""
    s = string_tone(freq, length, decay=2.8, hf_damp=0.45, brightness=0.40, pos=0.14,
                    inharm=0.0001, pitch_drop=10, drop_time=0.05)
    n = len(s)
    m = min(n, _n(0.010))
    click = np.zeros(n)
    click[:m] = bandpass_noise(m, 2800, 1200) * np.linspace(1, 0, m) ** 2
    out = s + click * 0.15
    out = resonate(out, KOTO_BODY, dry=0.85)
    return _frozen(out / (np.max(np.abs(out)) + 1e-9))


def _frozen(x: np.ndarray) -> np.ndarray:
    """キャッシュした波形を誤って書き換えないよう読み取り専用にする。"""
    x.setflags(write=False)
    return x


# ================================================================ 打楽器

def _membrane(f0: float, f_glide: float, decay: float, modes, length: float) -> np.ndarray:
    n = _n(length)
    t = _t(n)
    f = f0 + f_glide * np.exp(-t / 0.03)
    phase = 2 * np.pi * np.cumsum(f) / SR
    out = np.exp(-t / decay) * np.sin(phase)
    for ratio, amp, dk in modes:   # 膜の非整数倍モード
        out += amp * np.exp(-t / (decay * dk)) * np.sin(ratio * phase + _rng.uniform(0, 6))
    return out


def kakko_hit(right: bool = True) -> np.ndarray:
    """鞨鼓: 両面を細い桴で打つ、高く乾いた「カン」。"""
    f0 = 640 if right else 590
    body = _membrane(f0, 60, 0.045, [(1.59, 0.5, 0.7), (2.14, 0.35, 0.5), (2.65, 0.2, 0.4)], 0.35)
    n = len(body)
    m = _n(0.006)
    stick = np.zeros(n)
    stick[:m] = bandpass_noise(m, 4000, 1800) * np.linspace(1, 0, m)
    skin = lowpass_noise(n, 2500) * np.exp(-np.arange(n) / (SR * 0.015)) * 0.4
    out = body + stick * 0.8 + skin
    return out / np.max(np.abs(out))


def taiko_hit(strong: bool = True) -> np.ndarray:
    """楽太鼓: 大きな釣太鼓。革を巻いた桴の柔らかい打撃と、長く響く低音。"""
    if strong:
        body = _membrane(62, 14, 1.6, [(1.52, 0.55, 0.35), (2.3, 0.35, 0.2), (2.9, 0.15, 0.15)], 4.0)
    else:
        body = _membrane(66, 8, 0.9, [(1.52, 0.4, 0.3), (2.3, 0.2, 0.2)], 2.5)
    n = len(body)
    thump = lowpass_noise(n, 280) * np.exp(-np.arange(n) / (SR * 0.04)) * 0.6
    out = body + thump
    out *= np.minimum(1, np.arange(n) / _n(0.004))  # 柔らかい桴の立ち上がり
    return out / np.max(np.abs(out))


def shoko_hit(base: float = 1250.0) -> np.ndarray:
    """鉦鼓: 青銅の皿を角の付いた桴で内側から打つ、明るく鋭い「チン」。"""
    n = _n(1.4)
    t = _t(n)
    ratios = [1.0, 1.71, 2.53, 3.48, 4.62, 5.91, 7.3]
    decays = [0.75, 0.55, 0.38, 0.26, 0.17, 0.11, 0.07]
    out = np.zeros(n)
    for i, (r, d) in enumerate(zip(ratios, decays)):
        fr = base * r * (1 + _rng.uniform(-0.002, 0.002))
        # 同じモードの縮退が分かれて生じるうなり
        out += (1 / (1 + 0.35 * i)) * np.exp(-t / d) * (
            np.sin(2 * np.pi * fr * t) + 0.5 * np.sin(2 * np.pi * fr * 1.003 * t))
    m = _n(0.004)
    out[:m] += bandpass_noise(m, 6500, 2500) * np.linspace(1, 0, m) * 2.0
    return out / np.max(np.abs(out))


# ================================================================ 残響・ミックス

def make_ir(length: float = 2.2, decay: float = 0.55) -> np.ndarray:
    """寺社・ホールを想定した簡易残響インパルス応答。"""
    n = _n(length)
    t = _t(n)
    ir = _rng.standard_normal(n) * np.exp(-t / decay)
    ir = np.convolve(ir, np.ones(8) / 8, mode="same")  # 高域を少し丸める
    ir[: _n(0.012)] = 0  # プリディレイ
    return ir / np.sqrt(np.sum(ir ** 2))


def convolve_ola(x: np.ndarray, ir: np.ndarray, block: int = 1 << 16) -> np.ndarray:
    """長い信号用のオーバーラップ加算畳み込み。"""
    m = len(ir)
    nfft = 1
    while nfft < block + m - 1:
        nfft <<= 1
    H = np.fft.rfft(ir, nfft)
    out = np.zeros(len(x) + m - 1)
    for s in range(0, len(x), block):
        seg = x[s : s + block]
        y = np.fft.irfft(np.fft.rfft(seg, nfft) * H, nfft)[: len(seg) + m - 1]
        out[s : s + len(y)] += y
    return out
