"""English UI プラグイン: 画面を英語にし、譜字ボタンに読みと説明のポップアップを付ける。

譜面テキストに書く譜字そのものは(ファイルのデータなので)漢字のまま。
"""

INSTRUMENT_NAMES = {
    "sho": "Shō", "hichiriki": "Hichiriki", "ryuteki": "Ryūteki", "biwa": "Biwa",
    "koto": "Koto", "kakko": "Kakko", "shoko": "Shōko", "taiko": "Taiko",
}
MODE_NAMES = {
    "壱越調": "Ichikotsu-chō", "平調": "Hyōjō", "双調": "Sōjō",
    "黄鐘調": "Ōshiki-chō", "盤渉調": "Banshiki-chō", "太食調": "Taishiki-chō",
}

# 譜字 → (ローマ字の読み, かな)
_SHO_PIPES = {
    "千": ("sen", "せん"), "十": ("jū", "じゅう"), "下": ("ge", "げ"), "乙": ("otsu", "おつ"),
    "工": ("ku", "く"), "美": ("bi", "び"), "一": ("ichi", "いち"), "八": ("hachi", "はち"),
    "言": ("gon", "ごん"), "七": ("shichi", "しち"), "行": ("gyō", "ぎょう"), "上": ("jō", "じょう"),
    "凢": ("bō", "ぼう"), "乞": ("kotsu", "こつ"), "比": ("hi", "ひ"),
}
READINGS = {
    "sho": {
        **{k: v for k, v in _SHO_PIPES.items()},
        "乙美": ("otsu-bi", "おつび"), "乙言": ("otsu-gon", "おつごん"),
        "凢美": ("bō-bi", "ぼうび"), "凢言": ("bō-gon", "ぼうごん"),
        **{"単" + k: ("tan-" + r, "たん" + kana) for k, (r, kana) in _SHO_PIPES.items()},
    },
    "hichiriki": {
        "舌": ("zetsu", "ぜつ"), "五": ("go", "ご"), "工": ("kō", "こう"), "凢": ("han", "はん"),
        "六": ("riku", "りく"), "四": ("shi", "し"), "一": ("ichi", "いち"), "丄": ("jō", "じょう"),
        "丁": ("tei", "てい"), "ム": ("mu", "む"),
    },
    "ryuteki": {
        "干": ("kan", "かん"), "五": ("go", "ご"), "丄": ("jō", "じょう"), "夕": ("shaku", "しゃく"),
        "中": ("chū", "ちゅう"), "丅": ("ge", "げ"), "六": ("roku", "ろく"),
    },
    "biwa": {
        "一": ("ichi", "いち"), "工": ("ku", "く"), "凢": ("bo", "ぼ"), "フ": ("shu", "しゅ"), "斗": ("to", "と"),
        "乚": ("otsu", "おつ"), "下": ("ge", "げ"), "十": ("jū", "じゅう"), "乙": ("bi", "び"), "コ": ("ko", "こ"),
        "ク": ("gyō", "ぎょう"), "七": ("shichi", "しち"), "ヒ": ("hi", "ひ"), "〻": ("gon", "ごん"),
        "之": ("shi", "し"), "丄": ("jō", "じょう"), "八": ("hachi", "はち"), "丨": ("boku", "ぼく"),
        "ム": ("sen", "せん"), "也": ("ya", "や"),
    },
    "koto": {
        "一": ("ichi", "いち"), "二": ("ni", "に"), "三": ("san", "さん"), "四": ("shi", "し"),
        "五": ("go", "ご"), "六": ("roku", "ろく"), "七": ("shichi", "しち"), "八": ("hachi", "はち"),
        "九": ("ku", "く"), "十": ("jū", "じゅう"), "斗": ("to", "と"), "為": ("i", "い"), "巾": ("kin", "きん"),
    },
    "kakko": {"正": ("sei", "せい"), "片来": ("katarai", "かたらい"), "諸来": ("morarai", "もろらい"),
              "来": ("rai", "らい")},
    "shoko": {"ク": ("ku", "く"), "レイ": ("rei", "れい"), "クレイ": ("ku-rei", "くれい")},
    "taiko": {"図": ("zun", "ずん"), "百": ("dō", "どう")},
}
for _s in list(READINGS["biwa"]):
    _r, _k = READINGS["biwa"][_s]
    READINGS["biwa"]["単" + _s] = ("tan-" + _r, "たん" + _k)
