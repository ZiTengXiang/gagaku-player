"""譜面テキストの整形: 1段5小節で全楽器の行を上下に並べ、拍の頭を縦にそろえる。

整形しても音(各音の開始拍・長さ・テンポ変化)は変わらない。
等幅フォント(全角=半角2文字分)で見たときに縦がそろう。
"""
from __future__ import annotations

import math
import re
import unicodedata
from fractions import Fraction

from . import instruments
from .score import TOKEN_RE, parse, section_header_end

BARS_PER_SYSTEM = 5
SYSTEM_MARK_RE = re.compile(r"^#\s*-+\s*\d+(〜\d+)?小節")


def text_width(s: str) -> int:
    return sum(2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1 for ch in s)


def _fmt_dur(d: Fraction) -> str:
    return str(d.numerator) if d.denominator == 1 else f"{d.numerator}/{d.denominator}"


def _place_note(cells, s: Fraction, e: Fraction, label: str):
    """音 [s, e) を拍のセルに置く。拍頭から始まる整数拍の音は「譜字 - -」で書く。"""
    c0 = math.floor(s)
    if s.denominator == 1 and e.denominator == 1:
        cells.setdefault(c0, []).append((s, label))
        for c in range(c0 + 1, int(e)):
            cells.setdefault(c, []).append((Fraction(c), "-"))
        return
    b = min(e, Fraction(c0 + 1))
    remaining = e - b
    full = math.floor(remaining)
    first = (b - s) + (remaining - full)   # 端数はまとめて最初の音に持たせる
    cells.setdefault(c0, []).append((s, label if first == 1 else f"{label}:{_fmt_dur(first)}"))
    for i in range(full):
        cells.setdefault(c0 + 1 + i, []).append((Fraction(c0 + 1 + i), "-"))


def _place_rest(cells, a: Fraction, b: Fraction):
    """休み [a, b) を拍のセルに置く(休みは - で延ばせないので拍ごとに書く)。"""
    pos = a
    while pos < b:
        nxt = min(b, Fraction(math.floor(pos) + 1))
        length = nxt - pos
        cells.setdefault(math.floor(pos), []).append((pos, "." if length == 1 else f".:{_fmt_dur(length)}"))
        pos = nxt


def format_text(text: str) -> str:
    """整形済みのテキストを返す。譜面にエラーがあれば ScoreError を送出する。"""
    sc = parse(text)
    lines = text.splitlines()

    # 最初の [楽器] より前(ヘッダとコメント)はそのまま残す
    first_sec = next((i for i, ln in enumerate(lines) if section_header_end(ln) is not None), len(lines))
    head = lines[:first_sec]
    while head and (not head[-1].strip() or SYSTEM_MARK_RE.match(head[-1].strip())):
        head.pop()
    # 本文中のコメント(整形で付けた段の見出しは除く)はヘッダの後ろへまとめる
    moved = []
    for ln in lines[first_sec:]:
        if "#" in ln:
            c = "#" + ln.split("#", 1)[1]
            if not SYSTEM_MARK_RE.match(c.strip()):
                moved.append(c.rstrip())

    parts = [k for k in instruments.INSTRUMENTS if k in sc.part_lengths]
    src = text.splitlines()

    # パートごとに 拍番号 → [(位置, 文字列)] を作る
    cells_by_part: dict[str, dict[int, list]] = {}
    for k in parts:
        cells: dict[int, list] = {}
        pos = Fraction(0)
        for ev in sorted((e for e in sc.events if e.part == k), key=lambda e: e.beat):
            if ev.beat > pos:
                _place_rest(cells, pos, ev.beat)
            tok = src[ev.line - 1][ev.col:ev.col_end]
            m = TOKEN_RE.match(tok)
            label = (m.group("sym") + (m.group("oct") or "")) if m else ev.symbol
            _place_note(cells, ev.beat, ev.beat + ev.dur, label)
            pos = ev.beat + ev.dur
        if sc.part_lengths[k] > pos:
            _place_rest(cells, pos, sc.part_lengths[k])
        for part, beat, tok in sc.tempo_marks:
            if part == k:
                # 同じ位置の音より先に置く
                cells.setdefault(math.floor(beat), []).append((beat - Fraction(1, 10**6), tok))
        cells_by_part[k] = cells

    bars = sc.bars()
    systems = [bars[i:i + BARS_PER_SYSTEM] for i in range(0, len(bars), BARS_PER_SYSTEM)]
    labels = {k: f"[{instruments.INSTRUMENTS[k].display}]" for k in parts}
    label_w = max(text_width(v) for v in labels.values()) + 1

    out = head[:]
    if moved:
        out += [""] + moved
    for si, system in enumerate(systems):
        first_no = si * BARS_PER_SYSTEM + 1
        last_no = first_no + len(system) - 1
        out += ["", f"# ---- {first_no}〜{last_no}小節" if last_no > first_no else f"# ---- {first_no}小節"]
        # 各拍の列幅(全楽器で最も広いもの)
        beat_cols = []
        for (b0, b1) in system:
            beat_cols.append(list(range(math.floor(b0), math.ceil(b1))))
        width: dict[int, int] = {}
        texts: dict[tuple[str, int], str] = {}
        for k in parts:
            for cols in beat_cols:
                for c in cols:
                    items = sorted(cells_by_part[k].get(c, []), key=lambda x: x[0])
                    t = " ".join(s for _, s in items)
                    texts[(k, c)] = t
                    width[c] = max(width.get(c, 1), text_width(t))
        for k in parts:
            row = labels[k] + " " * (label_w - text_width(labels[k]))
            for cols in beat_cols:
                for c in cols:
                    t = texts[(k, c)]
                    # 拍と拍の間は空白2つ(同じ拍の中の音は空白1つ)
                    row += t + " " * (width[c] - text_width(t)) + "  "
                row += "|  "
            out.append(row.rstrip())
    return "\n".join(out) + "\n"
