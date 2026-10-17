"""雅楽譜テキスト(.gaku)のパーサ。

書式の概要(詳細は README.md):

    title: 越天楽(デモ)
    mode: 平調
    tempo: 60            # 1拍あたりのBPM

    [笙]
    乙 - - - | 一 - 工 - |
    [竜笛]
    六 中 夕:2 | 丄' - 五 . |

トークン:
    譜字            1拍
    譜字:2          2拍(1/2, 0.5 なども可)
    -  ー           直前の音を1拍延ばす
    .  ・ 〇 休     1拍休み
    |               小節線(見た目用、無視される)
    tempo=72        この位置からテンポ変更(全パート共通)
    譜字'  譜字,    1オクターブ上 / 下(旋律楽器)
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from fractions import Fraction

from . import instruments

REST_TOKENS = {".", "・", "〇", "○", "休", "_"}
EXTEND_TOKENS = {"-", "ー", "―", "－", "‐"}
BAR_TOKENS = {"|", "｜", "||", "‖"}

TOKEN_RE = re.compile(
    r"^(?P<sym>.+?)(?P<oct>['’,，]*)(?:[:：](?P<dur>[0-9０-９./／]+))?$"
)
TEMPO_RE = re.compile(r"^(?:tempo|テンポ)[=＝:：](?P<bpm>[0-9.]+)$", re.I)
HEADER_RE = re.compile(r"^(?P<key>[A-Za-z_一-龥ぁ-んァ-ヶ]+)\s*[:：]\s*(?P<val>.*)$")
# [楽器名] の後ろに同じ行で音符を続けてもよい(整形後の書式)
SECTION_RE = re.compile(r"^\[(?P<name>[^\]]+)\](?P<rest>.*)$")


def section_header_end(line: str) -> int | None:
    """行が [楽器名] で始まっていれば、その ] の直後の列を返す。"""
    code = line.split("#", 1)[0]
    s = code.lstrip()
    if SECTION_RE.match(s):
        return len(code) - len(s) + s.index("]") + 1
    return None


class ScoreError(Exception):
    def __init__(self, msg: str, line: int, col: int = 0):
        super().__init__(f"{line}行目: {msg}")
        self.line = line
        self.col = col


@dataclass
class Event:
    part: str               # 楽器キー (instruments.INSTRUMENTS のキー)
    beat: Fraction          # 開始拍
    dur: Fraction           # 長さ(拍)
    symbol: str             # 譜字
    octave: int = 0         # オクターブ移動
    line: int = 0           # ソース位置(1始まり行, 0始まり列)
    col: int = 0
    col_end: int = 0
    # render 後に埋まる
    start_sec: float = 0.0
    end_sec: float = 0.0
    beat_sec: float = 1.0   # その位置での1拍の秒数


@dataclass
class Score:
    title: str = ""
    mode: str = "平調"
    tempo: float = 60.0
    events: list[Event] = field(default_factory=list)
    tempo_changes: list[tuple[Fraction, float]] = field(default_factory=list)
    part_lengths: dict[str, Fraction] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    bar_lines: dict[str, list[Fraction]] = field(default_factory=dict)  # パートごとの小節線の拍位置
    tempo_marks: list[tuple[str, Fraction, str]] = field(default_factory=list)  # (パート, 拍, 元の tempo= トークン)

    def bars(self, default_len: int = 4) -> list[tuple[Fraction, Fraction]]:
        """小節の (開始拍, 終了拍) のリスト。小節線が最も多いパートの | を基準にする。"""
        total = max(self.part_lengths.values(), default=Fraction(0))
        lines = max(self.bar_lines.values(), key=len, default=[])
        starts = sorted({Fraction(0), *[b for b in lines if 0 < b < total]})
        if len(starts) <= 1:
            starts = [Fraction(i) for i in range(0, int(total) + 1, default_len) if i < total] or [Fraction(0)]
        ends = starts[1:] + [max(total, starts[-1] + 1)]
        return list(zip(starts, ends))


def _to_halfwidth(s: str) -> str:
    return s.translate(str.maketrans("０１２３４５６７８９／", "0123456789/"))


def _parse_dur(text: str, line: int, col: int) -> Fraction:
    text = _to_halfwidth(text)
    try:
        d = Fraction(text)
    except (ValueError, ZeroDivisionError):
        raise ScoreError(f"長さ '{text}' が読めません", line, col)
    if d <= 0:
        raise ScoreError("長さは正の数にしてください", line, col)
    return d


def _tokenize(line: str):
    """(token, col_start, col_end) を返す。# 以降はコメント。"""
    code = line.split("#", 1)[0]
    for m in re.finditer(r"\S+", code):
        yield m.group(), m.start(), m.end()


