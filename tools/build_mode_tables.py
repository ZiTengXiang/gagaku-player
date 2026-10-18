"""調子ごとの音階と各楽器の譜字の対応表を、アプリ自身の音高データから作る。

    python tools/build_mode_tables.py

六つの調子それぞれについて docs/<調子>/index.html(日本語)と docs/en/<調子>/index.html(英語)を書き出す。
音高と奏法は gagaku/instruments.py と gagaku/tunings.json の値(アプリが実際に鳴らす高さ)を使う。
"""

from __future__ import annotations

import html
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from gagaku import __version__  # noqa: E402
from gagaku import instruments as I  # noqa: E402

BASE = "https://zitengxiang.github.io/gagaku-player/"
PC = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
JUNIRITSU = {"D": "壱越", "D#": "断金", "E": "平調", "F": "勝絶", "F#": "下無", "G": "双調",
             "G#": "鳧鐘", "A": "黄鐘", "A#": "鸞鏡", "B": "盤渉", "C": "神仙", "C#": "上無"}
JUNIRITSU_EN = {"D": "Ichikotsu", "D#": "Tangin", "E": "Hyōjō", "F": "Shōzetsu", "F#": "Shimomu",
                "G": "Sōjō", "G#": "Fushō", "A": "Ōshiki", "A#": "Rankei", "B": "Banshiki",
                "C": "Shinsen", "C#": "Kamimu"}

# 調子: (スラッグ, 英語名, 主音, 旋法)
MODES = {
    "壱越調": ("ichikotsu", "Ichikotsu-chō", "D", "呂"),
    "平調": ("hyojo", "Hyōjō", "E", "律"),
    "双調": ("sojo", "Sōjō", "G", "呂"),
    "黄鐘調": ("oshiki", "Ōshiki-chō", "A", "律"),
    "盤渉調": ("banshiki", "Banshiki-chō", "B", "律"),
    "太食調": ("taishiki", "Taishiki-chō", "E", "呂"),
}
# 七声(主音からの半音数)。五声は 宮・商・角・徴・羽
SCALES = {
    "律": [("宮", "kyū", 0), ("商", "shō", 2), ("嬰商", "ei-shō", 3), ("角", "kaku", 5),
           ("徴", "chi", 7), ("羽", "u", 9), ("嬰羽", "ei-u", 10)],
    "呂": [("宮", "kyū", 0), ("商", "shō", 2), ("角", "kaku", 4), ("嬰角", "ei-kaku", 5),
           ("徴", "chi", 7), ("羽", "u", 9), ("嬰羽", "ei-u", 10)],
}
CORE = {"宮", "商", "角", "徴", "羽"}
INSTS = ["sho", "hichiriki", "ryuteki", "biwa", "koto"]
NAMES = {"ja": {"sho": "笙", "hichiriki": "篳篥", "ryuteki": "竜笛", "biwa": "琵琶", "koto": "筝"},
         "en": {"sho": "Shō 笙", "hichiriki": "Hichiriki 篳篥", "ryuteki": "Ryūteki 竜笛",
                "biwa": "Biwa 琵琶", "koto": "Koto 筝"}}


def split(note: str) -> tuple[str, int]:
    m = re.match(r"^([A-G]#?)(-?\d)$", note)
    return m.group(1), int(m.group(2))


def midi(note: str) -> int:
    pc, octv = split(note)
    return (octv + 1) * 12 + PC.index(pc)


def degrees(mode: str):
    """[(音名, 声の名(日), 声の名(英), 五声か)] を主音から。"""
    _, _, tonic, kind = MODES[mode]
    t = PC.index(tonic)
    return [(PC[(t + off) % 12], ja, en, ja in CORE) for ja, en, off in SCALES[kind]]


