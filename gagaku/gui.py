"""Tkinter GUI。

画面の文言はすべて App.t(キー, 既定の日本語) を通して出し、プラグインが差し替えられる
ようにしている(キーの一覧は bundled_plugins/english/plugin.py の TEXTS を参照)。
"""
from __future__ import annotations

import bisect
import re
import threading
import time
import tkinter as tk
from fractions import Fraction
from pathlib import Path
from tkinter import filedialog, font as tkfont, messagebox, ttk

from . import formatter, instruments, plugins, render, score as score_mod
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

_MODE_RE = re.compile(r"^\s*(?:mode|調子)\s*[:：]\s*(\S+)", re.M | re.I)


def _fmt_beats(x) -> str:
    """拍数を '1' '0.5' '1.25' のように書く。"""
    return f"{float(x):g}"


class Tooltip:
    """ウィジェットの上にしばらくカーソルを置くと出る、控えめな説明の吹き出し。"""

    DELAY_MS = 450

    def __init__(self, widget, text_func):
        self.widget, self.text_func = widget, text_func
        self.tip = None
        self.job = None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")

    def _schedule(self, _e=None):
        self._cancel()
        self.job = self.widget.after(self.DELAY_MS, self._show)

    def _cancel(self):
        if self.job:
            self.widget.after_cancel(self.job)
            self.job = None

    def _show(self):
        self.job = None
        text = self.text_func()
        if not text:
            return
        x = self.widget.winfo_rootx() + 8
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
        self.tip = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        try:
            tw.attributes("-topmost", True)
        except tk.TclError:
            pass
        tk.Label(tw, text=text, justify=tk.LEFT, background="#fffbea", foreground="#3a3228",
                 relief=tk.SOLID, borderwidth=1, padx=7, pady=4,
                 font=("Segoe UI", 9)).pack()

    def _hide(self, _e=None):
        self._cancel()
        if self.tip is not None:
            self.tip.destroy()
            self.tip = None


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
        self._tr_items: list = []        # (文言を設定する関数, キー, 既定の文言)
        self._palette: list = []         # (楽器キー, フレーム, [(ボタン, 譜字)])
        self._mixer_checks: dict = {}

        fams = set(tkfont.families())
        # 縦をそろえるため等幅(全角=半角2文字分)のフォントを優先する
        # (Windows では日本語名で登録されていることがある)
        fam = next((f for f in ("BIZ UDGothic", "BIZ UDゴシック", "MS Gothic", "ＭＳ ゴシック",
                                "Noto Sans Mono CJK JP", "Osaka－等幅", "Yu Gothic UI", "Yu Gothic")
                    if f in fams), "TkFixedFont")
        self.edit_font = tkfont.Font(family=fam, size=15)
        self.pal_font = tkfont.Font(family=fam, size=12)
        self.pal_font_small = tkfont.Font(family=fam, size=10)

        # プラグインは画面を作る前に読み込み、最初から差し替えた文言で作る
        self.plugins = plugins.PluginManager(current_mode=self._current_mode, on_change=self.retranslate)
        self.plugins.load_enabled()

        self._build()
        if path:
            self.open_file(Path(path))
        else:
            self.text.insert("1.0", TEMPLATE)
            self.text.edit_modified(False)
            self._dirty = False
            self._sync_beats_box()
            self._sync_ma_box()
        self._update_title()
        self._highlight_syntax()
        self.after(80, self._place_sash)
        # 境目を左端まで寄せて譜面の欄が見えなくならないようにする
        self._body.bind("<ButtonRelease-1>", lambda e: self._clamp_sash())
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        for pid, err in self.plugins.errors.items():
            self._update_status(err)

    # ------------------------------------------------------------ 文言(プラグインで差し替え可能)
    def t(self, key: str, default: str, **kw) -> str:
        s = self.plugins.texts().get(key, default)
        try:
            return s.format(**kw) if kw else s
        except (KeyError, IndexError, ValueError):
            return default.format(**kw) if kw else default

    def _tr(self, setter, key: str, default: str):
        """文言を設定し、プラグインの切り替え時に設定し直せるよう覚えておく。"""
        self._tr_items.append((setter, key, default))
        setter(self.t(key, default))

    def _tr_widget(self, widget, key: str, default: str, option: str = "text"):
        self._tr(lambda s, w=widget: w.configure(**{option: s}), key, default)
        return widget

    def inst_label(self, key: str) -> str:
        return self.plugins.instrument_label(key) or instruments.INSTRUMENTS[key].display

    def palette_label(self, inst_key: str, sym: str) -> str:
        return self.plugins.palette_label(inst_key, sym) or sym

    def _current_mode(self) -> str:
        text = getattr(self, "text", None)
        if text is not None:
            m = _MODE_RE.search(text.get("1.0", "end-1c").split("[", 1)[0])
            if m and m.group(1) in instruments.MODES:
                return m.group(1)
        return "平調"

    def retranslate(self):
        """プラグインの有効・無効が変わったら、画面の文言を設定し直す。"""
        if not hasattr(self, "text"):
            return
        for setter, key, default in self._tr_items:
            try:
                setter(self.t(key, default))
            except tk.TclError:
                pass
        self._layout_palette()
        for key, chk in self._mixer_checks.items():
            chk.configure(text=self.inst_label(key))
        for v in self.views:
            v.redraw()
        self._update_title()
        self._update_status()

    # ------------------------------------------------------------ UI 構築
    def _build(self):
        self._build_menu()
        bar = ttk.Frame(self, padding=(6, 4))
        bar.pack(side=tk.TOP, fill=tk.X)
        for key, label, cmd in (("tb.new", "新規", self.new_file), ("tb.open", "開く", self.ask_open),
                                ("tb.save", "保存", self.save), ("tb.export", "WAV書き出し", self.export_wav),
                                ("tb.align", "縦にそろえる", lambda: self.align_text(auto=False))):
            self._tr_widget(ttk.Button(bar, command=cmd), key, label).pack(side=tk.LEFT, padx=2)
        ttk.Separator(bar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=8)
        self._tr_widget(ttk.Button(bar, command=self.play), "tb.play", "▶ 再生").pack(side=tk.LEFT, padx=2)
        self._tr_widget(ttk.Button(bar, command=lambda: self.play(from_cursor=True)),
                        "tb.play_cursor", "▶ カーソルから").pack(side=tk.LEFT, padx=2)
        self._tr_widget(ttk.Button(bar, command=self.stop), "tb.stop", "■ 停止").pack(side=tk.LEFT, padx=2)
        ttk.Separator(bar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=8)
        self._tr_widget(ttk.Label(bar), "tb.bar", "1小節").pack(side=tk.LEFT)
        self.beats_var = tk.StringVar(value="4")
        beats_box = ttk.Spinbox(bar, from_=1, to=32, increment=1, width=3, textvariable=self.beats_var,
                                command=self._set_beats)
        beats_box.pack(side=tk.LEFT)
        beats_box.bind("<Return>", lambda e: self._set_beats())
        beats_box.bind("<FocusOut>", lambda e: self._set_beats())
        self._tr_widget(ttk.Label(bar), "tb.beats_unit", "拍").pack(side=tk.LEFT, padx=(0, 10))
        # 小節の間(ま): オンにすると各小節の終わりに間を挟み、その間は鳴っている音を延ばす
        self.ma_on = tk.BooleanVar(value=False)
        self.ma_len = tk.StringVar(value="1")
        self._tr_widget(ttk.Checkbutton(bar, variable=self.ma_on, command=self._set_ma),
                        "tb.ma", "小節の間(ま)").pack(side=tk.LEFT)
        ma_box = ttk.Spinbox(bar, from_=0.25, to=16, increment=0.25, width=4, textvariable=self.ma_len,
                             command=self._set_ma)
        ma_box.pack(side=tk.LEFT)
        ma_box.bind("<Return>", lambda e: self._set_ma())
        ma_box.bind("<FocusOut>", lambda e: self._set_ma())
        self._tr_widget(ttk.Label(bar), "tb.beats_unit", "拍").pack(side=tk.LEFT, padx=(0, 10))
        self._tr_widget(ttk.Label(bar), "tb.speed", "速さ").pack(side=tk.LEFT)
        self.speed = tk.DoubleVar(value=100)
        ttk.Spinbox(bar, from_=25, to=300, increment=5, width=5, textvariable=self.speed).pack(side=tk.LEFT)
        ttk.Label(bar, text="%").pack(side=tk.LEFT, padx=(0, 10))
        self._tr_widget(ttk.Label(bar), "tb.reverb", "残響").pack(side=tk.LEFT)
        self.reverb = tk.DoubleVar(value=0.3)
        ttk.Scale(bar, from_=0, to=0.8, variable=self.reverb, length=110).pack(side=tk.LEFT)
        self.progress = ttk.Progressbar(bar, length=140, mode="determinate")
        self.progress.pack(side=tk.RIGHT, padx=4)

        body = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        body.pack(fill=tk.BOTH, expand=True)

        # 左: 「譜面テキスト」(編集)・「楽譜表示」・「五線譜」のタブ
        self.left_tabs = ttk.Notebook(body)
        left = ttk.Frame(self.left_tabs)
        self.left_tabs.add(left)
        self.score_view = ScoreView(self.left_tabs, self.edit_font.cget("family"), on_click=self._jump_to_event)
        self.left_tabs.add(self.score_view)
        self.staff_view = StaffView(self.left_tabs, self.edit_font.cget("family"), on_click=self._jump_to_event)
        self.left_tabs.add(self.staff_view)
        self.views = [self.score_view, self.staff_view]
        for v in self.views:
            v.label_func = self.inst_label
        for tab, key, default in ((left, "tab.text", "譜面テキスト"), (self.score_view, "tab.score", "楽譜表示"),
                                  (self.staff_view, "tab.staff", "五線譜")):
            self._tr(lambda s, w=tab: self.left_tabs.tab(w, text=s), key, default)
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
        mix = self._tr_widget(ttk.LabelFrame(right, padding=4), "mixer.title", "ミキサー(チェックを外すとミュート)")
        mix.pack(side=tk.BOTTOM, fill=tk.X)
        self._tr_widget(ttk.Label(right), "palette.title", "譜字パレット(クリックで挿入)").pack(anchor=tk.W)
        self.palette_nb = nb = ttk.Notebook(right)
        nb.pack(fill=tk.BOTH, expand=True, pady=(2, 6))
        for inst in instruments.INSTRUMENTS.values():
            self._build_palette_tab(nb, inst)
        self._layout_palette()

        self.mute_vars: dict[str, tk.BooleanVar] = {}
        self.vol_vars: dict[str, tk.DoubleVar] = {}
        for r, inst in enumerate(instruments.INSTRUMENTS.values()):
            on = tk.BooleanVar(value=True)
            vol = tk.DoubleVar(value=1.0)
            self.mute_vars[inst.key], self.vol_vars[inst.key] = on, vol
            chk = ttk.Checkbutton(mix, text=self.inst_label(inst.key), variable=on)
            chk.grid(row=r, column=0, sticky="w")
            self._mixer_checks[inst.key] = chk
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

    def _build_menu(self):
        menubar = tk.Menu(self, tearoff=False)
        filem = tk.Menu(menubar, tearoff=False)
        plugm = tk.Menu(menubar, tearoff=False)
        menubar.add_cascade(label="File", menu=filem)
        menubar.add_cascade(label="Plugins", menu=plugm)
        self._tr(lambda s: menubar.entryconfigure(0, label=s), "menu.file", "ファイル")
        self._tr(lambda s: menubar.entryconfigure(1, label=s), "menu.plugins", "プラグイン")
        for i, (key, label, cmd) in enumerate((
                ("menu.file.new", "新規", self.new_file), ("menu.file.open", "開く…", self.ask_open),
                ("menu.file.save", "保存", self.save), ("menu.file.export", "WAV書き出し…", self.export_wav),
                ("menu.file.quit", "終了", self.on_close))):
            filem.add_command(label=label, command=cmd)
            self._tr(lambda s, i=i: filem.entryconfigure(i, label=s), key, label)
        plugm.add_command(label="Plugins", command=self.open_plugin_manager)
        self._tr(lambda s: plugm.entryconfigure(0, label=s), "menu.plugins.manage", "プラグインを探す・管理…")
        self.config(menu=menubar)

    def _build_palette_tab(self, nb, inst):
        frame = ttk.Frame(nb, padding=4)
        nb.add(frame)
        self._tr(lambda s, k=inst.key, f=frame: nb.tab(f, text=self.inst_label(k)), f"inst.{inst.key}", "")
        head = ttk.Button(frame, command=lambda d=inst.display: self.insert_text(f"\n[{d}]\n"))
        self._tr(lambda s, w=head, d=inst.display: w.configure(text=s.format(name=d)),
                 "palette.insert_section", "[{name}] 段を挿入")
        items = inst.palette + (["+"] if inst.key == "biwa" else []) + ["-", ".", "|"]
        half = None
        extras = []
        if inst.key == "koto":
            half = tk.BooleanVar(value=False)
            extras.append(self._tr_widget(ttk.Checkbutton(frame, variable=half), "palette.koto_half",
                                          "½拍で挿入(譜字・休みに :1/2 を付ける)"))
        help_lbl = ttk.Label(frame, wraplength=480, justify=tk.LEFT, foreground="#555")
        self._tr_widget(help_lbl, f"help.{inst.key}", _HELP.get(inst.key, ""))

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

        buttons = []
        for sym in items:
            b = tk.Button(frame, relief=tk.GROOVE, command=lambda s=sym, f=ins: f(s))
            Tooltip(b, lambda k=inst.key, s=sym: self.plugins.palette_tooltip(k, s, self._current_mode()))
            buttons.append((b, sym))
        self._palette.append((inst.key, frame, head, buttons, extras, help_lbl))

    def _layout_palette(self):
        """譜字ボタンの表示名を設定し直し、長さに合わせて並べ直す。"""
        for key, frame, head, buttons, extras, help_lbl in self._palette:
            labels = [self.palette_label(key, s) for _, s in buttons]
            longest = max(len(lab) for lab in labels)
            long = longest > 3
            cols = 7 if not long else (4 if longest <= 10 else 3)
            for c in range(7):
                use = long and c < cols
                frame.columnconfigure(c, weight=1 if use else 0, uniform="pal" if use else "")
            head.grid(row=0, column=0, columnspan=cols, sticky="we", pady=(0, 4))
            for i, ((b, _), lab) in enumerate(zip(buttons, labels)):
                b.configure(text=lab, font=self.pal_font_small if long else self.pal_font,
                            width=0 if long else 3)
                b.grid(row=1 + i // cols, column=i % cols, padx=1, pady=1, sticky="nsew")
            for j, w in enumerate(extras):
                w.grid(row=98 + j, column=0, columnspan=cols, sticky="w", pady=(6, 0))
            help_lbl.grid(row=99 + len(extras), column=0, columnspan=cols, sticky="w", pady=(6, 0))

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

    # ------------------------------------------------------------ プラグイン
    def open_plugin_manager(self):
        if getattr(self, "_plugin_dialog", None) is not None and self._plugin_dialog.winfo_exists():
            self._plugin_dialog.lift()
            return
        self._plugin_dialog = PluginDialog(self)

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
                messagebox.showerror(self.t("dlg.cannot_align", "整形できません"),
                                     self.t("dlg.align_error", "譜面にエラーがあります。\n{err}", err=e))
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
            self._update_status(self.t("status.aligned", "拍の頭が縦にそろうように整形しました(1段5小節)"))
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
        base = self.t("status.pos", "{line}行 {col}列", line=line, col=int(col) + 1)
        if msg is not None:
            self._last_msg = msg
        self.status.set(f"{base}    {getattr(self, '_last_msg', '')}")

    def _update_title(self):
        name = self.path.name if self.path else self.t("title.untitled", "無題")
        self.title(f"{'*' if self._dirty else ''}{name} - {self.t('title.app', '雅楽譜プレイヤー')}")

    def _filetypes(self):
        return [(self.t("file.gaku", "雅楽譜"), "*.gaku"), (self.t("file.txt", "テキスト"), "*.txt"),
                (self.t("file.all", "すべて"), "*.*")]

    # ------------------------------------------------------------ ファイル
    def _confirm_discard(self) -> bool:
        if not self._dirty:
            return True
        r = messagebox.askyesnocancel(self.t("dlg.confirm", "確認"), self.t("dlg.save_changes", "変更を保存しますか?"))
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
        self._sync_ma_box()
        self._refresh_score_view()

    def ask_open(self):
        if not self._confirm_discard():
            return
        p = filedialog.askopenfilename(filetypes=self._filetypes())
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
        self._sync_ma_box()
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
        self._write_header(score_mod.BEATS_KEYS, f"beats: {val}")
        self._beats_applied = val
        self.align_text(auto=True)
        self._highlight_syntax()
        self._refresh_score_view()
        self._update_status(self.t("status.rebarred", "1小節 {n} 拍で区切り直しました", n=val))

    def _write_header(self, keys, new_line: str | None):
        """ヘッダの keys のいずれかの行を new_line に置き換える(なければ追加、None なら削除)。"""
        lines = self.text.get("1.0", "end-1c").split("\n")
        first_sec = next((i for i, ln in enumerate(lines) if score_mod.section_header_end(ln) is not None),
                         len(lines))
        key_re = re.compile(r"^\s*(" + "|".join(map(re.escape, keys)) + r")\s*[:：]", re.I)
        idx = next((i for i in range(first_sec) if key_re.match(lines[i])), None)
        if new_line is None:
            if idx is None:
                return
            del lines[idx]
        elif idx is not None:
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
        self._highlight_syntax()

    # ------------------------------------------------------------ 小節の間(ま)
    def _sync_ma_box(self):
        try:
            sc = score_mod.parse(self.text.get("1.0", "end-1c"))
        except score_mod.ScoreError:
            return
        on = sc.ma_beats > 0
        self.ma_on.set(on)
        if on:
            self.ma_len.set(_fmt_beats(sc.ma_beats))
        self._ma_applied = (on, self.ma_len.get())

    def _set_ma(self):
        """「間あり / 間なし」と間の長さをヘッダ ma: に書く(間なしなら行を消す)。"""
        txt = self.ma_len.get().strip().translate(str.maketrans("０１２３４５６７８９．／", "0123456789./"))
        try:
            length = Fraction(txt)
        except (ValueError, ZeroDivisionError):
            length = Fraction(0)
        if not 0 < length <= 16:
            self.ma_len.set(getattr(self, "_ma_applied", (False, "1"))[1])
            return
        state = (bool(self.ma_on.get()), _fmt_beats(length))
        if state == getattr(self, "_ma_applied", None):
            return
        self._write_header(score_mod.MA_KEYS, f"ma: {state[1]}" if state[0] else None)
        self._ma_applied = state
        self._update_status(self.t("status.ma_on", "小節の間(ま): {n} 拍(再生・書き出しに反映)", n=state[1])
                            if state[0] else self.t("status.ma_off", "小節の間(ま)なし(インテンポ)"))

    def save(self) -> bool:
        if self.path is None:
            p = filedialog.asksaveasfilename(defaultextension=".gaku", filetypes=self._filetypes())
            if not p:
                return False
            self.path = Path(p)
        self.align_text(auto=True)
        self.path.write_text(self.text.get("1.0", "end-1c") + "\n", encoding="utf-8")
        self._dirty = False
        self._update_title()
        self._update_status(self.t("status.saved", "保存しました: {path}", path=self.path))
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
            view.set_message(self.t("status.score_error", "譜面エラー: {err}", err=e))
            return
        view.set_score(sc)

    def _jump_to_event(self, ev):
        """楽譜表示で音をクリック → テキストの該当トークンにカーソルを置く(F6でそこから再生)。"""
        idx = f"{ev.line}.{ev.col}"
        self.text.mark_set(tk.INSERT, idx)
        self.text.tag_remove(tk.SEL, "1.0", tk.END)
        self.text.tag_add(tk.SEL, idx, f"{ev.line}.{ev.col_end}")
        self.text.see(idx)
        self._update_status(self.t("status.selected", "{line}行の「{sym}」を選択(F6 でここから再生)",
                                   line=ev.line, sym=ev.symbol))

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
            self._update_status(self.t("status.error", "エラー: {err}", err=e))
            messagebox.showerror(self.t("dlg.score_error", "譜面エラー"), str(e))
            return None
        if not sc.events:
            messagebox.showinfo(self.t("dlg.info", "情報"), self.t("dlg.no_notes", "音符がありません"))
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
        self._update_status(self.t("status.rendering", "レンダリング中…"))

        def prog(x):
            self.after(0, lambda: self.progress.configure(value=x * 100))

        def work():
            try:
                data = render.render(sc, mute, vols, rev, progress=prog)
                self.after(0, lambda: on_done(data, sc))
            except Exception as e:  # noqa: BLE001
                err = e
                self.after(0, lambda: messagebox.showerror(self.t("dlg.render_failed", "レンダリング失敗"), repr(err)))
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
                messagebox.showerror(self.t("dlg.play_error", "再生エラー"), str(e))
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
            msg = self.t("status.playing", "再生中 ({title} / {mode} / {bpm} BPM)",
                         title=sc.title or self.t("title.untitled", "無題"), mode=sc.mode, bpm=f"{sc.tempo:g}")
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
            self._update_status(self.t("status.finished", "再生終了"))
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
            self._update_status(self.t("status.exported", "書き出しました: {path}", path=p))

        self._render_async(sc, done)

    def on_close(self):
        if self._confirm_discard():
            self.stop()
            self.destroy()


class PluginDialog(tk.Toplevel):
    """プラグインの検索・インストール・有効/無効の切り替え・アンインストール。"""

    def __init__(self, app: App):
        super().__init__(app)
        self.app = app
        self.mgr = app.plugins
        self.catalog = self.mgr.bundled_catalog()
        self.geometry("760x440")
        self.transient(app)
        t = app.t
        self.title(t("pm.title", "プラグイン"))

        top = ttk.Frame(self, padding=(10, 10, 10, 4))
        top.pack(fill=tk.X)
        self.search_lbl = ttk.Label(top, text=t("pm.search", "検索"))
        self.search_lbl.pack(side=tk.LEFT)
        self.query = tk.StringVar()
        entry = ttk.Entry(top, textvariable=self.query, width=36)
        entry.pack(side=tk.LEFT, padx=6)
        entry.focus_set()
        self.query.trace_add("write", lambda *a: self.refresh_list())
        self.refresh_btn = ttk.Button(top, text=t("pm.refresh", "オンラインの一覧を読み込む"), command=self.load_online)
        self.refresh_btn.pack(side=tk.RIGHT)

        cols = ("name", "version", "status", "desc")
        self.tree = ttk.Treeview(self, columns=cols, show="headings", height=10, selectmode="browse")
        for c, (key, default, w) in zip(cols, (("pm.col.name", "名前", 150), ("pm.col.version", "版", 60),
                                               ("pm.col.status", "状態", 90),
                                               ("pm.col.desc", "説明", 420))):
            self.tree.heading(c, text=t(key, default))
            self.tree.column(c, width=w, anchor=tk.W, stretch=(c == "desc"))
        self.tree.pack(fill=tk.BOTH, expand=True, padx=10)
        self.tree.bind("<<TreeviewSelect>>", lambda e: self.update_buttons())
        self.tree.bind("<Double-1>", lambda e: self.toggle())

        btns = ttk.Frame(self, padding=10)
        btns.pack(fill=tk.X)
        self.install_btn = ttk.Button(btns, text=t("pm.install", "インストール"), command=self.install)
        self.toggle_btn = ttk.Button(btns, text=t("pm.enable", "有効にする"), command=self.toggle)
        self.remove_btn = ttk.Button(btns, text=t("pm.uninstall", "アンインストール"), command=self.uninstall)
        for b in (self.install_btn, self.toggle_btn, self.remove_btn):
            b.pack(side=tk.LEFT, padx=(0, 6))
        self.close_btn = ttk.Button(btns, text=t("pm.close", "閉じる"), command=self.destroy)
        self.close_btn.pack(side=tk.RIGHT)
        self.msg = tk.StringVar(value=t("pm.warn", "プラグインは Python のコードとして動きます。信頼できるものだけを入れてください。"))
        ttk.Label(self, textvariable=self.msg, foreground="#7a5a20", padding=(10, 0, 10, 10),
                  wraplength=720).pack(fill=tk.X)
        self.refresh_list()
        self.load_online()

    # ---------- 一覧
    def _rows(self):
        installed = {p.id: p for p in self.mgr.installed()}
        merged = self.mgr.merge_catalogs(self.catalog, list(installed.values()))
        return [(p, installed.get(p.id)) for p in merged]

    def refresh_list(self):
        t = self.app.t
        lang = "en" if self.app.t("pm.lang", "ja") == "en" else "ja"
        sel = self.selected_id()
        self.tree.delete(*self.tree.get_children())
        for info, inst in self._rows():
            if not info.matches(self.query.get()):
                continue
            if inst is None:
                status = t("pm.status.not_installed", "未インストール")
            elif info.id in self.mgr.active:
                status = t("pm.status.enabled", "有効")
            else:
                status = t("pm.status.disabled", "無効")
            version = inst.version if inst else info.version
            if inst and info.version != inst.version and info.source != "installed":
                version = f"{inst.version} → {info.version}"
            self.tree.insert("", tk.END, iid=info.id, values=(info.name, version, status, info.describe(lang)))
        if sel and self.tree.exists(sel):
            self.tree.selection_set(sel)
        self.update_buttons()

    def selected_id(self):
        s = self.tree.selection()
        return s[0] if s else None

    def _info(self, pid):
        return next((p for p, _ in self._rows() if p.id == pid), None)

    def update_buttons(self):
        t = self.app.t
        pid = self.selected_id()
        installed = pid is not None and self.mgr.installed_info(pid) is not None
        info = self._info(pid) if pid else None
        newer = installed and info and info.source != "installed" and info.version != self.mgr.installed_info(pid).version
        self.install_btn.configure(state=tk.NORMAL if pid and (not installed or newer) else tk.DISABLED,
                                   text=t("pm.update", "更新") if newer else t("pm.install", "インストール"))
        self.toggle_btn.configure(state=tk.NORMAL if installed else tk.DISABLED,
                                  text=t("pm.disable", "無効にする") if pid in self.mgr.active
                                  else t("pm.enable", "有効にする"))
        self.remove_btn.configure(state=tk.NORMAL if installed else tk.DISABLED)

    def load_online(self):
        self.refresh_btn.configure(state=tk.DISABLED)
        self.msg.set(self.app.t("pm.loading", "オンラインの一覧を読み込んでいます…"))

        def work():
            try:
                online = self.mgr.online_catalog()
                err = None
            except Exception as e:  # noqa: BLE001
                online, err = [], e
            try:
                self.after(0, lambda: self._online_done(online, err))
            except (RuntimeError, tk.TclError):
                pass   # 読み込み中にダイアログやアプリが閉じられた

        threading.Thread(target=work, daemon=True).start()

    def _online_done(self, online, err):
        if not self.winfo_exists():
            return
        self.refresh_btn.configure(state=tk.NORMAL)
        if err is None:
            self.catalog = self.mgr.merge_catalogs(self.mgr.bundled_catalog(), online)
            self.msg.set(self.app.t("pm.online_ok", "オンラインの一覧を読み込みました({n} 件)", n=len(online)))
        else:
            self.msg.set(self.app.t("pm.online_failed", "オンラインの一覧を読み込めませんでした(同梱の一覧を表示しています)"))
        self.refresh_list()

    # ---------- 操作
    def install(self):
        t = self.app.t
        info = self._info(self.selected_id())
        if info is None:
            return
        if not messagebox.askokcancel(t("pm.title", "プラグイン"),
                                      t("pm.confirm_install", "「{name}」をインストールしますか?\n"
                                        "プラグインは Python のコードとして動きます。", name=info.name), parent=self):
            return
        try:
            if info.source == "online":
                self.mgr.install_online(info)
            else:
                self.mgr.install_bundled(info.id)
            self.mgr.set_enabled(info.id, True)
            self._retitle()
            self.msg.set(self.app.t("pm.installed_ok", "「{name}」をインストールして有効にしました", name=info.name))
        except plugins.PluginError as e:
            messagebox.showerror(t("pm.title", "プラグイン"), str(e), parent=self)
        self.refresh_list()

    def toggle(self):
        pid = self.selected_id()
        if pid is None or self.mgr.installed_info(pid) is None:
            return
        try:
            self.mgr.set_enabled(pid, pid not in self.mgr.active)
        except plugins.PluginError as e:
            messagebox.showerror(self.app.t("pm.title", "プラグイン"), str(e), parent=self)
        self._retitle()
        self.refresh_list()

    def uninstall(self):
        t = self.app.t
        pid = self.selected_id()
        info = pid and self.mgr.installed_info(pid)
        if not info:
            return
        if messagebox.askokcancel(t("pm.title", "プラグイン"),
                                  t("pm.confirm_uninstall", "「{name}」をアンインストールしますか?", name=info.name),
                                  parent=self):
            self.mgr.uninstall(pid)
            self._retitle()
            self.refresh_list()

    def _retitle(self):
        """このダイアログ自身の文言も、言語プラグインの切り替えに合わせて付け直す。"""
        t = self.app.t
        self.title(t("pm.title", "プラグイン"))
        self.search_lbl.configure(text=t("pm.search", "検索"))
        self.close_btn.configure(text=t("pm.close", "閉じる"))
        self.msg.set(t("pm.warn", "プラグインは Python のコードとして動きます。信頼できるものだけを入れてください。"))
        self.refresh_btn.configure(text=t("pm.refresh", "オンラインの一覧を読み込む"))
        for c, key, default in (("name", "pm.col.name", "名前"), ("version", "pm.col.version", "版"),
                                ("status", "pm.col.status", "状態"), ("desc", "pm.col.desc", "説明")):
            self.tree.heading(c, text=t(key, default))
        self.remove_btn.configure(text=t("pm.uninstall", "アンインストール"))


_HELP = {
    "sho": "合竹名(乞 一 工 凢 乙 下 十 美 行 比 / 乙美 乙言 凢美 凢言)。「単千」のように単を付けると一本だけ。双調では「十」が5音の十になる。",
    "hichiriki": "舌 五 工 凢 六 四 一 丄 丁(低い順, G4〜A5)。ムは現行曲では使わない。音頭に塩梅(下からのすくい上げ)が付く。調子ごとにメリを付ける(平調は舌・丄を F# に、凢は平調・盤渉調・太食調で C#5、双調・壱越調・黄鐘調でメリ凢の C5)。詳しくは紹介サイトの調子ごとの対応表を参照。音高は tunings.json の hichiriki で上書き可。",
    "ryuteki": "和(低)の譜字。延ばしは「-」(1拍)、「-:2」で2拍。「責六」または「六'」で責(1オクターブ上)、「干,」で1オクターブ下。干は六の上(E)で鳴る。〒→干 などの異体字も可。調子ごとにメリ・ハカリを付ける(丅は双調・壱越調・黄鐘調で C6、ほかは C#6)。詳しくは紹介サイトの調子ごとの対応表を参照。",
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
