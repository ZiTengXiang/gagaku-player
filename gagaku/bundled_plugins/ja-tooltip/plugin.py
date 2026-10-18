"""譜字ポップアップ(日本語): 譜字ボタンに、読み・表記・構成音の説明を日本語で出す。

画面の文言やボタンの表示名は変えない(日本語のまま)。
"""

INSTRUMENT_NAMES = {
    "sho": "笙", "hichiriki": "篳篥", "ryuteki": "竜笛", "biwa": "琵琶",
    "koto": "筝", "kakko": "鞨鼓", "shoko": "鉦鼓", "taiko": "太鼓",
}

_SHO_PIPES = {
    "千": "せん", "十": "じゅう", "下": "げ", "乙": "おつ", "工": "く", "美": "び", "一": "いち",
    "八": "はち", "言": "ごん", "七": "しち", "行": "ぎょう", "上": "じょう", "凢": "ぼう",
    "乞": "こつ", "比": "ひ",
}
READINGS = {
    "sho": {**_SHO_PIPES, "乙美": "おつび", "乙言": "おつごん", "凢美": "ぼうび", "凢言": "ぼうごん",
            **{"単" + k: v for k, v in _SHO_PIPES.items()}},
    "hichiriki": {"舌": "ぜつ", "五": "ご", "工": "こう", "凢": "はん", "六": "りく", "四": "し",
                  "一": "いち", "丄": "じょう", "丁": "てい", "ム": "む"},
    "ryuteki": {"干": "かん", "五": "ご", "丄": "じょう", "夕": "しゃく", "中": "ちゅう", "丅": "げ",
                "六": "ろく"},
    "biwa": {"一": "いち", "工": "く", "凢": "ぼ", "フ": "しゅ", "斗": "と", "乚": "おつ", "下": "げ",
             "十": "じゅう", "乙": "び", "コ": "こ", "ク": "ぎょう", "七": "しち", "ヒ": "ひ", "〻": "ごん",
             "之": "し", "丄": "じょう", "八": "はち", "丨": "ぼく", "ム": "せん", "也": "や"},
    "koto": {"一": "いち", "二": "に", "三": "さん", "四": "し", "五": "ご", "六": "ろく", "七": "しち",
             "八": "はち", "九": "く", "十": "じゅう", "斗": "と", "為": "い", "巾": "きん"},
    "kakko": {"正": "せい", "片来": "かたらい", "諸来": "もろらい", "来": "らい"},
    "shoko": {"ク": "く", "レイ": "れい", "クレイ": "くれい"},
    "taiko": {"図": "ずん", "百": "どう"},
}
for _s, _r in list(READINGS["biwa"].items()):
    READINGS["biwa"]["単" + _s] = _r
for _s, _r in list(READINGS["koto"].items()):
    READINGS["koto"]["閑" + _s] = "しずがき・" + _r
    READINGS["koto"]["早" + _s] = "はやがき・" + _r

STROKES = {
    ("kakko", "正"): "右の面を一打",
    ("kakko", "片来"): "左の桴だけのロール(打ち始めは間遠く、次第に速まる)",
    ("kakko", "諸来"): "両方の桴を交互に打つロール(打ち始めは間遠く、次第に速まる)",
    ("kakko", "来"): "ロール(打ち始めは間遠く、次第に速まる)",
    ("shoko", "金"): "一打", ("shoko", "生"): "一打",
    ("shoko", "ク"): "左の桴で一打", ("shoko", "レイ"): "右の桴で一打",
    ("shoko", "クレイ"): "左、右の順に二打",
    ("taiko", "図"): "軽い前打(ずん)", ("taiko", "百"): "強打(どう)",
}
SPECIAL = {
    "-": "直前の音を1拍延ばす(-:2 で2拍)",
    ".": "1拍休む(.:2 で2拍)",
    "|": "小節線",
    "+": "次の譜字とつなぎ、別々の弦を同時に弾く(例: 一+ク)",
}
BIWA_FRETS = ["開放", "第1柱", "第2柱", "第3柱", "第4柱"]


def _position(api, inst_key, sym):
    """表記の補足(琵琶の弦と柱、筝の弦、笙の合竹か一本か)。"""
    base = sym[1:] if sym[:1] in "単閑早" else sym
    if inst_key == "biwa" and "+" not in sym:
        pos = api.instruments.BIWA_POS.get(base)
        if pos:
            return f"{pos[0] + 1}弦・{BIWA_FRETS[pos[1]]}"
    if inst_key == "koto":
        return f"{base}の弦"
    if inst_key == "sho":
        return "一本だけ" if sym.startswith("単") else "合竹"
    return None


class Plugin:
    def activate(self, api):
        self.api = api
        api.add_palette_tooltip(self.tooltip)

    def deactivate(self, api):
        pass

    def tooltip(self, inst_key, sym, mode):
        if sym in SPECIAL:
            return SPECIAL[sym]
        lines = []
        reading = READINGS.get(inst_key, {}).get(sym)
        if reading:
            lines.append(f"読み: {reading}")
        pos = _position(self.api, inst_key, sym)
        lines.append(f"表記: {sym}" + (f"({INSTRUMENT_NAMES.get(inst_key, '')}・{pos})" if pos else
                                     f"({INSTRUMENT_NAMES.get(inst_key, '')})"))
        if (inst_key, sym) in STROKES:
            lines.append(f"打ち方: {STROKES[(inst_key, sym)]}")
            return "\n".join(lines)
        inst = self.api.instruments.INSTRUMENTS[inst_key]
        try:
            sp = inst.staff_pitches(inst.canonical(sym), 0, mode)
        except Exception:  # noqa: BLE001
            sp = None
        if sp:
            names, arp = sp
            if inst_key == "sho" and len(names) > 1:
                kind = "和音"
            elif inst_key == "biwa" and arp:
                kind = f"アルペジオ。{names[-1]} を拍頭に着地"
            elif inst_key == "koto" and sym[:1] in "閑早":
                kind = ("閑掻" if sym[0] == "閑" else "早掻") + "・アルペジオ"
            elif len(names) > 1:
                kind = "同時に鳴らす"
            else:
                kind = "単音"
            lines.append(f"構成音: {', '.join(names)}({kind})")
            lines.append(f"調子: {mode}")
        return "\n".join(lines)