def collect(mode: str) -> dict[str, list[tuple[str, str]]]:
    """楽器ごとに (譜字, 音名) の一覧(その調子でアプリが鳴らす高さ)。"""
    out: dict[str, list[tuple[str, str]]] = {}
    out["sho"] = sorted(I.SHO_PIPES.items(), key=lambda kv: midi(kv[1]))
    h = I.INSTRUMENTS["hichiriki"]
    out["hichiriki"] = [(s, h._note_name(s, mode)) for s in h.palette if s != "ム"]
    r = I.INSTRUMENTS["ryuteki"]
    ry = [(s, r._note_name(s, mode)) for s in I.RYUTEKI]
    ry += [("干,", I.shift_note(r._note_name("干", mode), -1))]
    ry += [("責" + s, I.shift_note(r._note_name(s, mode), 1)) for s in I.RYUTEKI]
    out["ryuteki"] = sorted(ry, key=lambda kv: midi(kv[1]))
    biwa = I._TUNINGS["biwa"][mode]
    out["biwa"] = sorted(((I.BIWA_GRID[s][f], biwa[s][f]) for s in range(4) for f in range(5)),
                         key=lambda kv: midi(kv[1]))
    out["koto"] = list(zip(I.KOTO_STRINGS, I._TUNINGS["koto"][mode]))
    return out


# ------------------------------------------------------------------ 奏法の説明

def _join(items, lang):
    items = sorted(items)
    return "・".join(items) if lang == "ja" else ", ".join(items)


