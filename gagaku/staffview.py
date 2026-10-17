"""五線譜表示: 全楽器を1段5小節の総譜として五線譜で書き、各音の下に譜字を付ける(読み取り専用)。

- 拍の位置は全楽器で縦にそろう(拍の長さに比例した配置)。
- 1拍 = 4分音符。小節線や拍をまたぐ音はタイでつなぐ。
- 調号は使わず、♯は音ごとに付ける。
- 笙は合竹を和音で、琵琶の掻撥・筝の閑掻/早掻は鳴る音をアルペジオ付きの和音で書く。
- 打楽器は1線譜(鞨鼓・鉦鼓は×の符頭、来はトレモロの斜線)。
"""
from __future__ import annotations

import math
import re
import tkinter as tk
from fractions import Fraction
from tkinter import font as tkfont, ttk

from . import instruments

BARS_PER_SYSTEM = 5
_LETTER = {"C": 0, "D": 1, "E": 2, "F": 3, "G": 4, "A": 5, "B": 6}
_NOTE_RE = re.compile(r"^([A-G])(#?)(-?\d)$")

# 音部記号: 名前 → (第1線(一番下の線)の音の位置, 記号, 8va/8vb の表示)
CLEFS = {
    "bass": (2 * 7 + 4, "\U0001D122", ""),        # 第1線 G2
    "treble8vb": (3 * 7 + 2, "\U0001D11E", "8vb"),  # 第1線 E3(ト音記号の1オクターブ下)
    "treble": (4 * 7 + 2, "\U0001D11E", ""),       # 第1線 E4
    "treble8va": (5 * 7 + 2, "\U0001D11E", "8va"),  # 第1線 E5
}
VALUES = [Fraction(4), Fraction(3), Fraction(2), Fraction(3, 2), Fraction(1),
          Fraction(3, 4), Fraction(1, 2), Fraction(1, 4)]


def note_step(note: str) -> tuple[int, bool]:
    """'F#4' → (五線上の位置, ♯か)。位置は C0=0 から全音階で数える。"""
    m = _NOTE_RE.match(note)
    return int(m.group(3)) * 7 + _LETTER[m.group(1)], bool(m.group(2))


def split_values(start: Fraction, dur: Fraction, bars) -> list[tuple[Fraction, Fraction]]:
    """音の長さを、書ける音価(全・付点2分・2分・付点4分・4分・付点8分・8分・16分)に分ける。"""
    out = []
    end = start + dur
    for b0, b1 in bars:
        a, b = max(start, b0), min(end, b1)
        pos = a
        while pos < b:
            allowed = b - pos
            if pos.denominator != 1:                       # 拍の途中からなら次の拍まで
                allowed = min(allowed, Fraction(math.ceil(pos)) - pos)
            elif allowed >= 2 and (pos - b0) % 2:          # 2拍目・4拍目からの長い音は拍で切る
                allowed = Fraction(1)
            v = next((x for x in VALUES if x <= allowed), allowed)
            out.append((pos, v))
            pos += v
    return out


