"""平調の音階と各楽器の譜字の対応表を、アプリ自身の音高データから作る。

    python tools/build_hyojo_table.py

docs/hyojo/index.html(日本語)と docs/en/hyojo/index.html(英語)を書き出す。
音高は gagaku/instruments.py と gagaku/tunings.json の値(アプリが実際に鳴らす高さ)を使う。
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

MODE = "平調"
BASE = "https://zitengxiang.github.io/gagaku-player/"
PC = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
# 十二律(壱越 = D)
JUNIRITSU = {"D": "壱越", "D#": "断金", "E": "平調", "F": "勝絶", "F#": "下無", "G": "双調",
             "G#": "鳧鐘", "A": "黄鐘", "A#": "鸞鏡", "B": "盤渉", "C": "神仙", "C#": "上無"}
JUNIRITSU_EN = {"D": "Ichikotsu", "D#": "Tangin", "E": "Hyōjō", "F": "Shōzetsu", "F#": "Shimomu",
                "G": "Sōjō", "G#": "Fushō", "A": "Ōshiki", "A#": "Rankei", "B": "Banshiki",
                "C": "Shinsen", "C#": "Kamimu"}
# 平調(E を宮とする律旋)の七声
DEGREES = {"E": "宮", "F#": "商", "G": "嬰商", "A": "角", "B": "徴", "C#": "羽", "D": "嬰羽"}
DEGREES_EN = {"E": "kyū (tonic)", "F#": "shō", "G": "ei-shō", "A": "kaku", "B": "chi", "C#": "u",
              "D": "ei-u"}
CORE = {"E", "F#", "A", "B", "C#"}   # 五声
ORDER = ["E", "F#", "G", "A", "B", "C#", "D"]   # 平調の音階を宮から


def split(note: str) -> tuple[str, int]:
    m = re.match(r"^([A-G]#?)(-?\d)$", note)
    return m.group(1), int(m.group(2))


def midi(note: str) -> int:
    pc, octv = split(note)
    return (octv + 1) * 12 + PC.index(pc)


def collect() -> dict[str, list[tuple[str, str]]]:
    """楽器ごとに (譜字, 音名) の一覧。"""
    out: dict[str, list[tuple[str, str]]] = {}
    out["sho"] = sorted(I.SHO_PIPES.items(), key=lambda kv: midi(kv[1]))
    h = I.INSTRUMENTS["hichiriki"]
    out["hichiriki"] = [(s, h._note_name(s, MODE)) for s in h.palette if s != "ム"]
    ry = [(s, n) for s, n in I.RYUTEKI.items()]
    ry += [("干,", I.shift_note(I.RYUTEKI["干"], -1))]
    ry += [("責" + s, I.shift_note(n, 1)) for s, n in I.RYUTEKI.items()]
    out["ryuteki"] = sorted(ry, key=lambda kv: midi(kv[1]))
    biwa = I._TUNINGS["biwa"][MODE]
    out["biwa"] = sorted(((I.BIWA_GRID[s][f], biwa[s][f]) for s in range(4) for f in range(5)),
                         key=lambda kv: midi(kv[1]))
    koto = I._TUNINGS["koto"][MODE]
    out["koto"] = list(zip(I.KOTO_STRINGS, koto))
    return out


INSTS = ["sho", "hichiriki", "ryuteki", "biwa", "koto"]
NAMES = {"ja": {"sho": "笙", "hichiriki": "篳篥", "ryuteki": "竜笛", "biwa": "琵琶", "koto": "筝"},
         "en": {"sho": "Shō 笙", "hichiriki": "Hichiriki 篳篥", "ryuteki": "Ryūteki 竜笛",
                "biwa": "Biwa 琵琶", "koto": "Koto 筝"}}


def biwa_pos(sym: str, lang: str) -> str:
    s, f = I.BIWA_POS[sym]
    if lang == "ja":
        return f"{s + 1}弦{'開放' if f == 0 else f'第{f}柱'}"
    return f"str. {s + 1}, {'open' if f == 0 else f'fret {f}'}"


def cell(inst: str, items: list[tuple[str, str]], lang: str) -> str:
    if not items:
        return '<td class="empty">—</td>'
    parts = []
    for sym, note in items:
        extra = ""
        if inst == "biwa":
            extra = f'<span class="pos">{biwa_pos(sym, lang)}</span>'
        mark = ' class="meri"' if (inst, sym) in MERI_MARKS else ""
        parts.append(f'<span class="ch"><b{mark}>{html.escape(sym)}</b><small>{note}</small>{extra}</span>')
    return "<td>" + "".join(parts) + "</td>"


MERI_MARKS = {("hichiriki", "舌"), ("hichiriki", "丄"), ("hichiriki", "凢"), ("hichiriki", "四"),
              ("hichiriki", "六"), ("ryuteki", "五"), ("ryuteki", "責五"), ("ryuteki", "丅"),
              ("ryuteki", "責丅"), ("ryuteki", "干"), ("ryuteki", "干,"), ("ryuteki", "六"),
              ("ryuteki", "責六"), ("ryuteki", "夕"), ("ryuteki", "責夕")}


def scale_table(data, lang: str) -> str:
    rows_pc = ORDER + [pc for pc in PC[4:] + PC[:4] if pc not in ORDER
                       and any(split(n)[0] == pc for v in data.values() for _, n in v)]
    head = ("<tr><th>音名</th><th>十二律</th><th>平調での役割</th>" if lang == "ja"
            else "<tr><th>Pitch</th><th>Jūniritsu</th><th>Role in Hyōjō</th>")
    head += "".join(f"<th>{NAMES[lang][i]}</th>" for i in INSTS) + "</tr>"
    body = []
    for pc in rows_pc:
        if pc in ORDER:
            role = DEGREES[pc] if lang == "ja" else DEGREES_EN[pc]
            role += ("(五声)" if lang == "ja" else " (core)") if pc in CORE else ""
            cls = "core" if pc in CORE else "aux"
        else:
            role = "音階外" if lang == "ja" else "outside the scale"
            cls = "out"
        rits = JUNIRITSU[pc] if lang == "ja" else f"{JUNIRITSU_EN[pc]} {JUNIRITSU[pc]}"
        tds = "".join(cell(i, [(s, n) for s, n in data[i] if split(n)[0] == pc], lang) for i in INSTS)
        body.append(f'<tr class="{cls}"><th class="pc">{pc}</th><td>{rits}</td><td>{role}</td>{tds}</tr>')
    return f'<div class="scroll"><table class="scale"><thead>{head}</thead><tbody>{"".join(body)}</tbody></table></div>'


def meri_table(lang: str) -> str:
    hm, rm = I.HICHIRIKI_MERI[MODE], I.RYUTEKI_MERI[MODE]
    hn = lambda s: I.HICHIRIKI[s]          # noqa: E731
    h = I.INSTRUMENTS["hichiriki"]
    if lang == "ja":
        rows = [
            ("篳篥", "舌", f"{hn('舌')} → {h._note_name('舌', MODE)}(下無)",
             f"メリで半音下げる。音頭は F(勝絶)近くまで約{hm['dip']['舌']}セント沈めてから立ち上げる。"),
            ("篳篥", "丄", f"{hn('丄')} → {h._note_name('丄', MODE)}(下無)",
             f"舌の1オクターブ上。同じくメリで下げ、音頭で約{hm['dip']['丄']}セント沈める。"),
            ("篳篥", "凢", f"{hn('凢')} → {h._note_name('凢', MODE)}(上無)",
             f"メリ凢。平調の音階の上無に合わせ、音頭で口元を緩めて約{hm['dip']['凢']}セント沈める。"),
            ("篳篥", "四", f"{hn('四')}(変えない)",
             f"旋律のつなぎや塩梅の始まりで、約{hm['dip']['四']}セント落とし込んでから立ち上げる。"),
            ("篳篥", "六", f"{hn('六')}(変えない)",
             f"工・五へ渡るとき(工・五から来るときも)、境目で約{hm['sink']['六'][1]}セントなめらかに沈み込む。"),
            ("竜笛", "五", f"{I.RYUTEKI['五']}(下無・平調の商)",
             f"高めに当たりやすいのを、メリで約{rm['settle']['五']}セント抑え込んで正しい高さに合わせる。"),
            ("竜笛", "丅", f"{I.RYUTEKI['丅']}(上無・平調の羽)",
             f"ハカリ・メリで約{rm['settle']['丅']}セント抑え、笙の合竹に揃える。"),
            ("竜笛", "干(和)", f"{I.RYUTEKI['干']}(平調・主音)",
             f"上向き(カリ)から下向き(メリ)へ角度を変え、約{rm['settle_low']['干']}セント上からなめらかに着地する。"),
            ("竜笛", "六", f"{I.RYUTEKI['六']}(変えない)",
             f"経過音(前後が別の音で1拍以内)のとき、メルで約{rm['passing_dip']['六']}セント落とす。"),
            ("竜笛", "夕", f"{I.RYUTEKI['夕']}(変えない)",
             f"{rm['fall_min_sec']}秒以上伸ばすと顎を引いて約{rm['fall']['夕']}セント落とす(途中は階段状、フレーズの終わりは滑り台状)。"),
        ]
        head = "<tr><th>楽器</th><th>譜字</th><th>音高(正律 → 平調)</th><th>平調での奏法(このアプリでの再現)</th></tr>"
    else:
        rows = [
            ("Hichiriki", "舌", f"{hn('舌')} → {h._note_name('舌', MODE)} (Shimomu)",
             f"Lowered a semitone (meri). The onset dips about {hm['dip']['舌']} cents, near F (Shōzetsu), then rises."),
            ("Hichiriki", "丄", f"{hn('丄')} → {h._note_name('丄', MODE)} (Shimomu)",
             f"An octave above 舌, lowered the same way, with a {hm['dip']['丄']}-cent dip at the onset."),
            ("Hichiriki", "凢", f"{hn('凢')} → {h._note_name('凢', MODE)} (Kamimu)",
             f"Meri-han: fitted to the mode's C#, with a {hm['dip']['凢']}-cent dip at the onset."),
            ("Hichiriki", "四", f"{hn('四')} (unchanged)",
             f"Dips about {hm['dip']['四']} cents before rising at phrase joins and 塩梅 onsets."),
            ("Hichiriki", "六", f"{hn('六')} (unchanged)",
             f"Sinks about {hm['sink']['六'][1]} cents where it meets 工 or 五."),
            ("Ryūteki", "五", f"{I.RYUTEKI['五']} (Shimomu, shō degree)",
             f"Tends to start sharp; pulled down about {rm['settle']['五']} cents to pitch (meri)."),
            ("Ryūteki", "丅", f"{I.RYUTEKI['丅']} (Kamimu, u degree)",
             f"Pulled down about {rm['settle']['丅']} cents (hakari / meri) to match the shō chords."),
            ("Ryūteki", "干 (low)", f"{I.RYUTEKI['干']} (Hyōjō, tonic)",
             f"Lands smoothly on E from about {rm['settle_low']['干']} cents above (kari to meri)."),
            ("Ryūteki", "六", f"{I.RYUTEKI['六']} (unchanged)",
             f"As a passing note (different notes on both sides, one beat or less), dips about {rm['passing_dip']['六']} cents (meru)."),
            ("Ryūteki", "夕", f"{I.RYUTEKI['夕']} (unchanged)",
             f"Held for {rm['fall_min_sec']} s or more, falls about {rm['fall']['夕']} cents: in steps mid-phrase, sliding at the end of a phrase."),
        ]
        head = "<tr><th>Instrument</th><th>Character</th><th>Pitch (standard → Hyōjō)</th><th>Technique in Hyōjō (as played by the app)</th></tr>"
    body = "".join(f"<tr><td>{a}</td><td class='ch1'>{b}</td><td>{c}</td><td>{d}</td></tr>" for a, b, c, d in rows)
    return f'<div class="scroll"><table class="meri-t"><thead>{head}</thead><tbody>{body}</tbody></table></div>'


TEXT = {
    "ja": {
        "lang": "ja", "path": "hyojo/", "other": "en/hyojo/", "other_label": "English version",
        "title": "平調の音階と譜字の対応表|雅楽譜プレイヤー",
        "desc": "雅楽の平調(E を主音とする律旋)の音階と、笙・篳篥・竜笛・琵琶・筝の譜字・音高の対応表。篳篥・竜笛の平調のメリ(メリ凢など)も一覧にしています。",
        "h1": "平調の音階と譜字の対応表",
        "lead": "平調(ひょうじょう)は、E(十二律の平調)を主音(宮)とする律旋の調子です。下の表は、雅楽譜プレイヤーが平調で鳴らす各楽器の譜字と音高を、音階の音ごとにまとめたものです。",
        "h_scale": "音階と各楽器の譜字",
        "scale_note": "音名は国際式(A4 = 430 Hz を基準)。<b class='meri'>赤字</b>の譜字は、平調でメリなどの例外的な奏法が付くもの(下の表を参照)。琵琶は弦と柱、筝は弦の名前です。琵琶・筝の平調の調弦は、出典が見つからなかったため主音と音階から組んだ暫定値です。笙は合竹ではなく、竹(簧)1本ずつの音高です。",
        "h_meri": "平調の例外的な奏法(メリ・ハカリ)",
        "meri_note": "セントは半音の 1/100。値はアプリの既定値で、<code>gagaku/instruments.py</code> の <code>HICHIRIKI_MERI</code>・<code>RYUTEKI_MERI</code> と <code>gagaku/tunings.json</code> で変えられます。",
        "h_scale_def": "平調の音階",
        "scale_def": "平調は律旋で、五声は 宮 E・商 F#・角 A・徴 B・羽 C#。これに嬰商 G・嬰羽 D を加えた七声で旋律が動きます。",
        "back": "← 雅楽譜プレイヤーのトップへ", "back_href": "../",
        "gen": f"この表は雅楽譜プレイヤー {__version__} の音高データから自動で作っています(<code>tools/build_hyojo_table.py</code>)。",
    },
    "en": {
        "lang": "en", "path": "en/hyojo/", "other": "hyojo/", "other_label": "日本語版",
        "title": "Hyōjō scale and notation chart | Gagaku Score Player",
        "desc": "The gagaku Hyōjō mode (a ritsu scale on E) and the matching notation characters and pitches for shō, hichiriki, ryūteki, biwa and koto, including the hichiriki and ryūteki meri techniques.",
        "h1": "Hyōjō scale and notation chart",
        "lead": "Hyōjō (平調) is a gagaku mode in the ritsu scale with E (the pitch Hyōjō in the twelve-tone jūniritsu system) as its tonic. The chart lists, for each pitch, the characters and pitches that Gagaku Score Player plays in Hyōjō.",
        "h_scale": "Scale and characters by instrument",
        "scale_note": "Pitches use international names (A4 = 430 Hz). Characters in <b class='meri'>red</b> get a special technique such as meri in Hyōjō (see the next table). Biwa entries show string and fret; koto entries are string names. The biwa and koto Hyōjō tunings are provisional, built from the mode's tonic and scale because no source was found. Shō pitches are for single pipes, not chords.",
        "h_meri": "Special techniques in Hyōjō (meri and hakari)",
        "meri_note": "A cent is 1/100 of a semitone. The values are the app's defaults; change them in <code>HICHIRIKI_MERI</code> and <code>RYUTEKI_MERI</code> in <code>gagaku/instruments.py</code> and in <code>gagaku/tunings.json</code>.",
        "h_scale_def": "The Hyōjō scale",
        "scale_def": "Hyōjō uses the ritsu scale. Its five core degrees are kyū E, shō F#, kaku A, chi B and u C#, with ei-shō G and ei-u D as the two additional degrees.",
        "back": "← Back to Gagaku Score Player", "back_href": "../",
        "gen": f"This chart is generated from the pitch data of Gagaku Score Player {__version__} (<code>tools/build_hyojo_table.py</code>).",
    },
}

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
"""