def techniques(mode: str, lang: str) -> list[tuple[str, str, str, str]]:
    """(楽器, 譜字, 音高, 奏法の説明) の一覧を、調子ごとの設定から組み立てる。"""
    rows: dict[tuple[str, str], list[str]] = {}
    pitch: dict[tuple[str, str], str] = {}
    ja = lang == "ja"
    add = lambda inst, s, text: rows.setdefault((inst, s), []).append(text)  # noqa: E731

    # 篳篥
    h = I.INSTRUMENTS["hichiriki"]
    hm = I.HICHIRIKI_MERI.get(mode, {})
    for s in h.palette:
        if s == "ム":
            continue
        std, now = I.HICHIRIKI[s], h._note_name(s, mode)
        if std != now:
            pitch[("hichiriki", s)] = f"{std} → {now}"
            if s == "凢":
                add("hichiriki", s, "音階の上無(C#)に合わせる。" if ja else "Fitted to the mode's C# (Kamimu).")
            else:
                add("hichiriki", s, "メリで半音下げる。" if ja else "Lowered a semitone (meri).")
    for s, c in hm.get("dip", {}).items():
        if s == "凢" and h._note_name("凢", mode) == "C5":
            add("hichiriki", s, f"メリ凢: くわえを浅く口元を緩め、C(神仙)で吹く。音頭で約{c}セント沈めてから立ち上げる。" if ja
                else f"Meri-han: a shallow, relaxed embouchure gives C (Shinsen); the onset dips about {c} cents.")
        else:
            add("hichiriki", s, f"音頭で約{c}セント沈めてから立ち上げる。" if ja
                else f"The onset dips about {c} cents before rising.")
    for s, (partners, c) in hm.get("sink", {}).items():
        add("hichiriki", s, f"{_join(partners, lang)}と行き来する境目で、約{c}セントなめらかに沈み込む。" if ja
            else f"Sinks about {c} cents where it meets {_join(partners, lang)}.")
    for s, (partners, c) in hm.get("land", {}).items():
        add("hichiriki", s, f"{_join(partners, lang)}から下りて着地するとき、境目で約{c}セント沈み込んでつなぐ。" if ja
            else f"When the line descends to it from {_join(partners, lang)}, it sinks about {c} cents at the join.")
    for s, c in hm.get("detune", {}).items():
        if c > 0 and s in ("舌", "丄"):
            add("hichiriki", s, f"メリをかけず、約{c}セント上向かせる(カリ気味)。" if ja
                else f"No meri; bent about {c} cents upward (kari).")
        elif c > 0:
            add("hichiriki", s, f"約{c}セント高めに保つ。" if ja else f"Held about {c} cents sharp.")
        else:
            add("hichiriki", s, f"約{-c}セント低めに保つ。" if ja else f"Held about {-c} cents flat.")

    # 竜笛
    r = I.INSTRUMENTS["ryuteki"]
    rm = I.RYUTEKI_MERI.get(mode, {})
    for s in I.RYUTEKI:
        std, now = I.RYUTEKI[s], r._note_name(s, mode)
        if std != now:
            pitch[("ryuteki", s)] = f"{std} → {now}"
            add("ryuteki", s, "ハカリ(指孔を半分塞ぐ)と強いメリで半音下げる(責も同じ)。" if ja
                else "Lowered a semitone with hakari (half-covering the hole) and strong meri (also in 責).")
    for s, c in rm.get("settle", {}).items():
        add("ryuteki", s, f"高めに当たりやすいのを、顎を引いて約{c}セント抑え込み、正しい高さに合わせる。" if ja
            else f"Tends to start sharp; pulled down about {c} cents to pitch.")
    for s, c in rm.get("settle_low", {}).items():
        add("ryuteki", s, f"和(低音域)では、約{c}セント上から角度を変えてなめらかに着地する。" if ja
            else f"In the low register, lands smoothly from about {c} cents above.")
    for s, c in rm.get("detune", {}).items():
        add("ryuteki", s, f"顎を引いて、約{-c}セント低めに保つ。" if ja and c < 0 else
            (f"Held about {-c} cents flat." if c < 0 else f"Held about {c} cents sharp."))
    for s, c in rm.get("passing_dip", {}).items():
        add("ryuteki", s, f"経過音(前後が別の音で1拍以内)のとき、メルで約{c}セント落とす。" if ja
            else f"As a passing note (different notes on both sides, one beat or less), dips about {c} cents (meru).")
    for s, c in rm.get("fall", {}).items():
        sec = rm.get("fall_min_sec")
        add("ryuteki", s, f"{sec}秒以上伸ばすと、顎を引いて約{c}セント落とす(途中は階段状、フレーズの終わりは滑り台状)。" if ja
            else f"Held for {sec} s or more, falls about {c} cents: in steps mid-phrase, sliding at the end of a phrase.")
    fb = rm.get("fall_before", {})
    targets: dict[tuple, list[str]] = {}
    for s, (partners, c, *opt) in fb.items():
        targets.setdefault((tuple(sorted(partners)), c, "down" in opt), []).append(s)
    for (partners, c, down), srcs in targets.items():
        key = srcs[0] if len(srcs) == 1 else ("・" if ja else ", ").join(srcs)
        if ja:
            text = (f"{'上から' if down else ''}{_join(partners, lang)}へ移る手前で、急に顎を引いて約{c}セント階段状に落とす。")
        else:
            text = f"Just before moving {'down ' if down else ''}to {_join(partners, lang)}, falls about {c} cents in steps."
        add("ryuteki", key, text)

    inst_name = {"hichiriki": "篳篥" if ja else "Hichiriki", "ryuteki": "竜笛" if ja else "Ryūteki"}
    order = {"hichiriki": 0, "ryuteki": 1}
    out = []
    pal = {"hichiriki": I.INSTRUMENTS["hichiriki"].palette, "ryuteki": list(I.RYUTEKI)}
    for (inst, s), texts in sorted(rows.items(), key=lambda kv: (order[kv[0][0]],
                                                               pal[kv[0][0]].index(re.split("・|, ", kv[0][1])[0]))):
        table = I.HICHIRIKI if inst == "hichiriki" else I.RYUTEKI
        now = (lambda b: h._note_name(b, mode)) if inst == "hichiriki" else (lambda b: r._note_name(b, mode))
        bases = re.split("・|, ", s)
        same = all(table[b] == now(b) for b in bases)
        p = pitch.get((inst, s)) or (("、" if ja else ", ").join(now(b) for b in bases)
                                     + (("(変えない)" if ja else " (unchanged)") if same else ""))
        out.append((inst_name[inst], s, p, " ".join(texts)))
    return out