class StaffView(ttk.Frame):
    def __init__(self, master, family: str, on_click=None):
        super().__init__(master)
        self.on_click = on_click
        self.canvas = tk.Canvas(self, background="#fffdf7", highlightthickness=0)
        ys = ttk.Scrollbar(self, orient=tk.VERTICAL, command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=ys.set)
        ys.pack(side=tk.RIGHT, fill=tk.Y)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.s = 9  # 線の間隔(px)
        fams = set(tkfont.families())
        self.sym_family = next((f for f in ("Segoe UI Symbol", "Noto Music", "Bravura Text", "DejaVu Sans")
                                if f in fams), None)
        self.label_font = tkfont.Font(family=family, size=12, weight="bold")
        self.small_font = tkfont.Font(family=family, size=9)
        self.fit_fonts = [tkfont.Font(family=family, size=s) for s in (12, 10, 8, 7)]
        self.score = None
        self.message = "再生するか、このタブを開くと五線譜が表示されます"
        self._items: dict[int, list[int]] = {}
        self._event_by_item: dict[int, object] = {}
        self._active: set[int] = set()
        self.canvas.bind("<Configure>", lambda e: self.redraw())
        self.canvas.bind("<MouseWheel>", lambda e: self.canvas.yview_scroll(int(-e.delta / 120) * 3, "units"))
        self.canvas.tag_bind("note", "<Button-1>", self._on_note_click)

    # ------------------------------------------------------------ 公開API(ScoreView と同じ)
    def set_score(self, sc):
        self.score = sc
        self.message = ""
        self.redraw()

    def set_message(self, msg):
        self.score = None
        self.message = msg
        self.redraw()

    def set_active(self, events):
        ids = {id(e) for e in events}
        if ids == self._active:
            return
        for i in self._active - ids:
            for item in self._items.get(i, []):
                self.canvas.itemconfigure(item, fill="")
        for i in ids - self._active:
            for item in self._items.get(i, []):
                self.canvas.itemconfigure(item, fill="#ffe58a")
        self._active = ids

    def see_event(self, ev):
        items = self._items.get(id(ev))
        region = self.canvas.bbox("all")
        if not items or not region:
            return
        y0, y1 = self.canvas.bbox(items[0])[1], self.canvas.bbox(items[0])[3]
        top, bottom = self.canvas.canvasy(0), self.canvas.canvasy(self.canvas.winfo_height())
        if y0 < top or y1 > bottom:
            self.canvas.yview_moveto(max(0, (y0 - 30) / max(1, region[3])))

    # ------------------------------------------------------------ 楽器ごとの準備
    def _prepare(self, sc):
        """各パートの音部記号・音域・各音の (位置, ♯) リストを求める。"""
        info = {}
        for k in [k for k in instruments.INSTRUMENTS if k in {e.part for e in sc.events}]:
            inst = instruments.INSTRUMENTS[k]
            evs = sorted((e for e in sc.events if e.part == k), key=lambda e: e.beat)
            pitches = {}
            perc = True
            for e in evs:
                sp = inst.staff_pitches(e.symbol, e.octave, sc.mode)
                if sp is not None:
                    perc = False
                    notes, arp = sp
                    pitches[id(e)] = ([note_step(n) for n in notes], arp)
            if perc:
                info[k] = dict(perc=True, evs=evs, clef=None, lo=0, hi=0)
                continue
            steps = sorted(st for v in pitches.values() for st, _ in v[0])
            median = steps[len(steps) // 2]
            clef = min(CLEFS, key=lambda c: abs(median - (CLEFS[c][0] + 4)))
            info[k] = dict(perc=False, evs=evs, clef=clef, pitches=pitches, lo=steps[0], hi=steps[-1])
        return info

    # ------------------------------------------------------------ 描画
    def redraw(self):
        c = self.canvas
        c.delete("all")
        self._items.clear()
        self._event_by_item.clear()
        self._active = set()
        width = max(500, c.winfo_width())
        if self.score is None or not self.score.events:
            c.create_text(20, 20, text=self.message, anchor="nw", fill="#666", font=self.label_font)
            c.configure(scrollregion=(0, 0, width, 100))
            return
        sc, s = self.score, self.s
        info = self._prepare(sc)
        parts = list(info)
        bars = sc.bars()
        systems = [bars[i:i + BARS_PER_SYSTEM] for i in range(0, len(bars), BARS_PER_SYSTEM)]
        label_w = self.label_font.measure("篳篥") + 16
        uniform = len({b1 - b0 for b0, b1 in bars}) == 1
        clef_w = int((5.6 if uniform else 3.8) * s)   # 音部記号(+拍子記号)の幅
        margin = 10
        max_beats = max(float(sy[-1][1] - sy[0][0]) for sy in systems)
        ppb = (width - label_w - clef_w - 2 * margin - s) / max_beats
        text_h = self.fit_fonts[0].metrics("linespace") + 4

        # 各パートの段の高さ(上の余白・五線・下の余白・譜字)
        rows = {}
        for k in parts:
            d = info[k]
            if d["perc"]:
                rows[k] = (3.5 * s, 0, 3.5 * s)
            else:
                b = CLEFS[d["clef"]][0]
                top = max(3.5 * s, (d["hi"] - (b + 8)) * s / 2 + 4 * s)
                bottom = max(3.5 * s, (b - d["lo"]) * s / 2 + 4 * s)
                rows[k] = (top, 4 * s, bottom)

        y = margin
        for si, system in enumerate(systems):
            s0, s1 = system[0][0], system[-1][1]
            x_of = lambda b, s0=s0: label_w + clef_w + margin + s + float(b - s0) * ppb
            c.create_text(label_w + clef_w + margin, y, text=str(si * BARS_PER_SYSTEM + 1), anchor="nw",
                          fill="#9a8a75", font=self.small_font)
            y += 14
            staff_spans = []
            for k in parts:
                top_pad, staff_h, bot_pad = rows[k]
                staff_top = y + top_pad
                staff_spans.append((staff_top - (s if info[k]["perc"] else 0),
                                    staff_top + (s if info[k]["perc"] else staff_h)))
                d = info[k]
                # 楽器名
                c.create_text(label_w - 8, staff_top + staff_h / 2, text=instruments.INSTRUMENTS[k].display,
                              anchor="e", fill="#8a1c1c", font=self.label_font)
                x0, x1 = label_w + margin, x_of(s1)
                if d["perc"]:
                    c.create_line(x0, staff_top, x1, staff_top, fill="#555")
                    c.create_rectangle(x0 + 6, staff_top - s, x0 + 9, staff_top + s, fill="#555", outline="")
                    c.create_rectangle(x0 + 12, staff_top - s, x0 + 15, staff_top + s, fill="#555", outline="")
                else:
                    for i in range(5):
                        c.create_line(x0, staff_top + i * s, x1, staff_top + i * s, fill="#555")
                    self._draw_clef(x0, staff_top, d["clef"])
                if uniform:   # 拍子記号(全小節が同じ長さのときだけ)
                    n = int(bars[0][1] - bars[0][0])
                    tf = tkfont.Font(family=self.label_font.cget("family"), size=-int(2.1 * s), weight="bold")
                    tx = x0 + 4.3 * s
                    if d["perc"]:
                        c.create_text(tx, staff_top - 0.9 * s, text=str(n), font=tf)
                        c.create_text(tx, staff_top + 0.9 * s, text="4", font=tf)
                    else:
                        c.create_text(tx, staff_top + s, text=str(n), font=tf)
                        c.create_text(tx, staff_top + 3 * s, text="4", font=tf)
                # 小節線
                bl_top, bl_bot = (staff_top - s, staff_top + s) if d["perc"] else (staff_top, staff_top + 4 * s)
                for b0, _ in system[1:]:
                    xb = x_of(b0) - s
                    c.create_line(xb, bl_top, xb, bl_bot, fill="#555")
                c.create_line(x1, bl_top, x1, bl_bot, fill="#555", width=2 if si == len(systems) - 1 else 1)
                text_y = staff_top + staff_h + bot_pad + text_h / 2 - 4
                self._draw_part(k, d, system, s0, s1, x_of, staff_top, text_y, bars)
                y = staff_top + staff_h + bot_pad + text_h
            # 段の左端の縦線(全楽器をつなぐ)
            c.create_line(label_w + margin, staff_spans[0][0], label_w + margin, staff_spans[-1][1],
                          fill="#555", width=2)
            y += 18
        c.configure(scrollregion=(0, 0, width, y + margin))

    def _draw_clef(self, x0, staff_top, clef):
        c, s = self.canvas, self.s
        b, glyph, octave_mark = CLEFS[clef]
        if self.sym_family:
            f = tkfont.Font(family=self.sym_family, size=-int(6.4 * s if glyph == "\U0001D11E" else 3.6 * s))
            if glyph == "\U0001D11E":
                c.create_text(x0 + 1.6 * s, staff_top + 2.6 * s, text=glyph, font=f)
            else:
                c.create_text(x0 + 1.6 * s, staff_top + 1.6 * s, text=glyph, font=f)
        else:
            c.create_text(x0 + 1.4 * s, staff_top + 2 * s, text="G" if glyph == "\U0001D11E" else "F",
                          font=self.label_font)
        if octave_mark:
            yy = staff_top - 2.4 * s if octave_mark == "8va" else staff_top + 6.4 * s
            c.create_text(x0 + 1.7 * s, yy, text="8", font=self.small_font)

    def _draw_part(self, k, d, system, s0, s1, x_of, staff_top, text_y, bars):
        evs = d["evs"]
        pos = Fraction(0)
        part_end = self.score.part_lengths.get(k, Fraction(0))
        segments = []   # (開始, 長さ, event or None)
        for e in evs:
            if e.beat > pos:
                segments.append((pos, e.beat - pos, None))
            segments.append((e.beat, e.dur, e))
            pos = e.beat + e.dur
        if part_end > pos:
            segments.append((pos, part_end - pos, None))
        for n_i, (start, dur, ev) in enumerate(segments):
            if start + dur <= s0 or start >= s1:
                continue
            pieces = split_values(start, dur, [(b0, b1) for b0, b1 in system])
            if ev is None:
                for p, v in pieces:
                    self._draw_rest(x_of(p), staff_top, v, d["perc"], d)
                continue
            all_pieces = split_values(start, dur, bars)
            heads_prev = None
            for p, v in pieces:
                first = p == start
                last = p == all_pieces[-1][0]
                heads = self._draw_note(x_of(p), staff_top, v, ev, d, first)
                if heads_prev is not None:
                    self._tie(heads_prev, heads)
                elif not first:
                    self._tie(None, heads)   # 前の段から続くタイ
                heads_prev = heads if not last else None
                if first:
                    nxt = next((st for st, _, _ in segments[n_i + 1:]), s1)
                    self._label(ev, x_of(p), text_y, x_of(min(nxt, s1)) - x_of(p) - 4, staff_top, d)
            if heads_prev is not None and pieces[-1][0] + pieces[-1][1] >= s1:
                self._tie(heads_prev, None)  # 次の段へ続くタイ

    # ------------------------------------------------------------ 部品
    def _y(self, step, staff_top, clef):
        b = CLEFS[clef][0]
        return staff_top + 4 * self.s - (step - b) * self.s / 2

    def _draw_note(self, x, staff_top, v, ev, d, first):
        """1つの音価ぶんの音符(和音可)を書き、符頭の (x, y) のリストを返す。"""
        c, s = self.canvas, self.s
        hw, hh = 1.3 * s, 0.95 * s
        hollow = v >= 2
        tags = ("note",)
        reg = lambda item: self._event_by_item.__setitem__(item, ev)
        if d["perc"]:
            yy = staff_top
            if ev.part == "taiko":
                h = c.create_oval(x - hw / 2, yy - hh / 2, x + hw / 2, yy + hh / 2,
                                  fill="" if hollow else "#111", outline="#111", tags=tags)
                reg(h)
            else:
                for dx in (-1, 1):
                    h = c.create_line(x - hw / 2, yy - dx * hh / 2, x + hw / 2, yy + dx * hh / 2,
                                      fill="#111", width=2, tags=tags)
                    reg(h)
            if v < 4:
                sx = x + hw / 2
                c.create_line(sx, yy, sx, yy - 3.2 * s, fill="#111")
                self._flags(sx, yy - 3.2 * s, v, up=True)
                if "来" in ev.symbol:   # ロールはトレモロの斜線
                    for i in range(3):
                        ty = yy - 1.4 * s - i * 0.6 * s
                        c.create_line(sx - 0.6 * s, ty + 0.3 * s, sx + 0.6 * s, ty - 0.3 * s, fill="#111", width=2)
            self._dot(x, yy - s / 2, v)
            return [(x, yy)]

        steps, arp = d["pitches"][id(ev)]
        steps = sorted(set(steps))
        b = CLEFS[d["clef"]][0]
        mid = b + 4
        up = sum(st for st, _ in steps) / len(steps) < mid
        heads = []
        prev_step, prev_shift = None, False
        for st, sharp in steps:
            yy = self._y(st, staff_top, d["clef"])
            shift = prev_step is not None and st - prev_step == 1 and not prev_shift
            xx = x + (hw if up else -hw) * shift
            # 加線
            for ls in range(b - 2, st - 1, -2):
                ly = self._y(ls, staff_top, d["clef"])
                c.create_line(xx - hw * 0.85, ly, xx + hw * 0.85, ly, fill="#555")
            for ls in range(b + 10, st + 1, 2):
                ly = self._y(ls, staff_top, d["clef"])
                c.create_line(xx - hw * 0.85, ly, xx + hw * 0.85, ly, fill="#555")
            h = c.create_oval(xx - hw / 2, yy - hh / 2, xx + hw / 2, yy + hh / 2,
                              fill="" if hollow else "#111", outline="#111", width=1.4, tags=tags)
            reg(h)
            if sharp and first:
                acc_x = x - hw * (1.25 + 0.55 * (len(heads) % 2))
                if self.sym_family:
                    c.create_text(acc_x, yy, text="♯", font=(self.sym_family, -int(2.1 * s)), fill="#111")
                else:
                    c.create_text(acc_x, yy, text="#", font=self.small_font, fill="#111")
            self._dot(xx + (hw if up and not shift else 0), yy if (st - b) % 2 else yy - s / 2, v)
            heads.append((xx, yy))
            prev_step, prev_shift = st, shift
        ys = [yy for _, yy in heads]
        if v < 4:
            if up:
                sx = x + hw / 2
                c.create_line(sx, max(ys), sx, min(ys) - 3.4 * s, fill="#111", width=1.2)
                self._flags(sx, min(ys) - 3.4 * s, v, up=True)
            else:
                sx = x - hw / 2
                c.create_line(sx, min(ys), sx, max(ys) + 3.4 * s, fill="#111", width=1.2)
                self._flags(sx, max(ys) + 3.4 * s, v, up=False)
        if arp and first and len(heads) > 1:
            ax = x - hw * (2.3 if any(sh for _, sh in steps) else 1.4)
            pts = []
            yy, i = max(ys) + s / 2, 0
            while yy > min(ys) - s / 2:
                pts += [ax + (3 if i % 2 else -3), yy]
                yy -= s / 2
                i += 1
            if len(pts) >= 4:
                c.create_line(*pts, fill="#111", smooth=True)
        return heads

    def _flags(self, sx, sy, v, up):
        c, s = self.canvas, self.s
        n = 2 if v == Fraction(1, 4) else (1 if v in (Fraction(1, 2), Fraction(3, 4)) else 0)
        for i in range(n):
            oy = sy + (i * 0.8 * s if up else -i * 0.8 * s)
            ey = oy + (1.6 * s if up else -1.6 * s)
            c.create_line(sx, oy, sx + 0.9 * s, (oy + ey) / 2, sx + 0.6 * s, ey, fill="#111", width=1.6, smooth=True)

    def _dot(self, x, y, v):
        if v in (Fraction(3), Fraction(3, 2), Fraction(3, 4)):
            r = self.s * 0.17
            xx = x + self.s * 0.95
            self.canvas.create_oval(xx - r, y - r, xx + r, y + r, fill="#111", outline="")

    def _tie(self, a, b):
        c, s = self.canvas, self.s
        if a is None and b is None:
            return
        if a is None:   # 段の頭: 左から入る短いタイ
            for (x, y) in b:
                c.create_line(x - 2.2 * s, y + 0.6 * s, x - 1.1 * s, y + 1.0 * s, x - 0.7 * s, y + 0.6 * s,
                              smooth=True, fill="#111")
            return
        if b is None:   # 段の終わり: 右へ抜ける短いタイ
            for (x, y) in a:
                c.create_line(x + 0.7 * s, y + 0.6 * s, x + 1.4 * s, y + 1.0 * s, x + 2.4 * s, y + 0.6 * s,
                              smooth=True, fill="#111")
            return
        for (xa, ya), (xb, yb) in zip(a, b):
            c.create_line(xa + 0.6 * s, ya + 0.6 * s, (xa + xb) / 2, ya + 1.2 * s, xb - 0.6 * s, yb + 0.6 * s,
                          smooth=True, fill="#111")

    def _draw_rest(self, x, staff_top, v, perc, d):
        c, s = self.canvas, self.s
        mid = staff_top if perc else staff_top + 2 * s
        col = "#333"
        if v >= 4:
            yy = mid - s
            c.create_rectangle(x - 0.6 * s, yy, x + 0.6 * s, yy + 0.5 * s, fill=col, outline="")
        elif v >= 2:
            c.create_rectangle(x - 0.6 * s, mid - 0.5 * s, x + 0.6 * s, mid, fill=col, outline="")
        elif v >= 1:
            pts = [x - 0.2 * s, mid - 1.5 * s, x + 0.5 * s, mid - 0.6 * s, x - 0.3 * s, mid + 0.1 * s,
                   x + 0.4 * s, mid + 0.8 * s, x - 0.3 * s, mid + 0.6 * s, x, mid + 1.4 * s]
            c.create_line(*pts, fill=col, width=2)
        else:
            n = 2 if v < Fraction(1, 2) else 1
            for i in range(n):
                oy = mid - 0.4 * s + i * 0.8 * s
                c.create_oval(x - 0.5 * s, oy - 0.25 * s, x, oy + 0.25 * s, fill=col, outline="")
                c.create_line(x, oy, x + 0.5 * s, oy - 0.3 * s, fill=col, width=1.5)
            c.create_line(x + 0.5 * s, mid - 0.7 * s, x - 0.1 * s, mid + (1.2 if n == 2 else 0.9) * s, fill=col, width=1.5)
        self._dot(x, mid - s / 2, v)

    def _label(self, ev, x, y, room, staff_top, d):
        """音の下に譜字を書き、再生ハイライト用の背景を付ける。"""
        c = self.canvas
        text = ev.symbol + ("'" * ev.octave if ev.octave > 0 else "," * -ev.octave)
        fnt = next((f for f in self.fit_fonts if f.measure(text) <= max(room, 1)), self.fit_fonts[-1])
        tw = fnt.measure(text)
        top = staff_top - (2 * self.s if d["perc"] else self.s)
        bg = c.create_rectangle(x - 0.9 * self.s, top, x - 0.9 * self.s + max(tw + 6, 2 * self.s),
                                y + fnt.metrics("linespace") / 2 + 1, fill="", outline="", tags=("note",))
        c.tag_lower(bg)
        t = c.create_text(x - 0.7 * self.s, y, text=text, anchor="w", font=fnt, fill="#8a1c1c", tags=("note",))
        self._items.setdefault(id(ev), []).append(bg)
        self._event_by_item[bg] = ev
        self._event_by_item[t] = ev

    def _on_note_click(self, _e):
        item = self.canvas.find_withtag("current")
        if item and self.on_click:
            ev = self._event_by_item.get(item[0])
            if ev is not None:
                self.on_click(ev)
