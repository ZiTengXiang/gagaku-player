"""楽譜表示: 全楽器の拍頭を縦にそろえ、1段5小節で総譜のように並べる(読み取り専用)。"""
from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont, ttk

from . import instruments

BARS_PER_SYSTEM = 5


class ScoreView(ttk.Frame):
    def __init__(self, master, family: str, on_click=None):
        super().__init__(master)
        self.on_click = on_click
        # 楽器名の表示(プラグインで英語などに差し替えられる)
        self.label_func = lambda key: instruments.INSTRUMENTS[key].display
        self.canvas = tk.Canvas(self, background="#fffdf7", highlightthickness=0)
        ys = ttk.Scrollbar(self, orient=tk.VERTICAL, command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=ys.set)
        ys.pack(side=tk.RIGHT, fill=tk.Y)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.note_font = tkfont.Font(family=family, size=13)
        self.small_font = tkfont.Font(family=family, size=9)
        # 次の音までの空きに収まらない譜字は小さい字で書く
        self.fit_fonts = [self.note_font, tkfont.Font(family=family, size=11),
                          tkfont.Font(family=family, size=9), tkfont.Font(family=family, size=7)]
        self.label_font = tkfont.Font(family=family, size=12, weight="bold")
        self.score = None
        self.message = "再生するか、このタブを開くと楽譜が表示されます"
        self._items: dict[int, list[int]] = {}   # id(event) → 背景矩形の item id
        self._active: set[int] = set()
        self.canvas.bind("<Configure>", lambda e: self.redraw())
        self.canvas.bind("<MouseWheel>", self._on_wheel)
        self.canvas.tag_bind("note", "<Button-1>", self._on_note_click)
        self._event_by_item: dict[int, object] = {}

    # ------------------------------------------------------------ 公開API
    def set_score(self, sc):
        self.score = sc
        self.message = ""
        self.redraw()

    def set_message(self, msg: str):
        self.score = None
        self.message = msg
        self.redraw()

    def set_active(self, events):
        """再生中の音をハイライトする。"""
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
        if not items:
            return
        x0, y0, x1, y1 = self.canvas.bbox(items[0])
        top, bottom = self.canvas.canvasy(0), self.canvas.canvasy(self.canvas.winfo_height())
        region = self.canvas.bbox("all")
        if region and (y0 < top or y1 > bottom):
            total = max(1, region[3])
            self.canvas.yview_moveto(max(0, (y0 - 40) / total))

    # ------------------------------------------------------------ 描画
    def redraw(self):
        c = self.canvas
        c.delete("all")
        self._items.clear()
        self._event_by_item.clear()
        self._active = set()
        width = max(400, c.winfo_width())
        if self.score is None or not self.score.events:
            c.create_text(20, 20, text=self.message, anchor="nw", fill="#666", font=self.note_font)
            c.configure(scrollregion=(0, 0, width, 100))
            return

        sc = self.score
        parts = [k for k in instruments.INSTRUMENTS if k in {e.part for e in sc.events}]
        bars = sc.bars()
        systems = [bars[i:i + BARS_PER_SYSTEM] for i in range(0, len(bars), BARS_PER_SYSTEM)]
        label_w = max(self.label_font.measure(self.label_func(k)) for k in parts) + 24
        margin = 12
        max_beats = max(float(s[-1][1] - s[0][0]) for s in systems)
        ppb = (width - label_w - 2 * margin) / max_beats   # 1拍あたりのピクセル
        row_h = int(self.note_font.metrics("linespace") * 1.7)
        head_h = self.small_font.metrics("linespace") + 6
        gap = 18
        by_part = {k: sorted((e for e in sc.events if e.part == k), key=lambda e: e.beat) for k in parts}

        y = margin
        for si, system in enumerate(systems):
            s0, s1 = system[0][0], system[-1][1]
            x_of = lambda b: label_w + margin + float(b - s0) * ppb
            top = y + head_h
            bottom = top + row_h * len(parts)
            # 段の背景と行の区切り
            for r in range(len(parts)):
                if r % 2:
                    c.create_rectangle(label_w, top + r * row_h, x_of(s1), top + (r + 1) * row_h,
                                       fill="#f6f1e4", outline="")
            # 拍の目盛り
            b = s0
            while b < s1:
                c.create_line(x_of(b), top, x_of(b), bottom, fill="#e4dccb")
                b += 1
            # 小節線と小節番号
            for bi, (b0, b1) in enumerate(system):
                no = si * BARS_PER_SYSTEM + bi + 1
                c.create_line(x_of(b0), top - 2, x_of(b0), bottom, fill="#7a6a55", width=1.5)
                c.create_text(x_of(b0) + 3, y, text=str(no), anchor="nw", fill="#9a8a75", font=self.small_font)
            c.create_line(x_of(s1), top - 2, x_of(s1), bottom, fill="#7a6a55", width=1.5)
            # 楽器名
            for r, k in enumerate(parts):
                c.create_text(label_w - 10, top + r * row_h + row_h / 2, text=self.label_func(k),
                              anchor="e", fill="#8a1c1c", font=self.label_font)
            # 音
            for r, k in enumerate(parts):
                cy = top + r * row_h + row_h / 2
                evs = by_part[k]
                for n_i, ev in enumerate(evs):
                    e0, e1 = ev.beat, ev.beat + ev.dur
                    if e1 <= s0 or e0 >= s1:
                        continue
                    starts_here = e0 >= s0
                    xa = x_of(max(e0, s0))
                    xb = x_of(min(e1, s1))
                    label = ev.symbol + ("'" * ev.octave if ev.octave > 0 else "," * -ev.octave)
                    if starts_here:
                        nxt = evs[n_i + 1].beat if n_i + 1 < len(evs) else s1
                        room = x_of(min(nxt, s1)) - xa - 6
                        fnt = next((f for f in self.fit_fonts if f.measure(label) <= room), self.fit_fonts[-1])
                        tw = fnt.measure(label)
                        bg = c.create_rectangle(xa + 1, cy - row_h / 2 + 3, xa + tw + 7, cy + row_h / 2 - 3,
                                                fill="", outline="", tags=("note",))
                        t = c.create_text(xa + 4, cy, text=label, anchor="w", font=fnt,
                                          fill="#1a1a1a", tags=("note",))
                        self._items.setdefault(id(ev), []).append(bg)
                        self._event_by_item[bg] = ev
                        self._event_by_item[t] = ev
                        line_from = xa + tw + 9
                    else:
                        line_from = xa + 2   # 前の段から続く音
                    if xb - line_from > 4:
                        # 音の長さ(延ばし)を細い線で示す
                        c.create_line(line_from, cy, xb - 4, cy, fill="#b9a98f", width=2, capstyle=tk.ROUND)
            y = bottom + gap
        c.configure(scrollregion=(0, 0, width, y + margin))

    # ------------------------------------------------------------ 操作
    def _on_wheel(self, e):
        self.canvas.yview_scroll(int(-e.delta / 120) * 3, "units")

    def _on_note_click(self, _e):
        item = self.canvas.find_withtag("current")
        if item and self.on_click:
            ev = self._event_by_item.get(item[0])
            if ev is not None:
                self.on_click(ev)