MERI_INST = {"hichiriki", "ryuteki"}


def meri_symbols(mode: str) -> set[tuple[str, str]]:
    marks = set()
    for inst, meri in (("hichiriki", I.HICHIRIKI_MERI.get(mode, {})), ("ryuteki", I.RYUTEKI_MERI.get(mode, {}))):
        for key, val in meri.items():
            if isinstance(val, dict):
                for s in val:
                    marks.add((inst, s))
    for s in I.RYUTEKI:
        if I.INSTRUMENTS["ryuteki"]._note_name(s, mode) != I.RYUTEKI[s]:
            marks.add(("ryuteki", s))
    for s in I.HICHIRIKI:
        if I.INSTRUMENTS["hichiriki"]._note_name(s, mode) != I.HICHIRIKI[s]:
            marks.add(("hichiriki", s))
    # 竜笛は責・低い干にも同じ奏法が付く
    for inst, s in list(marks):
        if inst == "ryuteki":
            marks.add((inst, "責" + s))
            if s == "干":
                marks.add((inst, "干,"))
    return marks


# ------------------------------------------------------------------ 表

def biwa_pos(sym: str, lang: str) -> str:
    s, f = I.BIWA_POS[sym]
    if lang == "ja":
        return f"{s + 1}弦{'開放' if f == 0 else f'第{f}柱'}"
    return f"str. {s + 1}, {'open' if f == 0 else f'fret {f}'}"


def cell(inst, items, lang, marks) -> str:
    if not items:
        return '<td class="empty">—</td>'
    parts = []
    for sym, note in items:
        extra = f'<span class="pos">{biwa_pos(sym, lang)}</span>' if inst == "biwa" else ""
        mark = ' class="meri"' if (inst, sym) in marks else ""
        parts.append(f'<span class="ch"><b{mark}>{html.escape(sym)}</b><small>{note}</small>{extra}</span>')
    return "<td>" + "".join(parts) + "</td>"


def scale_table(mode: str, lang: str) -> str:
    data, marks = collect(mode), meri_symbols(mode)
    degs = degrees(mode)
    in_scale = [d[0] for d in degs]
    t = PC.index(MODES[mode][2])
    rest = [PC[(t + k) % 12] for k in range(12)]
    rest = [pc for pc in rest if pc not in in_scale
            and any(split(n)[0] == pc for v in data.values() for _, n in v)]
    head = ("<tr><th>音名</th><th>十二律</th><th>この調子での役割</th>" if lang == "ja"
            else "<tr><th>Pitch</th><th>Jūniritsu</th><th>Role in this mode</th>")
    head += "".join(f"<th>{NAMES[lang][i]}</th>" for i in INSTS) + "</tr>"
    body = []
    for pc, dja, den, core in [*degs, *[(pc, None, None, False) for pc in rest]]:
        if dja:
            role = (dja + ("(五声)" if core else "")) if lang == "ja" else (den + (" (core)" if core else ""))
            if dja == "宮":
                role += "・主音" if lang == "ja" else ", tonic"
            cls = "core" if core else "aux"
        else:
            role, cls = ("音階外" if lang == "ja" else "outside the scale"), "out"
        rits = JUNIRITSU[pc] if lang == "ja" else f"{JUNIRITSU_EN[pc]} {JUNIRITSU[pc]}"
        tds = "".join(cell(i, [(s, n) for s, n in data[i] if split(n)[0] == pc], lang, marks) for i in INSTS)
        body.append(f'<tr class="{cls}"><th class="pc">{pc}</th><td>{rits}</td><td>{role}</td>{tds}</tr>')
    return f'<div class="scroll"><table class="scale"><thead>{head}</thead><tbody>{"".join(body)}</tbody></table></div>'


