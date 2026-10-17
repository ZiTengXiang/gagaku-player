"""楽器定義: 譜字 → 音高 / 奏法 の対応と、1音ぶんの波形生成。

笙・竜笛の音高は Wikipedia「笙」「龍笛」の表に基づく。
楽琵琶・楽箏の調弦は tunings.json (暫定値・編集可)。
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from . import synth

MODES = ["壱越調", "平調", "双調", "黄鐘調", "盤渉調", "太食調"]

_TUNINGS = json.loads((Path(__file__).with_name("tunings.json")).read_text(encoding="utf-8"))
A4 = float(_TUNINGS.get("a4_hz", 430.0))

_NOTE_RE = re.compile(r"^([A-G])(#?)(-?\d)$")
_SEMI = {"C": -9, "D": -7, "E": -5, "F": -4, "G": -2, "A": 0, "B": 2}


def hz(note: str, octave_shift: int = 0) -> float:
    m = _NOTE_RE.match(note)
    if not m:
        raise ValueError(f"音名 '{note}' が不正です")
    semis = _SEMI[m.group(1)] + (1 if m.group(2) else 0) + 12 * (int(m.group(3)) - 4)
    return A4 * 2 ** (semis / 12 + octave_shift)


class Instrument:
    key = ""
    display = ""
    aliases: tuple[str, ...] = ()
    pan = 0.0          # -1 左 〜 +1 右
    gain = 1.0
    palette: list[str] = []   # GUIの譜字パレット
    symbol_aliases: dict[str, str] = {}

    def symbols(self) -> set[str]:
        return set(self.palette)

    def canonical(self, sym: str) -> str | None:
        sym = self.symbol_aliases.get(sym, sym)
        return sym if sym in self.symbols() else None

    def render(self, sym: str, octave: int, dur: float, mode: str, beat_sec: float = 1.0) -> np.ndarray:
        raise NotImplementedError

    # パート全体をまとめて合成する楽器(笙・管)はこれを上書きする。
    # events は start_sec / end_sec / beat_sec が埋まった Event のリスト。
    # 戻り値は [(開始秒, 波形), ...]
    render_part = None

    def staff_pitches(self, sym: str, octave: int, mode: str):
        """五線譜に書く音: (音名のリスト, アルペジオか)。打楽器は None。"""
        return None

    def explain_invalid(self, sym: str) -> str | None:
        """canonical() が None を返したときの、より詳しいエラーメッセージ(なければ None)。"""
        return None

    def render_single(self, sym, octave, dur, mode, beat_sec=1.0):
        """render_part を持つ楽器で1音だけ鳴らす(テスト・試聴用)。"""
        ev = SimpleNamespace(symbol=sym, octave=octave, start_sec=0.0, end_sec=dur, beat_sec=beat_sec)
        (_, w), = self.render_part([ev], mode)
        return w


def shift_note(note: str, octaves: int) -> str:
    """'F#4' を octaves オクターブずらす。"""
    m = _NOTE_RE.match(note)
    return f"{m.group(1)}{m.group(2)}{int(m.group(3)) + octaves}"


def split_phrases(events, gap: float = 0.005):
    """休みで区切られた、途切れなく続く音のまとまりに分ける。"""
    phrases, cur = [], []
    for ev in sorted(events, key=lambda e: e.start_sec):
        if cur and ev.start_sec - cur[-1].end_sec > gap:
            phrases.append(cur)
            cur = []
        cur.append(ev)
    if cur:
        phrases.append(cur)
    return phrases


# ------------------------------------------------------------------ 笙

SHO_PIPES = {
    "千": "F#6", "十": "G5", "下": "F#5", "乙": "E5", "工": "C#5", "美": "G#5",
    "一": "B4", "八": "E6", "言": "C#6", "七": "B5", "行": "A5", "上": "D6",
    "凢": "D5", "乞": "A4", "比": "C6",
    # 也・毛 は現行の笙では無音(簧なし)
}
SHO_AITAKE = {
    "乞": "乞 乙 行 七 八 千",
    "一": "一 凢 乙 行 七 千",
    "工": "工 凢 乙 美 行 七",
    "凢": "凢 乙 行 七 八 千",
    "乙": "乙 行 七 上 八 千",
    "下": "下 美 行 七 上 千",
    "十": "下 十 行 七 上 八",
    "美": "美 行 七 比 上 千",
    "行": "行 七 上 八 千",
    "比": "行 七 比 上 八 千",
    # 音取・調子用の特殊合竹
    "乙美": "乙 美 行 七 上 千",
    "乙言": "乙 行 七 言 上 千",
    "凢美": "凢 乙 美 行 七 千",
    "凢言": "凢 乙 行 七 言 千",
}
SHO_JU_SOJO = "十 行 七 上 八"  # 双調の曲での「十」


class Sho(Instrument):
    key = "sho"
    display = "笙"
    aliases = ("笙", "しょう", "sho", "shou", "shō")
    pan = -0.35
    gain = 0.9
    palette = list(SHO_AITAKE) + ["単" + p for p in SHO_PIPES]
    symbol_aliases = {"凡": "凢", "彳": "行"}

    def canonical(self, sym):
        sym = sym.replace("凡", "凢").replace("彳", "行")
        if sym in SHO_AITAKE:
            return sym
        if sym.startswith("単") and sym[1:] in SHO_PIPES:
            return sym
        return None

    def _pipes(self, sym, mode):
        if sym.startswith("単"):
            return [sym[1:]]
        if sym == "十" and mode == "双調":
            return SHO_JU_SOJO.split()
        return SHO_AITAKE[sym].split()

    def staff_pitches(self, sym, octave, mode):
        return [shift_note(SHO_PIPES[p], octave) for p in self._pipes(sym, mode)], False

    def render(self, sym, octave, dur, mode, beat_sec=1.0):
        return self.render_single(sym, octave, dur, mode, beat_sec)

    def render_part(self, events, mode):
        """合竹が替わっても共通の竹は鳴らし続け、入れ替わる竹は手移りで少しずつずらす。"""
        rng = np.random.default_rng(7)
        items = []
        for ph in split_phrases(events):
            T0 = ph[0].start_sec
            end = ph[-1].end_sec - T0
            active: dict[tuple, float] = {}
            segments = []
            prev: set = set()
            breath = []  # (開始, 終了) 各合竹の息の区切り
            for i, ev in enumerate(ph):
                cur = {(p, ev.octave) for p in self._pipes(ev.symbol, mode)}
                t = ev.start_sec - T0
                step = min(1.0, ev.beat_sec)
                for key in prev - cur:   # 離す指: 少し遅れて順に離れる
                    segments.append((key, active.pop(key), t + rng.uniform(0.0, 0.10) * step))
                for key in cur - prev:   # 押さえる指: 順に加わる
                    active[key] = t + (rng.uniform(0.02, 0.14) * step if i else rng.uniform(0, 0.03))
                prev = cur
                breath.append((t, ev.end_sec - T0))
            segments += [(key, st, end) for key, st in active.items()]

            n = synth._n(end + 0.3)
            out = np.zeros(n)
            for (pipe, octv), st, en in segments:
                phrase_start = st < 0.05
                w = synth.sho_pipe(hz(SHO_PIPES[pipe], octv), max(0.05, en - st) + 0.08,
                                   attack=0.22 if phrase_start else 0.07, release=0.08)
                p = synth._n(st) if st > 0 else 0
                out[p:p + len(w)] += w[: n - p]
            # 息: 合竹ごとに少し弱く入って膨らむ(吸う・吐くの替わり目でわずかに沈む)
            env = np.ones(n)
            for (a, b) in breath:
                ia, ib = synth._n(a) if a > 0 else 0, min(n, synth._n(b))
                x = np.linspace(0, 1, max(1, ib - ia))
                env[ia:ib] = 0.72 + 0.28 * synth.smoothstep(x) ** 0.8
            env = synth.moving_average(env, synth._n(0.08))
            items.append((T0, out * env * 0.085))
        return items


# ------------------------------------------------------------------ 竜笛

RYUTEKI = {  # 和(低音域)。責は ' を付けて1オクターブ上
    # 干は指孔順では最低音(E5)だが、実際の曲(越天楽の「六 干」など)では
    # 六(D6)の上の E6 として吹かれるのが普通なので、既定値を E6 にしている。
    # 低い E5 が必要なときは「干,」と書く。
    "干": "E6", "五": "F#5", "丄": "G5", "夕": "A5", "中": "B5", "丅": "C#6", "六": "D6",
}


class Ryuteki(Instrument):
    key = "ryuteki"
    display = "竜笛"
    aliases = ("竜笛", "龍笛", "りゅうてき", "ryuteki", "笛")
    pan = 0.25
    gain = 1.0
    palette = list(RYUTEKI)
    symbol_aliases = {"〒": "干", "上": "丄", "下": "丅", "T": "丅"}

    def canonical(self, sym):
        high = sym.startswith("責")
        base = sym[1:] if high or sym.startswith("和") else sym
        base = self.symbol_aliases.get(base, base)
        if base not in RYUTEKI:
            return None
        return ("責" if high else "") + base

    def _pitch(self, sym, octave):
        if sym.startswith("責"):
            sym, octave = sym[1:], octave + 1
        return hz(RYUTEKI[sym], octave), octave >= 1

    def staff_pitches(self, sym, octave, mode):
        if sym.startswith("責"):
            sym, octave = sym[1:], octave + 1
        return [shift_note(RYUTEKI[sym], octave)], False

    def render(self, sym, octave, dur, mode, beat_sec=1.0):
        return self.render_single(sym, octave, dur, mode, beat_sec)

    def render_part(self, events, mode):
        items = []
        for ph in split_phrases(events):
            T0 = ph[0].start_sec
            notes = []
            for ev in ph:
                f, high = self._pitch(ev.symbol, ev.octave)
                notes.append(synth.PhraseNote(ev.start_sec - T0, ev.end_sec - T0, f, high))
            items.append((T0, synth.ryuteki_phrase(notes)))
        return items


# ------------------------------------------------------------------ 篳篥

HICHIRIKI = {  # Wikipedia「篳篥」の正律。調子ごとの上書きは tunings.json
    "舌": "G4", "五": "A4", "工": "B4", "凢": "C5", "六": "D5",
    "四": "E5", "一": "F#5", "丄": "G5", "丁": "A5",
    "ム": "C#5",  # 現行の古典曲では使わない(右親指孔は常に閉じる)
}


class Hichiriki(Instrument):
    key = "hichiriki"
    display = "篳篥"
    aliases = ("篳篥", "ひちりき", "hichiriki")
    pan = 0.05
    gain = 1.0
    palette = ["舌", "五", "工", "凢", "六", "四", "一", "丄", "丁", "ム"]
    symbol_aliases = {"凡": "凢", "上": "丄", "丅": "丁", "下": "丁"}

    def _note_name(self, sym, mode):
        return _TUNINGS.get("hichiriki", {}).get(mode, {}).get(sym, HICHIRIKI[sym])

    def _pitch(self, sym, octave, mode):
        return hz(self._note_name(sym, mode), octave)

    def staff_pitches(self, sym, octave, mode):
        return [shift_note(self._note_name(sym, mode), octave)], False

    def render(self, sym, octave, dur, mode, beat_sec=1.0):
        return self.render_single(sym, octave, dur, mode, beat_sec)

    def render_part(self, events, mode):
        items = []
        for ph in split_phrases(events):
            T0 = ph[0].start_sec
            notes = [synth.PhraseNote(ev.start_sec - T0, ev.end_sec - T0,
                                      self._pitch(ev.symbol, ev.octave, mode)) for ev in ph]
            items.append((T0, synth.hichiriki_phrase(notes)))
        return items


# ------------------------------------------------------------------ 楽琵琶

BIWA_GRID = [  # [弦][柱]  柱0 = 開放
    ["一", "工", "凢", "フ", "斗"],
    ["乚", "下", "十", "乙", "コ"],
    ["ク", "七", "ヒ", "〻", "之"],
    ["丄", "八", "丨", "ム", "也"],
]
BIWA_POS = {s: (i, j) for i, row in enumerate(BIWA_GRID) for j, s in enumerate(row)}
# 掻撥のリズム: 弦の本数 → 各弦を鳴らす位置。
# 位置は「その音の長さ(次の音か休み . までの時間)」に対する割合。
# ここにない本数(2本)は、拍の前半を弦の数で等分する。
BIWA_SWEEP_RHYTHM = {
    4: [0, 2 / 8, 3 / 8, 4 / 8],   # 8等分した 1・3・4・5 番目
    3: [0, 1 / 4, 2 / 4],          # 4等分した 1・2・3 番目
}


class Biwa(Instrument):
    key = "biwa"
    display = "琵琶"
    aliases = ("琵琶", "楽琵琶", "びわ", "biwa")
    pan = -0.15
    gain = 0.9
    palette = [s for row in BIWA_GRID for s in row] + ["単一", "単乚", "単ク", "単丄"]
    symbol_aliases = {"凡": "凢", "上": "丄", "行": "ク", "ゝ": "〻", "々": "〻", "比": "ヒ"}

    def _chord_parts(self, sym):
        """'一+ク' のような同時に鳴らす組み合わせを、正規化した譜字のリストにする(不正なら None)。"""
        parts = [self.symbol_aliases.get(p, p) for p in sym.replace("＋", "+").split("+")]
        parts = [p[1:] if p.startswith("単") else p for p in parts]
        if len(parts) < 2 or any(p not in BIWA_POS for p in parts):
            return None
        if len({BIWA_POS[p][0] for p in parts}) != len(parts):
            return None   # 同じ弦の音は同時に鳴らせない
        return sorted(parts, key=lambda p: BIWA_POS[p][0])

    def canonical(self, sym):
        if "+" in sym or "＋" in sym:
            parts = self._chord_parts(sym)
            return "+".join(parts) if parts else None
        single = sym.startswith("単")
        base = sym[1:] if single else sym
        base = self.symbol_aliases.get(base, base)
        if base not in BIWA_POS:
            return None
        return ("単" if single else "") + base

    def explain_invalid(self, sym):
        if "+" not in sym and "＋" not in sym:
            return None
        parts = [self.symbol_aliases.get(p, p) for p in sym.replace("＋", "+").split("+")]
        parts = [p[1:] if p.startswith("単") else p for p in parts]
        bad = [p for p in parts if p not in BIWA_POS]
        if bad:
            return f"琵琶の譜字 '{bad[0]}' は不明です"
        strings = [BIWA_POS[p][0] for p in parts]
        dup = next(p for p in parts if strings.count(BIWA_POS[p][0]) > 1)
        return f"'{sym}' は同じ弦({BIWA_POS[dup][0] + 1}弦)の音を含むため、同時には鳴らせません"

    def _note(self, s, f, mode):
        return _TUNINGS["biwa"][mode][s][f]

    @staticmethod
    def sweep_times(n_strings: int, dur: float, beat_sec: float) -> list[float]:
        """掻撥で各弦を鳴らす時刻(音の頭からの秒)。"""
        if n_strings in BIWA_SWEEP_RHYTHM:
            return [dur * p for p in BIWA_SWEEP_RHYTHM[n_strings]]
        span = min(beat_sec, dur)
        return [span * 0.5 * i / n_strings for i in range(n_strings)]

    def staff_pitches(self, sym, octave, mode):
        if "+" in sym:   # 同時に鳴らす和音(アルペジオなし)
            return [shift_note(self._note(*BIWA_POS[p], mode), octave) for p in sym.split("+")], False
        single = sym.startswith("単")
        s, f = BIWA_POS[sym[1:] if single else sym]
        if single:
            return [shift_note(self._note(s, f, mode), octave)], False
        # 掻撥: 低い弦の開放 + 目的の音を、アルペジオの和音として書く
        notes = [self._note(st, f if st == s else 0, mode) for st in range(0, s + 1)]
        return [shift_note(n, octave) for n in notes], len(notes) > 1

    def render(self, sym, octave, dur, mode, beat_sec=1.0):
        ring = max(round(dur * 2) / 2, 3.0)  # 0.5秒刻みに丸めて同じ音をキャッシュで使い回す
        tone = lambda note, strike=1.0: synth.biwa_note(hz(note, octave), ring, strike)
        if "+" in sym:
            # 同時に鳴らす: 撥でまとめて弾く(撥面を打つ音は1回)
            parts = sym.split("+")
            out = sum(tone(self._note(*BIWA_POS[p], mode), 1.0 if i == 0 else 0.2)
                      for i, p in enumerate(parts))
            return out * (0.6 / len(parts) ** 0.5)
        single = sym.startswith("単")
        base = sym[1:] if single else sym
        s, f = BIWA_POS[base]
        if single:
            return tone(self._note(s, f, mode)) * 0.6
        # 掻撥: 低い弦(開放)から目的の弦まで撥で掻き下ろす(第3・4弦なら3〜4本)。
        # 第1・2弦が目的のときは割撥風に隣の弦と2本で弾く。
        # 3・4本は、その音の長さを BIWA_SWEEP_RHYTHM の割合で分けた位置で鳴らす。
        # 2本は拍の前半を等分する(音符が1拍より短いときは、その長さを1拍とみなす)。
        order = list(range(0, s + 1)) if s >= 1 else [0]
        starts = [synth._n(t) if t > 0 else 0 for t in self.sweep_times(len(order), dur, beat_sec)]
        total = starts[-1] + synth._n(ring)
        out = np.zeros(total)
        for i, st in enumerate(order):
            note = self._note(st, f if st == s else 0, mode)
            # 撥が撥面を打つ音は最初の一掻きで強く、以降は弦を払う程度
            w = tone(note, 1.0 if i == 0 else 0.25) * (1.0 if st == s else 0.55)
            out[starts[i] : starts[i] + len(w)] += w
        return out * 0.55


# ------------------------------------------------------------------ 楽箏

KOTO_STRINGS = ["一", "二", "三", "四", "五", "六", "七", "八", "九", "十", "斗", "為", "巾"]


class Koto(Instrument):
    key = "koto"
    display = "筝"
    aliases = ("筝", "箏", "楽箏", "楽筝", "こと", "そう", "koto", "so")
    pan = 0.4
    gain = 0.85
    palette = KOTO_STRINGS + ["閑" + s for s in KOTO_STRINGS[:11]] + ["早" + s for s in KOTO_STRINGS[:11]]
    symbol_aliases = {"〇": "十"}

    def canonical(self, sym):
        if sym and sym[0] in "閑早":
            return sym if sym[1:] in KOTO_STRINGS else None
        return sym if sym in KOTO_STRINGS else None

    def _tone(self, idx, octave, ring, mode):
        note = _TUNINGS["koto"][mode][idx]
        return synth.koto_note(hz(note, octave), ring)

    def _octave_string(self, idx, mode):
        tune = _TUNINGS["koto"][mode]
        target = hz(tune[idx]) * 2
        for j in range(idx + 1, len(tune)):
            if abs(np.log2(hz(tune[j]) / target)) < 0.02:
                return j
        return min(idx + 5, len(tune) - 1)

    def staff_pitches(self, sym, octave, mode):
        tune = _TUNINGS["koto"][mode]
        if sym[0] not in "閑早":
            return [shift_note(tune[KOTO_STRINGS.index(sym)], octave)], False
        # 閑掻・早掻: 隣り合う2弦とオクターブ上の弦を、アルペジオの和音として書く
        idx = KOTO_STRINGS.index(sym[1:])
        strings = sorted({idx, min(idx + 1, 12), self._octave_string(idx, mode)})
        return [shift_note(tune[i], octave) for i in strings], True

    def render(self, sym, octave, dur, mode, beat_sec=1.0):
        ring = max(round(dur * 2) / 2, 3.0)  # 0.5秒刻みに丸めて同じ音をキャッシュで使い回す
        if sym[0] not in "閑早":
            return self._tone(KOTO_STRINGS.index(sym), octave, ring, mode) * 0.6
        idx = KOTO_STRINGS.index(sym[1:])
        nxt = min(idx + 1, 12)
        octs = self._octave_string(idx, mode)
        # 閑掻: 隣接2弦をゆっくり → オクターブ上の弦 / 早掻: 素早く
        if sym[0] == "閑":
            plan = [(0.0, nxt, 0.5), (0.09, idx, 0.6), (min(0.5, dur * 0.5), octs, 0.6)]
        else:
            plan = [(0.0, idx, 0.5), (0.06, nxt, 0.5), (0.12, octs, 0.6)]
        total = synth._n(plan[-1][0]) + synth._n(ring)
        out = np.zeros(total)
        for t0, s, amp in plan:
            w = self._tone(s, octave, ring, mode) * amp
            p = synth._n(t0) if t0 > 0 else 0
            out[p : p + len(w)] += w
        return out


# ------------------------------------------------------------------ 打楽器

KAKKO_ROLL_SPEED = 0.3   # 来の連打の速さ(1.0 = もとの速さ。0.3 なら間隔が約3.3倍)


class Kakko(Instrument):
    key = "kakko"
    display = "鞨鼓"
    aliases = ("鞨鼓", "羯鼓", "かっこ", "kakko")
    pan = 0.0
    gain = 0.7
    palette = ["正", "片来", "諸来", "来"]

    def _hit(self, amp, right=True):
        return synth.kakko_hit(right) * amp

    @staticmethod
    def roll_times(sym: str, dur: float, beat_sec: float) -> list[float]:
        """来の各打の時刻(音の頭からの秒)。打ち始めは間遠く、次第に速くなる。

        間隔は tempo=60(1拍1秒)のときの値を基準に、テンポに比例して変わる。
        """
        scale = beat_sec / KAKKO_ROLL_SPEED
        gap = (0.22 if sym != "諸来" else 0.16) * scale
        min_gap = 0.035 * scale
        times, t = [], 0.0
        while t < dur * 0.92:
            times.append(t)
            t += gap
            gap = max(min_gap, gap * 0.82)
        return times

    def render(self, sym, octave, dur, mode, beat_sec=1.0):
        if sym == "正":
            return self._hit(1.0)
        times = self.roll_times(sym, dur, beat_sec)
        out = np.zeros(synth._n(dur + 0.4))
        for i, t0 in enumerate(times):
            right = (i % 2 == 0) if sym == "諸来" else False
            amp = 0.55 + 0.35 * (i / max(1, len(times) - 1))
            w = self._hit(amp, right)
            p = synth._n(t0) if t0 > 0 else 0
            out[p : p + len(w)] += w[: len(out) - p]
        return out


class Shoko(Instrument):
    key = "shoko"
    display = "鉦鼓"
    aliases = ("鉦鼓", "しょうこ", "shoko", "shōko")
    pan = 0.15
    gain = 0.75
    palette = ["金", "生", "ク", "レイ", "クレイ"]

    def _hit(self, amp, base=1250.0):
        return synth.shoko_hit(base) * amp

    def render(self, sym, octave, dur, mode, beat_sec=1.0):
        if sym == "クレイ":
            # 左(ク)→右(レイ)の2打
            a, b = self._hit(0.75, 1240), self._hit(1.0, 1260)
            gap = synth._n(min(0.18, dur * 0.4))
            out = np.zeros(gap + len(b))
            out[: len(a)] += a
            out[gap:] += b
            return out
        return self._hit(0.75 if sym == "ク" else 1.0)


class Taiko(Instrument):
    key = "taiko"
    display = "太鼓"
    aliases = ("太鼓", "楽太鼓", "釣太鼓", "たいこ", "taiko")
    pan = -0.05
    gain = 1.0
    palette = ["百", "図"]
    symbol_aliases = {"ドウ": "百", "ズン": "図", "圖": "図"}

    def render(self, sym, octave, dur, mode, beat_sec=1.0):
        if sym == "百":   # 強打
            return synth.taiko_hit(strong=True)
        return synth.taiko_hit(strong=False) * 0.35  # 図: 軽い前打


INSTRUMENTS: dict[str, Instrument] = {
    i.key: i for i in (Sho(), Hichiriki(), Ryuteki(), Biwa(), Koto(), Kakko(), Shoko(), Taiko())
}


def resolve_name(name: str) -> str | None:
    n = name.strip().lower()
    for inst in INSTRUMENTS.values():
        if n == inst.key or n in (a.lower() for a in inst.aliases):
            return inst.key
    return None