def page(lang: str, data) -> str:
    t = TEXT[lang]
    src = (ROOT / "docs" / "index.html").read_text(encoding="utf-8")
    style = re.search(r"<style>(.*?)</style>", src, re.S).group(1)
    url, alt = BASE + t["path"], BASE + t["other"]
    ja_url, en_url = BASE + "hyojo/", BASE + "en/hyojo/"
    icon = "../images/icon.png" if lang == "ja" else "../../images/icon.png"
    return f"""<!doctype html>
<html lang="{t['lang']}">
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
  </div>
</header>

<main class="wrap">

  <section>
    <h2>{t['h_scale_def']}</h2>
    <p>{t['scale_def']}</p>
  </section>

  <section id="scale">
    <h2>{t['h_scale']}</h2>
    {scale_table(data, lang)}
    <p class="small-note">{t['scale_note']}</p>
  </section>

  <section id="meri">
    <h2>{t['h_meri']}</h2>
    {meri_table(lang)}
    <p class="small-note">{t['meri_note']}</p>
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


def main():
    data = collect()
    for lang in ("ja", "en"):
        out = ROOT / "docs" / TEXT[lang]["path"] / "index.html"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(page(lang, data), encoding="utf-8", newline="\n")
        print("wrote", out.relative_to(ROOT))


if __name__ == "__main__":
    main()