def meri_table(mode: str, lang: str) -> str:
    rows = techniques(mode, lang)
    if lang == "ja":
        head = "<tr><th>楽器</th><th>譜字</th><th>音高(正律 → この調子)</th><th>この調子での奏法(このアプリでの再現)</th></tr>"
    else:
        head = "<tr><th>Instrument</th><th>Character</th><th>Pitch (standard → this mode)</th><th>Technique (as played by the app)</th></tr>"
    have = {r[0] for r in rows}
    for inst in (("篳篥", "竜笛") if lang == "ja" else ("Hichiriki", "Ryūteki")):
        if inst not in have:
            rows.append((inst, "—", "—", "この調子では特別な奏法を付けず、正律のまま吹く。" if lang == "ja"
                         else "No special technique in this mode; played at standard pitch."))
    body = "".join(f"<tr><td>{a}</td><td class='ch1'>{b}</td><td>{c}</td><td>{d}</td></tr>" for a, b, c, d in rows)
    return f'<div class="scroll"><table class="meri-t"><thead>{head}</thead><tbody>{body}</tbody></table></div>'


# ------------------------------------------------------------------ ページ

def mode_nav(current: str, lang: str, prefix: str) -> str:
    items = []
    for m, (slug, en, *_ ) in MODES.items():
        label = m if lang == "ja" else en
        if m == current:
            items.append(f'<li class="here">{label}</li>')
        else:
            items.append(f'<li><a href="{prefix}{slug}/">{label}</a></li>')
    return '<ul class="modes">' + "".join(items) + "</ul>"


EXTRA_CSS = """
  .scroll { overflow-x: auto; -webkit-overflow-scrolling: touch; border: 1px solid var(--line); border-radius: 12px; background: var(--paper); }
  table.scale, table.meri-t { min-width: 760px; }
  table.scale th, table.scale td { white-space: nowrap; }
  table.scale thead th { color: var(--ink); font-weight: bold; background: var(--code); }
  table.scale th.pc { font-weight: bold; color: var(--ink); font-size: 1.05rem; }
  table.scale tr.core th.pc { color: var(--accent); }
  table.scale tr.out { color: var(--muted); }
  table.scale td.empty { color: var(--line); }
  .ch { display: inline-flex; align-items: baseline; gap: 3px; margin: 0 10px 2px 0; }
  .ch b { font-family: "BIZ UDMincho", "Hiragino Mincho ProN", "Yu Mincho", "Noto Serif JP", serif; font-size: 1.15rem; font-weight: normal; }
  .ch small { color: var(--muted); }
  .ch .pos { color: var(--muted); font-size: .8rem; }
  b.meri, .ch b.meri { color: var(--accent); }
  table.meri-t thead th { color: var(--ink); font-weight: bold; background: var(--code); }
  table.meri-t th, table.meri-t td:nth-child(-n+3) { white-space: nowrap; }
  table.meri-t td.ch1 { font-family: "BIZ UDMincho", "Yu Mincho", serif; font-size: 1.1rem; white-space: nowrap; }
  header.hero.small { padding: 40px 0 28px; }
  .hero.small h1 { font-size: clamp(1.6rem, 4vw, 2.2rem); }
  ul.modes { list-style: none; padding: 0; margin: 14px 0 0; display: flex; flex-wrap: wrap; gap: 8px; }
  ul.modes li { border: 1px solid var(--gold); border-radius: 8px; background: var(--paper); font-family: "BIZ UDMincho", "Yu Mincho", serif; }
  ul.modes li a { display: block; padding: 2px 12px; text-decoration: none; }
  ul.modes li.here { padding: 2px 12px; background: var(--accent); border-color: var(--accent); color: #fff; }
"""