def parse(text: str) -> Score:
    score = Score()
    cursors: dict[str, Fraction] = {}
    last_event: dict[str, Event | None] = {}
    current: str | None = None

    for lineno, raw in enumerate(text.splitlines(), start=1):
        stripped = raw.split("#", 1)[0].strip()
        if not stripped:
            continue

        m = SECTION_RE.match(stripped)
        min_col = 0
        if m:
            name = m.group("name").strip()
            key = instruments.resolve_name(name)
            if key is None:
                raise ScoreError(
                    f"楽器名 '{name}' は不明です(使えるもの: "
                    + "、".join(i.display for i in instruments.INSTRUMENTS.values())
                    + ")",
                    lineno,
                )
            current = key
            cursors.setdefault(key, Fraction(0))
            last_event.setdefault(key, None)
            if not m.group("rest").strip():
                continue
            min_col = section_header_end(raw)

        if current is None:
            m = HEADER_RE.match(stripped)
            if not m:
                raise ScoreError("ヘッダ行は 'key: 値' の形、楽譜は [楽器名] の後に書いてください", lineno)
            key, val = m.group("key").lower(), m.group("val").strip()
            if key in ("title", "曲名"):
                score.title = val
            elif key in ("mode", "調子"):
                if val not in instruments.MODES:
                    raise ScoreError(
                        f"調子 '{val}' は未対応です(対応: {'、'.join(instruments.MODES)})", lineno
                    )
                score.mode = val
            elif key in ("tempo", "テンポ"):
                try:
                    score.tempo = float(_to_halfwidth(val))
                except ValueError:
                    raise ScoreError(f"テンポ '{val}' が数値ではありません", lineno)
            else:
                score.warnings.append(f"{lineno}行目: 未知のヘッダ '{key}' は無視しました")
            continue

        inst = instruments.INSTRUMENTS[current]
        for tok, c0, c1 in _tokenize(raw):
            if c0 < min_col:
                continue
            if tok in BAR_TOKENS:
                lines = score.bar_lines.setdefault(current, [])
                if not lines or lines[-1] != cursors[current]:
                    lines.append(cursors[current])
                continue
            if tok in REST_TOKENS:
                cursors[current] += 1
                last_event[current] = None
                continue
            if tok in EXTEND_TOKENS:
                ev = last_event[current]
                if ev is None:
                    raise ScoreError("'-' の前に延ばす音がありません", lineno, c0)
                ev.dur += 1
                cursors[current] += 1
                continue
            tm = TEMPO_RE.match(tok)
            if tm:
                score.tempo_changes.append((cursors[current], float(tm.group("bpm"))))
                score.tempo_marks.append((current, cursors[current], tok))
                continue
            # 休符に長さ指定  例: .:2
            rm = re.match(r"^(?P<r>[.・〇○休_])[:：](?P<dur>.+)$", tok)
            if rm:
                cursors[current] += _parse_dur(rm.group("dur"), lineno, c0)
                last_event[current] = None
                continue

            m = TOKEN_RE.match(tok)
            if not m:
                raise ScoreError(f"'{tok}' が読めません", lineno, c0)
            sym = m.group("sym")
            canon = inst.canonical(sym)
            if canon is None:
                raise ScoreError(
                    f"{inst.display}の譜字 '{sym}' は不明です", lineno, c0
                )
            octs = m.group("oct") or ""
            octave = sum(1 if ch in "'’" else -1 for ch in octs)
            dur = _parse_dur(m.group("dur"), lineno, c0) if m.group("dur") else Fraction(1)
            ev = Event(current, cursors[current], dur, canon, octave, lineno, c0, c1)
            score.events.append(ev)
            last_event[current] = ev
            cursors[current] += dur

    score.part_lengths = dict(cursors)
    lengths = {k: v for k, v in cursors.items() if v > 0}
    if len(set(lengths.values())) > 1:
        detail = "、".join(
            f"{instruments.INSTRUMENTS[k].display}={float(v):g}拍" for k, v in lengths.items()
        )
        score.warnings.append(f"パートの長さが揃っていません: {detail}")
    score.tempo_changes.sort(key=lambda x: x[0])
    return score


def beat_to_sec_fn(score: Score):
    """拍→秒の変換関数(テンポ変更を考慮)。"""
    points = [(Fraction(0), score.tempo)] + [
        (b, t) for b, t in score.tempo_changes if b > 0
    ]
    if score.tempo_changes and score.tempo_changes[0][0] == 0:
        points[0] = (Fraction(0), score.tempo_changes[0][1])
    # 各区間の開始秒を前計算
    starts = []
    sec = 0.0
    for i, (b, bpm) in enumerate(points):
        starts.append(sec)
        if i + 1 < len(points):
            sec += float(points[i + 1][0] - b) * 60.0 / bpm

    def conv(beat: Fraction) -> float:
        idx = 0
        for i, (b, _) in enumerate(points):
            if beat >= b:
                idx = i
        b, bpm = points[idx]
        return starts[idx] + float(beat - b) * 60.0 / bpm

    return conv