for _s in list(READINGS["koto"]):
    _r, _k = READINGS["koto"][_s]
    READINGS["koto"]["閑" + _s] = ("shizu-" + _r, "しずがき・" + _k)
    READINGS["koto"]["早" + _s] = ("haya-" + _r, "はやがき・" + _k)

# 打楽器の打ち方の説明
STROKES = {
    ("kakko", "正"): "single stroke on the right head",
    ("kakko", "片来"): "roll with the left stick only, starting slow and speeding up",
    ("kakko", "諸来"): "roll alternating both sticks, starting slow and speeding up",
    ("kakko", "来"): "roll, starting slow and speeding up",
    ("shoko", "金"): "one stroke",
    ("shoko", "生"): "one stroke",
    ("shoko", "ク"): "stroke with the left stick",
    ("shoko", "レイ"): "stroke with the right stick",
    ("shoko", "クレイ"): "two strokes: left, then right",
    ("taiko", "図"): "light lead-in stroke (zun)",
    ("taiko", "百"): "strong main stroke (dō)",
}
SPECIAL = {
    "-": "Hold the previous note one more beat (-:2 holds two beats)",
    ".": "Rest one beat (.:2 rests two beats)",
    "|": "Bar line",
    "+": "Join with the next character to strike different strings together (e.g. 一+ク)",
}

TEXTS = {
    "pm.lang": "en",
    "title.app": "Gagaku Score Player",
    "title.untitled": "Untitled",
    "menu.file": "File", "menu.plugins": "Plugins",
    "menu.file.new": "New", "menu.file.open": "Open…", "menu.file.save": "Save",
    "menu.file.export": "Export WAV…", "menu.file.quit": "Quit",
    "menu.plugins.manage": "Find and manage plugins…",
    "tb.new": "New", "tb.open": "Open", "tb.save": "Save", "tb.export": "Export WAV", "tb.align": "Align",
    "tb.play": "▶ Play", "tb.play_cursor": "▶ From cursor", "tb.stop": "■ Stop",
    "tb.bar": "Bar", "tb.beats_unit": "beats", "tb.ma": "Ma between bars", "tb.speed": "Speed",
    "tb.reverb": "Reverb",
    "tab.text": "Score text", "tab.score": "Score view", "tab.staff": "Staff",
    "palette.title": "Notation palette (click to insert)",
    "palette.insert_section": "Insert a [{name}] block",
    "palette.koto_half": "Insert as half beats (adds :1/2 to characters and rests)",
    "mixer.title": "Mixer (uncheck to mute)",
    "help.sho": "Chord names (乞 一 工 凢 乙 下 十 美 行 比 / 乙美 乙言 凢美 凢言). Prefix 単 (e.g. 単千) for a single pipe. In Sōjō, 十 is the five-note 十.",
    "help.hichiriki": "舌 五 工 凢 六 四 一 丄 丁 (low to high, G4–A5). ム is not used in current pieces. Notes start with an enbai pitch bend. In Hyōjō, 舌 is lowered to F#4 and 丄 to F#5 (meri).",
    "help.ryuteki": "Low-register (wa) characters. Hold with - (1 beat) or -:2 (2 beats). 責六 or 六' for the high register (seme); 干, for one octave lower. 干 sounds above 六 (E).",
    "help.biwa": "String 1: 一工凢フ斗  2: 乚下十乙コ  3: ク七ヒ〻之  4: 丄八丨ム也 (open, frets 1–4). Normally a sweep that lands on the beat; prefix 単 for a single note. Join with + (e.g. 一+ク) to strike different strings together. Tunings are provisional (tunings.json).",
    "help.koto": "String names 一–十 斗 為 巾 for single notes. 閑三 = shizugaki pattern, 早三 = hayagaki pattern (approximate). Half beat: 三:1/2 (rest: .:1/2). Tunings are provisional (tunings.json).",
    "help.kakko": "正 = single right stroke / 片来 = roll with the left stick / 諸来 = roll with both sticks. Give rolls a length, e.g. 諸来:3 (speed follows the tempo).",
    "help.shoko": "金・生 = one stroke / ク = left / レイ = right / クレイ = left then right",
    "help.taiko": "図 = light lead-in stroke (zun) / 百 = strong stroke (dō)",
    "status.pos": "Ln {line}, Col {col}",
    "status.aligned": "Aligned so that the beats line up (five bars per system)",
    "status.rebarred": "Re-barred at {n} beats per bar",
    "status.ma_on": "Ma between bars: {n} beats (applied to playback and export)",
    "status.ma_off": "No ma between bars (in tempo)",
    "status.saved": "Saved: {path}",
    "status.score_error": "Score error: {err}",
    "status.selected": "Selected “{sym}” on line {line} (press F6 to play from here)",
    "status.error": "Error: {err}",
    "status.rendering": "Rendering…",
    "status.playing": "Playing ({title} / {mode} / {bpm} BPM)",
    "status.finished": "Finished",
    "status.exported": "Exported: {path}",
    "dlg.cannot_align": "Cannot align", "dlg.align_error": "The score has an error.\n{err}",
    "dlg.confirm": "Confirm", "dlg.save_changes": "Save changes?",
    "dlg.score_error": "Score error", "dlg.info": "Information", "dlg.no_notes": "There are no notes",
    "dlg.render_failed": "Rendering failed", "dlg.play_error": "Playback error",
    "file.gaku": "Gagaku score", "file.txt": "Text", "file.all": "All files",
    "pm.title": "Plugins", "pm.search": "Search", "pm.refresh": "Load online list",
    "pm.col.name": "Name", "pm.col.version": "Version", "pm.col.status": "Status", "pm.col.desc": "Description",
    "pm.install": "Install", "pm.update": "Update", "pm.enable": "Enable", "pm.disable": "Disable",
    "pm.uninstall": "Uninstall", "pm.close": "Close",
    "pm.warn": "Plugins run as Python code. Install only plugins you trust.",
    "pm.status.not_installed": "Not installed", "pm.status.enabled": "Enabled", "pm.status.disabled": "Disabled",
    "pm.loading": "Loading the online list…",
    "pm.online_ok": "Loaded the online list ({n} plugins)",
    "pm.online_failed": "Could not load the online list (showing the bundled list)",
    "pm.confirm_install": "Install “{name}”?\nPlugins run as Python code.",
    "pm.installed_ok": "Installed and enabled “{name}”",
    "pm.confirm_uninstall": "Uninstall “{name}”?",
}