def texts(mode: str, lang: str) -> dict:
    slug, en, tonic, kind = MODES[mode]
    degs = degrees(mode)
    core = [f"{d[1]} {d[0]}" for d in degs if d[3]]
    aux = [f"{d[1]} {d[0]}" for d in degs if not d[3]]
    core_en = [f"{d[2]} {d[0]}" for d in degs if d[3]]
    aux_en = [f"{d[2]} {d[0]}" for d in degs if not d[3]]
    kind_en = "ryo" if kind == "呂" else "ritsu"
    if lang == "ja":
        return {
            "path": f"{slug}/", "other": f"en/{slug}/", "other_label": "English version",
            "title": f"{mode}の音階と譜字の対応表|雅楽譜プレイヤー",
            "desc": f"雅楽の{mode}({tonic} を主音とする{kind}旋)の音階と、笙・篳篥・竜笛・琵琶・筝の譜字・音高の対応表。篳篥・竜笛の{mode}でのメリ・ハカリも一覧にしています。",
            "h1": f"{mode}の音階と譜字の対応表",
            "lead": f"{mode}は、{tonic}(十二律の{JUNIRITSU[tonic]})を主音(宮)とする{kind}旋の調子です。下の表は、雅楽譜プレイヤーが{mode}で鳴らす各楽器の譜字と音高を、音階の音ごとにまとめたものです。",
            "h_def": f"{mode}の音階",
            "def": f"{mode}は{kind}旋で、五声は {'・'.join(core)}。これに{'・'.join(aux)}を加えた七声で旋律が動きます。主音にあたる譜字は、メリを付けずに正律で安定して吹きます。",
            "h_scale": "音階と各楽器の譜字",
            "scale_note": f"音名は国際式(A4 = 430 Hz を基準)。<b class='meri'>赤字</b>の譜字は、{mode}でメリ・ハカリなどの例外的な奏法が付くもの(下の表を参照)。琵琶は弦と柱、筝は弦の名前です。琵琶・筝の調弦は、出典が見つからなかったため主音と音階から組んだ暫定値です。笙は合竹ではなく、竹(簧)1本ずつの音高です。",
            "h_meri": f"{mode}の例外的な奏法(メリ・ハカリ)",
            "meri_note": "セントは半音の 1/100。値はアプリの既定値で、<code>gagaku/instruments.py</code> の <code>HICHIRIKI_MERI</code>・<code>RYUTEKI_MERI</code> と <code>gagaku/tunings.json</code> で変えられます。",
            "nav": "ほかの調子", "back": "← 雅楽譜プレイヤーのトップへ", "back_href": "../",
            "gen": f"この表は雅楽譜プレイヤー {__version__} の音高データから自動で作っています(<code>tools/build_mode_tables.py</code>)。",
        }
    return {
        "path": f"en/{slug}/", "other": f"{slug}/", "other_label": "日本語版",
        "title": f"{en} scale and notation chart | Gagaku Score Player",
        "desc": f"The gagaku mode {en} ({mode}, a {kind_en} scale on {tonic}) and the matching notation characters and pitches for shō, hichiriki, ryūteki, biwa and koto, including the hichiriki and ryūteki meri and hakari techniques.",
        "h1": f"{en} scale and notation chart",
        "lead": f"{en} ({mode}) is a gagaku mode in the {kind_en} scale with {tonic} (the pitch {JUNIRITSU_EN[tonic]} in the jūniritsu system) as its tonic. The chart lists, for each pitch, the characters and pitches that Gagaku Score Player plays in {en}.",
        "h_def": f"The {en} scale",
        "def": f"{en} uses the {kind_en} scale. Its five core degrees are {', '.join(core_en)}, with {' and '.join(aux_en)} as the two additional degrees. The characters on the tonic are played steadily at standard pitch, without meri.",
        "h_scale": "Scale and characters by instrument",
        "scale_note": f"Pitches use international names (A4 = 430 Hz). Characters in <b class='meri'>red</b> get a special technique such as meri or hakari in {en} (see the next table). Biwa entries show string and fret; koto entries are string names. The biwa and koto tunings are provisional, built from the mode's tonic and scale because no source was found. Shō pitches are for single pipes, not chords.",
        "h_meri": f"Special techniques in {en} (meri and hakari)",
        "meri_note": "A cent is 1/100 of a semitone. The values are the app's defaults; change them in <code>HICHIRIKI_MERI</code> and <code>RYUTEKI_MERI</code> in <code>gagaku/instruments.py</code> and in <code>gagaku/tunings.json</code>.",
        "nav": "Other modes", "back": "← Back to Gagaku Score Player", "back_href": "../",
        "gen": f"This chart is generated from the pitch data of Gagaku Score Player {__version__} (<code>tools/build_mode_tables.py</code>).",
    }


