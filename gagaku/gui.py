"""Tkinter GUI。"""
from __future__ import annotations

import bisect
import re
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, font as tkfont, messagebox, ttk

from . import formatter, instruments, render, score as score_mod
from .audio import Player
from .scoreview import ScoreView
from .staffview import StaffView

TEMPLATE = """title: 新しい曲
mode: 平調
tempo: 60

[笙]
乙 - - - |

[篳篥]
四 - 一 - |

[竜笛]
干 - 五 丄 |

[琵琶]
ク - - - |

[筝]
閑三 - - - |

[鞨鼓]
. . 正 . |

[鉦鼓]
. . . 金 |

[太鼓]
. . 図 百 |
"""

FILETYPES = [("雅楽譜", "*.gaku"), ("テキスト", "*.txt"), ("すべて", "*.*")]


class App(tk.Tk):
    def __init__(self, path: str | None = None):
        super().__init__()
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f"{int(sw * 0.85)}x{int(sh * 0.82)}+{int(sw * 0.05)}+{int(sh * 0.04)}")
        self.minsize(900, 560)
        assets = Path(__file__).resolve().parent / "assets"
        try:
            self._icon = tk.PhotoImage(file=str(assets / "gagaku.png"))
            self.iconphoto(True, self._icon)
            if (assets / "gagaku.ico").exists():
                self.iconbitmap(default=str(assets / "gagaku.ico"))
        except tk.TclError:
            pass
        self.player = Player()
        self.path: Path | None = None
        self.audio = None
        self.events: list = []
        self.play_t0 = 0.0
        self.play_offset = 0.0
        self.playing = False
        self.rendering = False
        self._dirty = False

        fams = set(tkfont.families())
        # 縦をそろえるため等幅(全角=半角2文字分)のフォントを優先する
        # (Windows では日本語名で登録されていることがある)
        fam = next((f for f in ("BIZ UDGothic", "BIZ UDゴシック", "MS Gothic", "ＭＳ ゴシック",
                                "Noto Sans Mono CJK JP", "Osaka－等幅", "Yu Gothic UI", "Yu Gothic")
                    if f in fams), "TkFixedFont")
        self.edit_font = tkfont.Font(family=fam, size=15)
        self.pal_font = tkfont.Font(family=fam, size=12)

        self._build()
        if path:
            self.open_file(Path(path))
        else:
            self.text.insert("1.0", TEMPLATE)
            self.text.edit_modified(False)
            self._dirty = False
            self._sync_beats_box()
        self._update_title()
        self._highlight_syntax()
        self.after(80, self._place_sash)
        # 境目を左端まで寄せて譜面の欄が見えなくならないようにする
        self._body.bind("<ButtonRelease-1>", lambda e: self._clamp_sash())
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    # ------------------------------------------------------------ UI 構築
    def _build(self):
        bar = ttk.Frame(self, padding=(6, 4))
        bar.pack(side=tk.TOP, fill=tk.X)
        for label, cmd in (("新規", self.new_file), ("開く", self.ask_open),
                           ("保存", self.save), ("WAV書き出し", self.export_wav),
                           ("縦にそろえる", lambda: self.align_text(auto=False))):
            ttk.Button(bar, text=label, command=cmd).pack(side=tk.LEFT, padx=2)
        ttk.Separator(bar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=8)
        ttk.Button(bar, text="▶ 再生", command=self.play).pack(side=tk.LEFT, padx=2)
        ttk.Button(bar, text="▶ カーソルから", command=lambda: self.play(from_cursor=True)).pack(side=tk.LEFT, padx=2)
        ttk.Button(bar, text="■ 停止", command=self.stop).pack(side=tk.LEFT, padx=2)
        ttk.Separator(bar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=8)
        ttk.Label(bar, text="1小節").pack(side=tk.LEFT)
        self.beats_var = tk.StringVar(value="4")
        beats_box = ttk.Spinbox(bar, from_=1, to=32, increment=1, width=3, textvariable=self.beats_var,
                                command=self._set_beats)
        beats_box.pack(side=tk.LEFT)
        beats_box.bind("<Return>", lambda e: self._set_beats())
        beats_box.bind("<FocusOut>", lambda e: self._set_beats())
        ttk.Label(bar, text="拍").pack(side=tk.LEFT, padx=(0, 10))
        ttk.Label(bar, text="速さ").pack(side=tk.LEFT)
        self.speed = tk.DoubleVar(value=100)
        ttk.Spinbox(bar, from_=25, to=300, increment=5, width=5, textvariable=self.speed).pack(side=tk.LEFT)
        ttk.Label(bar, text="%").pack(side=tk.LEFT, padx=(0, 10))
        ttk.Label(bar, text="残響").pack(side=tk.LEFT)
        self.reverb = tk.DoubleVar(value=0.3)
        ttk.Scale(bar, from_=0, to=0.8, variable=self.reverb, length=110).pack(side=tk.LEFT)
        self.progress = ttk.Progressbar(bar, length=140, mode="determinate")
        self.progress.pack(side=tk.RIGHT, padx=4)

        body = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        body.pack(fill=tk.BOTH, expand=True)

        # 左: 「譜面テキスト」(編集) と「楽譜表示」(全楽器を拍でそろえた総譜) のタブ
        self.left_tabs = ttk.Notebook(body)
        left = ttk.Frame(self.left_tabs)
        self.left_tabs.add(left, text="譜面テキスト")
        self.score_view = ScoreView(self.left_tabs, self.edit_font.cget("family"), on_click=self._jump_to_event)
        self.left_tabs.add(self.score_view, text="楽譜表示")
        self.staff_view = StaffView(self.left_tabs, self.edit_font.cget("family"), on_click=self._jump_to_event)
        self.left_tabs.add(self.staff_view, text="五線譜")
        self.views = [self.score_view, self.staff_view]
        self.left_tabs.bind("<<NotebookTabChanged>>", lambda e: self._refresh_score_view())
        self.text = tk.Text(left, font=self.edit_font, undo=True, wrap=tk.NONE,
                            padx=8, pady=6, insertwidth=2, spacing1=2, spacing3=3)
        ys = ttk.Scrollbar(left, orient=tk.VERTICAL, command=self.text.yview)
        xs = ttk.Scrollbar(left, orient=tk.HORIZONTAL, command=self.text.xview)
        self.text.configure(yscrollcommand=ys.set, xscrollcommand=xs.set)
        ys.pack(side=tk.RIGHT, fill=tk.Y)
        xs.pack(side=tk.BOTTOM, fill=tk.X)
        self.text.pack(fill=tk.BOTH, expand=True)
        self.text.tag_configure("section", foreground="#8a1c1c")  # 太字にすると幅が変わりうるので色だけ
        self.text.tag_configure("header", foreground="#2b5f8a")
        self.text.tag_configure("comment", foreground="#888888")
        self.text.tag_configure("bar", foreground="#b0b0b0")
        self.text.tag_configure("error", background="#ffd0d0")
        self.text.tag_configure("playing", background="#ffe58a")
        self.text.bind("<<Modified>>", self._on_modified)
        self.text.bind("<KeyRelease>", lambda e: self._update_status())
        self.text.bind("<ButtonRelease-1>", lambda e: self._update_status())
        body.add(self.left_tabs, weight=3)

        # 右パネル: パレット + ミキサー
        right = ttk.Frame(body, padding=4)
        body.add(right, weight=2)
        self._body = body
        mix = ttk.LabelFrame(right, text="ミキサー(チェックを外すとミュート)", padding=4)
        mix.pack(side=tk.BOTTOM, fill=tk.X)
        ttk.Label(right, text="譜字パレット(クリックで挿入)").pack(anchor=tk.W)
        nb = ttk.Notebook(right)
        nb.pack(fill=tk.BOTH, expand=True, pady=(2, 6))
        for inst in instruments.INSTRUMENTS.values():
            frame = ttk.Frame(nb, padding=4)
            nb.add(frame, text=inst.display)
            ttk.Button(frame, text=f"[{inst.display}] 段を挿入",
                       command=lambda d=inst.display: self.insert_text(f"\n[{d}]\n")).grid(
                row=0, column=0, columnspan=7, sticky="we", pady=(0, 4))
            cols = 7
            items = inst.palette + (["+"] if inst.key == "biwa" else []) + ["-", ".", "|"]
            half = None
            if inst.key == "koto":
                half = tk.BooleanVar(value=False)
                ttk.Checkbutton(frame, text="½拍で挿入(譜字・休みに :1/2 を付ける)", variable=half).grid(
                    row=98, column=0, columnspan=cols, sticky="w", pady=(6, 0))

            def ins(s, half=half):
                if s == "+":
                    # 直前の譜字につなげる(「一」「+」「ク」と押すと「一+ク」)
                    if self.text.get("insert -1c", "insert") == " ":
                        self.text.delete("insert -1c", "insert")
                    self.insert_text("+")
                    return
                if self.text.get("insert -1c", "insert") == "+":
                    self.insert_text(s + " ")
                    return
                if half is not None and half.get() and s not in ("-", "|"):
                    s += ":1/2"
                self.insert_text(s + " ")

            for i, sym in enumerate(items):
                b = tk.Button(frame, text=sym, font=self.pal_font, width=3, relief=tk.GROOVE,
                              command=lambda s=sym, f=ins: f(s))
                b.grid(row=1 + i // cols, column=i % cols, padx=1, pady=1, sticky="nsew")
            ttk.Label(frame, text=_HELP.get(inst.key, ""), wraplength=480, justify=tk.LEFT,
                      foreground="#555").grid(row=99, column=0, columnspan=cols, sticky="w", pady=(6, 0))

        self.mute_vars: dict[str, tk.BooleanVar] = {}
        self.vol_vars: dict[str, tk.DoubleVar] = {}
        for r, inst in enumerate(instruments.INSTRUMENTS.values()):
            on = tk.BooleanVar(value=True)
            vol = tk.DoubleVar(value=1.0)
            self.mute_vars[inst.key], self.vol_vars[inst.key] = on, vol
            ttk.Checkbutton(mix, text=inst.display, variable=on).grid(row=r, column=0, sticky="w")
            ttk.Scale(mix, from_=0, to=2, variable=vol, length=200).grid(row=r, column=1, sticky="we", padx=4)
        mix.columnconfigure(1, weight=1)

        self.status = tk.StringVar()
        ttk.Label(self, textvariable=self.status, relief=tk.SUNKEN, anchor=tk.W, padding=(6, 2)).pack(
            side=tk.BOTTOM, fill=tk.X)

        self.bind_all("<Control-s>", lambda e: self.save())
        self.bind_all("<Control-o>", lambda e: self.ask_open())
        self.bind_all("<F5>", lambda e: self.play())
        self.bind_all("<F6>", lambda e: self.play(from_cursor=True))
        self.bind_all("<Escape>", lambda e: self.stop())
        self.bind_all("<Control-Shift-F>", lambda e: self.align_text(auto=False))
        self.bind_all("<Control-Shift-f>", lambda e: self.align_text(auto=False))

    # ------------------------------------------------------------ 左右の境目
    MIN_LEFT = 320   # 譜面の欄の最小幅(px)

    def _place_sash(self, tries: int = 0):
        """ウィンドウの幅が確定してから、譜面の欄が6割になるよう境目を置く。"""
        self.update_idletasks()
        w = self._body.winfo_width()
        if w < 2 * self.MIN_LEFT and tries < 50:   # まだ表示が終わっていない
            self.after(100, lambda: self._place_sash(tries + 1))
            return
        self._body.sashpos(0, max(self.MIN_LEFT, int(w * 0.6)))

    def _clamp_sash(self):
        w = self._body.winfo_width()
        if w >= 2 * self.MIN_LEFT and self._body.sashpos(0) < self.MIN_LEFT:
            self._body.sashpos(0, self.MIN_LEFT)

    # ------------------------------------------------------------ 編集補助
    def insert_text(self, s: str):
        self.text.insert(tk.INSERT, s)
        self.text.focus_set()

    def _on_modified(self, _e=None):
        if self.text.edit_modified():
            self._dirty = True
            self.text.edit_modified(False)
            self._update_title()
            self.after_idle(self._highlight_syntax)

    def align_text(self, auto: bool = True) -> bool:
        """譜面テキストを1段5小節・拍頭そろえに整形する。カーソルは同じ音符の位置に戻す。

        auto=True(開く・保存・再生時)は、譜面にエラーがあれば黙って何もしない。
        """
        old = self.text.get("1.0", "end-1c")
        try:
            new = formatter.format_text(old).rstrip("\n")
        except score_mod.ScoreError as e:
            if not auto:
                messagebox.showerror("整形できません", f"譜面にエラーがあります。\n{e}")
            return False
        if new == old:
            return True
        # カーソル位置の音符(パートと、そのパートの何番目か)を覚える
        anchor = None
        line, col = map(int, self.text.index(tk.INSERT).split("."))
        try:
            evs = score_mod.parse(old).events
            hit = [e for e in evs if (e.line, e.col_end) >= (line, col)]
            if hit:
                ev = min(hit, key=lambda e: (e.line, e.col))
                anchor = (ev.part, [e for e in evs if e.part == ev.part].index(ev))
        except score_mod.ScoreError:
            pass
        yview = self.text.yview()[0]
        self.text.edit_separator()
        self.text.delete("1.0", tk.END)
        self.text.insert("1.0", new)
        self.text.edit_separator()
        if anchor is not None:
            part_evs = [e for e in score_mod.parse(new).events if e.part == anchor[0]]
            if anchor[1] < len(part_evs):
                ev = part_evs[anchor[1]]
                self.text.mark_set(tk.INSERT, f"{ev.line}.{ev.col}")
        self.text.yview_moveto(yview)
        self.text.see(tk.INSERT)
        self._highlight_syntax()
        if not auto:
            self._update_status("拍の頭が縦にそろうように整形しました(1段5小節)")
        return True

    def _highlight_syntax(self):
        t = self.text
        for tag in ("section", "header", "comment", "bar"):
            t.tag_remove(tag, "1.0", tk.END)
        in_section = False
        for i, line in enumerate(t.get("1.0", "end-1c").splitlines(), start=1):
            code, _, _ = line.partition("#")
            if "#" in line:
                t.tag_add("comment", f"{i}.{len(code)}", f"{i}.end")
            s = code.strip()
            head_end = score_mod.section_header_end(line)
            if head_end is not None:
                in_section = True
                t.tag_add("section", f"{i}.0", f"{i}.{head_end}")
            elif not in_section and s:
                t.tag_add("header", f"{i}.0", f"{i}.{len(code)}")
            if in_section:
                for m in re.finditer(r"[|｜]", code):
                    t.tag_add("bar", f"{i}.{m.start()}", f"{i}.{m.end()}")

    def _update_status(self, msg: str | None = None):
        line, col = self.text.index(tk.INSERT).split(".")
        base = f"{line}行 {int(col) + 1}列"
        if msg is not None:
            self._last_msg = msg
        self.status.set(f"{base}    {getattr(self, '_last_msg', '')}")

    def _update_title(self):
        name = self.path.name if self.path else "無題"
        self.title(f"{'*' if self._dirty else ''}{name} - 雅楽譜プレイヤー")

    # ------------------------------------------------------------ ファイル
    def _confirm_discard(self) -> bool:
        if not self._dirty:
            return True
        r = messagebox.askyesnocancel("確認", "変更を保存しますか?")
        if r is None:
            return False
        return self.save() if r else True

    def new_file(self):
        if not self._confirm_discard():
            return
        self.stop()
        self.text.delete("1.0", tk.END)
        self.text.insert("1.0", TEMPLATE)
        self.text.edit_modified(False)
        self.path = None
        self._dirty = False
        self._update_title()
        self._sync_beats_box()
        self._refresh_score_view()

    def ask_open(self):
        if not self._confirm_discard():
            return
        p = filedialog.askopenfilename(filetypes=FILETYPES)
        if p:
            self.open_file(Path(p))

    def open_file(self, p: Path):
        self.stop()
        self.text.delete("1.0", tk.END)
        self.text.insert("1.0", p.read_text(encoding="utf-8-sig"))
        self.text.mark_set(tk.INSERT, "1.0")
        self.align_text(auto=True)
        self.text.edit_modified(False)
        self.text.edit_reset()
        self.path = p
        self._dirty = False
        self._update_title()
        self._highlight_syntax()
        self._sync_beats_box()
        self._refresh_score_view()   # 楽譜表示・五線譜タブを開いたままでも新しい譜面に描き直す

    # ------------------------------------------------------------ 1小節の拍数
    def _sync_beats_box(self):
        """入力欄を譜面に合わせる(ヘッダの beats:、なければ | から推定した小節の長さ)。"""
        try:
            sc = score_mod.parse(self.text.get("1.0", "end-1c"))
        except score_mod.ScoreError:
            return
        if sc.beats_per_bar:
            n = sc.beats_per_bar
        else:
            lengths = [b1 - b0 for b0, b1 in sc.bars()]
            common = max(set(lengths), key=lengths.count) if lengths else 4
            n = int(common) if common == int(common) and common > 0 else 4
        self._beats_applied = str(n)
        self.beats_var.set(str(n))

    def _set_beats(self):
        """入力欄の拍数をヘッダ beats: に書き、全楽器をその拍数ごとの小節に区切り直す。"""
        val = self.beats_var.get().strip().translate(str.maketrans("０１２３４５６７８９", "0123456789"))
        if not val.isdigit() or not 1 <= int(val) <= 32:
            self.beats_var.set(getattr(self, "_beats_applied", "4"))
            return
        if val == getattr(self, "_beats_applied", None):
            return
        lines = self.text.get("1.0", "end-1c").split("\n")
        first_sec = next((i for i, ln in enumerate(lines) if score_mod.section_header_end(ln) is not None),
                         len(lines))
        new_line = f"beats: {val}"
        key_re = re.compile(r"^\s*(beats|拍子|拍数)\s*[:：]", re.I)
        idx = next((i for i in range(first_sec) if key_re.match(lines[i])), None)
        if idx is not None:
            lines[idx] = new_line
        else:
            # ヘッダの最後の「key: 値」行の後ろに入れる
            last = max((i for i in range(first_sec)
                        if score_mod.HEADER_RE.match(lines[i].split("#", 1)[0].strip())), default=-1)
            lines.insert(last + 1, new_line)
        self.text.edit_separator()
        self.text.delete("1.0", tk.END)
        self.text.insert("1.0", "\n".join(lines))
        self.text.edit_separator()
        self._beats_applied = val
        self.align_text(auto=True)
        self._highlight_syntax()
        self._refresh_score_view()
        self._update_status(f"1小節 {val} 拍で区切り直しました")

    def save(self) -> bool:
        if self.path is None:
            p = filedialog.asksaveasfilename(defaultextension=".gaku", filetypes=FILETYPES)
            if not p:
                return False
            self.path = Path(p)
        self.align_text(auto=True)
        self.path.write_text(self.text.get("1.0", "end-1c") + "\n", encoding="utf-8")
        self._dirty = False
        self._update_title()
        self._update_status(f"保存しました: {self.path}")
        return True

    # ------------------------------------------------------------ 楽譜表示
    def _visible_view(self):
        """いま見えている表示タブ(楽譜表示・五線譜)。テキストタブなら None。"""
        sel = self.left_tabs.select()
        return next((v for v in self.views if str(v) == sel), None)

    def _score_tab_visible(self) -> bool:
        return self._visible_view() is not None

    def _refresh_score_view(self):
        """表示タブが見えているときに、現在のテキストから描き直す(再生中は再生中の譜面のまま)。"""
        view = self._visible_view()
        if view is None or self.playing:
            return
        try:
            sc = score_mod.parse(self.text.get("1.0", "end-1c"))
        except score_mod.ScoreError as e:
            view.set_message(f"譜面エラー: {e}")
            return
        view.set_score(sc)

    def _jump_to_event(self, ev):
        """楽譜表示で音をクリック → テキストの該当トークンにカーソルを置く(F6でそこから再生)。"""
        idx = f"{ev.line}.{ev.col}"
        self.text.mark_set(tk.INSERT, idx)
        self.text.tag_remove(tk.SEL, "1.0", tk.END)
        self.text.tag_add(tk.SEL, idx, f"{ev.line}.{ev.col_end}")
        self.text.see(idx)
        self._update_status(f"{ev.line}行の「{ev.symbol}」を選択(F6 でここから再生)")

    # ------------------------------------------------------------ 解析・レンダ
    def _parse(self):
        if not self.playing:
            self.align_text(auto=True)
        self.text.tag_remove("error", "1.0", tk.END)
        try:
            sc = score_mod.parse(self.text.get("1.0", "end-1c"))
        except score_mod.ScoreError as e:
            self.text.tag_add("error", f"{e.line}.0", f"{e.line}.end")
            self.text.see(f"{e.line}.0")
            self._update_status(f"エラー: {e}")
            messagebox.showerror("譜面エラー", str(e))
            return None
        if not sc.events:
            messagebox.showinfo("情報", "音符がありません")
            return None
        factor = max(0.1, float(self.speed.get() or 100) / 100)
        sc.tempo *= factor
        sc.tempo_changes = [(b, t * factor) for b, t in sc.tempo_changes]
        return sc

    def _render_async(self, sc, on_done):
        if self.rendering:
            return
        self.rendering = True
        mute = {k for k, v in self.mute_vars.items() if not v.get()}
        vols = {k: v.get() for k, v in self.vol_vars.items()}
        rev = self.reverb.get()
        self._update_status("レンダリング中…")

        def prog(x):
            self.after(0, lambda: self.progress.configure(value=x * 100))

        def work():
            try:
                data = render.render(sc, mute, vols, rev, progress=prog)
                self.after(0, lambda: on_done(data, sc))
            except Exception as e:  # noqa: BLE001
                err = e
                self.after(0, lambda: messagebox.showerror("レンダリング失敗", repr(err)))
            finally:
                self.rendering = False

        threading.Thread(target=work, daemon=True).start()

    # ------------------------------------------------------------ 再生
    def play(self, from_cursor: bool = False):
        sc = self._parse()
        if sc is None:
            return
        self.stop()
        cursor_line, cursor_col = map(int, self.text.index(tk.INSERT).split("."))

        def done(data, sc):
            offset = 0.0
            if from_cursor:
                cands = [e for e in sc.events if e.line == cursor_line and e.col_end >= cursor_col]
                ev = min(cands, key=lambda e: e.col) if cands else None
                if ev is None:
                    after = [e for e in sc.events if e.line > cursor_line]
                    ev = min(after, key=lambda e: (e.line, e.col)) if after else None
                offset = ev.start_sec if ev else 0.0
            start = int(offset * render.SR)
            try:
                self.player.play(data[start:])
            except Exception as e:  # noqa: BLE001
                messagebox.showerror("再生エラー", str(e))
                return
            self.audio = data
            self.events = sorted(sc.events, key=lambda e: e.start_sec)
            self._starts = [e.start_sec for e in self.events]
            self.play_offset = offset
            self.play_t0 = time.perf_counter()
            self.playing = True
            self.duration = len(data) / render.SR
            for v in self.views:  # 再生中の譜面と同じ音符オブジェクトでハイライトする
                v.set_score(sc)
            msg = f"再生中 ({sc.title or '無題'} / {sc.mode} / {sc.tempo:g} BPM)"
            if sc.warnings:
                msg += "  ⚠ " + " / ".join(sc.warnings)
            self._update_status(msg)
            self._tick()

        self._render_async(sc, done)

    def _tick(self):
        if not self.playing:
            return
        now = time.perf_counter() - self.play_t0 + self.play_offset
        self.text.tag_remove("playing", "1.0", tk.END)
        hi = bisect.bisect_right(self._starts, now)
        first = None
        active = []
        for ev in self.events[max(0, hi - 200):hi]:
            if ev.start_sec <= now < ev.end_sec:
                self.text.tag_add("playing", f"{ev.line}.{ev.col}", f"{ev.line}.{ev.col_end}")
                active.append(ev)
                first = first or ev
        for v in self.views:
            v.set_active(active)
        if first is not None:
            view = self._visible_view()
            if view is not None:
                view.see_event(first)
            else:
                self.text.see(f"{first.line}.{first.col}")
        if now >= self.duration:
            self.playing = False
            for v in self.views:
                v.set_active([])
            self._update_status("再生終了")
            return
        self.after(40, self._tick)

    def stop(self):
        self.player.stop()
        self.playing = False
        self.text.tag_remove("playing", "1.0", tk.END)
        for v in self.views:
            v.set_active([])

    def export_wav(self):
        sc = self._parse()
        if sc is None:
            return
        default = (self.path.stem if self.path else (sc.title or "gagaku")) + ".wav"
        p = filedialog.asksaveasfilename(defaultextension=".wav", initialfile=default,
                                         filetypes=[("WAV", "*.wav")])
        if not p:
            return

        def done(data, _sc):
            render.write_wav(p, data)
            self._update_status(f"書き出しました: {p}")

        self._render_async(sc, done)

    def on_close(self):
        if self._confirm_discard():
            self.stop()
            self.destroy()


_HELP = {
    "sho": "合竹名(乞 一 工 凢 乙 下 十 美 行 比 / 乙美 乙言 凢美 凢言)。「単千」のように単を付けると一本だけ。双調では「十」が5音の十になる。",
    "hichiriki": "舌 五 工 凢 六 四 一 丄 丁(低い順, G4〜A5)。ムは現行曲では使わない。音頭に塩梅(下からのすくい上げ)が付く。平調では舌を F#4、丄を F#5 にメリで下げる。調子ごとのメリは tunings.json の hichiriki で上書き可。",
    "ryuteki": "和(低)の譜字。延ばしは「-」(1拍)、「-:2」で2拍。「責六」または「六'」で責(1オクターブ上)、「干,」で1オクターブ下。干は六の上(E)で鳴る。〒→干 などの異体字も可。",
    "biwa": "1弦:一工凢フ斗 2弦:乚下十乙コ 3弦:ク七ヒ〻之 4弦:丄八丨ム也(開放,第1〜4柱)。通常は掻撥(低い弦から掻く)、「単」を付けると単音。「一+ク」のように + でつなぐと別々の弦を同時に鳴らす(同じ弦どうしは不可)。調弦は tunings.json(暫定値)。",
    "koto": "弦名 一〜十 斗 為 巾 で単音。「閑三」=閑掻、「早三」=早掻(近似)。半拍は「三:1/2」(休みは「.:1/2」)。調弦は tunings.json(暫定値)。",
    "kakko": "正=右の単打 / 片来=左桴のみのロール / 諸来=両桴のロール。来は長さ指定 例: 諸来:3(速さはテンポに連動)",
    "shoko": "金・生=一打 / ク=左 / レイ=右 / クレイ=左右2打",
    "taiko": "図=軽い前打(ズン) / 百=強打(ドウ)",
}


def main(path: str | None = None):
    import sys
    if sys.platform == "win32":
        try:  # 高DPI環境で文字がぼやけないように
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
            # タスクバーで python ではなくこのアプリのアイコンを出す
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Gagaku.Player")
        except Exception:  # noqa: BLE001
            pass
    App(path).mainloop()


def examples_dir() -> Path | None:
    """サンプル譜のフォルダ(pip で入れた場合はパッケージ内、ソースからならリポジトリの examples/)。"""
    here = Path(__file__).resolve().parent
    for d in (here / "examples", here.parent / "examples"):
        if d.is_dir():
            return d
    return None


def cli():
    """コマンド `gagaku-player [譜面.gaku | --demo | --version]` の入口。"""
    import argparse

    from . import __version__

    ap = argparse.ArgumentParser(prog="gagaku-player", description="雅楽譜プレイヤー")
    ap.add_argument("score", nargs="?", help="開く譜面ファイル(.gaku)")
    ap.add_argument("--demo", action="store_true", help="サンプル曲「若竹」を開く")
    ap.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    args = ap.parse_args()
    path = args.score
    if args.demo:
        d = examples_dir()
        path = str(d / "wakatake_sojo.gaku") if d else None
    main(path)