def _cap(s: str) -> str:
    return s[:1].upper() + s[1:]


class Plugin:
    def activate(self, api):
        self.api = api
        api.set_texts(TEXTS)
        api.add_instrument_label(lambda key: INSTRUMENT_NAMES.get(key))
        api.add_palette_label(self.label)
        api.add_palette_tooltip(self.tooltip)

    def deactivate(self, api):
        pass

    # 譜字ボタンの表示名: 「Ichi（一）」
    def label(self, inst_key, sym):
        r = READINGS.get(inst_key, {}).get(sym)
        if r:
            return f"{_cap(r[0])}（{sym}）"
        if (inst_key, sym) in STROKES:
            return f"Hit（{sym}）"
        return None

    # ボタンに触れたときのポップアップ: 読み・日本語表記・構成音
    def tooltip(self, inst_key, sym, mode):
        if sym in SPECIAL:
            return SPECIAL[sym]
        lines = []
        r = READINGS.get(inst_key, {}).get(sym)
        if r:
            lines.append(f"Reading: {r[0]}")
            lines.append(f"Japanese: {sym}({r[1]})")
        else:
            lines.append(f"Japanese: {sym}")
        if (inst_key, sym) in STROKES:
            lines.append(f"Stroke: {STROKES[(inst_key, sym)]}")
            return "\n".join(lines)
        inst = self.api.instruments.INSTRUMENTS[inst_key]
        try:
            sp = inst.staff_pitches(inst.canonical(sym), 0, mode)
        except Exception:  # noqa: BLE001
            sp = None
        if sp:
            names, arp = sp
            notes = ", ".join(names)
            if inst_key == "sho" and len(names) > 1:
                kind = "chord"
            elif inst_key == "biwa" and arp:
                kind = f"arpeggio, landing on {names[-1]} on the beat"
            elif inst_key == "koto" and sym[:1] in "閑早":
                kind = "shizugaki pattern" if sym[0] == "閑" else "hayagaki pattern"
                kind += ", arpeggio"
            elif len(names) > 1:
                kind = "played together"
            else:
                kind = "single note"
            lines.append(f"Notes: {notes} ({kind})")
            lines.append(f"Mode: {MODE_NAMES.get(mode, mode)}")
        return "\n".join(lines)