def page(mode: str, lang: str) -> str:
    t = texts(mode, lang)
    slug = MODES[mode][0]
    src = (ROOT / "docs" / "index.html").read_text(encoding="utf-8")
    style = re.search(r"<style>(.*?)</style>", src, re.S).group(1)
    url, alt = BASE + t["path"], BASE + t["other"]
    ja_url, en_url = BASE + f"{slug}/", BASE + f"en/{slug}/"
    icon = "../images/icon.png" if lang == "ja" else "../../images/icon.png"
    nav = mode_nav(mode, lang, "../")
    return f"""<!doctype html>
<html lang="{lang}">
<head>
<meta charset="utf-8">
<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-YRQ8M99RN2"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){{dataLayer.push(arguments);}}
  gtag('js', new Date());

  gtag('config', 'G-YRQ8M99RN2');
</script>
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{t['title']}</title>
<meta name="description" content="{t['desc']}">
<link rel="canonical" href="{url}">
<link rel="alternate" hreflang="ja" href="{ja_url}">
<link rel="alternate" hreflang="en" href="{en_url}">
<link rel="alternate" hreflang="x-default" href="{en_url}">
<meta property="og:title" content="{t['h1']}">
<meta property="og:description" content="{t['desc']}">
<meta property="og:type" content="article">
<meta property="og:url" content="{url}">
<meta property="og:image" content="{BASE}images/score.png">
<link rel="icon" href="{icon}">
<style>{style}{EXTRA_CSS}</style>
</head>
<body>

<header class="hero small">
  <div class="wrap">
    <p class="lang">{t['other_label']}: <a href="{alt}" hreflang="{'en' if lang == 'ja' else 'ja'}">{alt}</a></p>
    <h1>{t['h1']}</h1>
    <p class="tag">{t['lead']}</p>
    <p class="sub"><a href="{t['back_href']}">{t['back']}</a></p>
    {nav}
  </div>
</header>

<main class="wrap">

  <section>
    <h2>{t['h_def']}</h2>
    <p>{t['def']}</p>
  </section>

  <section id="scale">
    <h2>{t['h_scale']}</h2>
    {scale_table(mode, lang)}
    <p class="small-note">{t['scale_note']}</p>
  </section>

  <section id="meri">
    <h2>{t['h_meri']}</h2>
    {meri_table(mode, lang)}
    <p class="small-note">{t['meri_note']}</p>
  </section>

  <section>
    <h2>{t['nav']}</h2>
    {nav}
  </section>

</main>

<footer>
  <div class="wrap">
    <p>{t['gen']}</p>
    <a href="{t['back_href']}">{t['back']}</a> — <a href="https://github.com/ZiTengXiang/gagaku-player">github.com/ZiTengXiang/gagaku-player</a>
  </div>
</footer>

</body>
</html>
"""


def outputs():
    """[(書き出し先, 調子, 言語)]"""
    out = []
    for mode, (slug, *_ ) in MODES.items():
        out.append((ROOT / "docs" / slug / "index.html", mode, "ja"))
        out.append((ROOT / "docs" / "en" / slug / "index.html", mode, "en"))
    return out


def main():
    for path, mode, lang in outputs():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(page(mode, lang), encoding="utf-8", newline="\n")
        print("wrote", path.relative_to(ROOT))


if __name__ == "__main__":
    main()
