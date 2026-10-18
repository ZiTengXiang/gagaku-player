"""紹介サイト用の試聴音源(MP3)を docs/audio/ に書き出す。

    python tools/make_site_audio.py [越天楽の譜面ファイル]

MP3 の書き出しには soundfile が必要(pip install soundfile。アプリ本体の依存ではない)。
"""
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from gagaku import render, score  # noqa: E402

OUT = ROOT / "docs" / "audio"
OUT.mkdir(parents=True, exist_ok=True)

pieces = [
    ("etenraku", Path(sys.argv[1]) if len(sys.argv) > 1 else None),
    ("wakatake", ROOT / "examples" / "wakatake_sojo.gaku"),
    ("asagasumi", ROOT / "examples" / "asagasumi_ichikotsu.gaku"),
    ("tsukikage", ROOT / "examples" / "tsukikage_oshiki.gaku"),
    ("shimoyo", ROOT / "examples" / "shimoyo_banshiki.gaku"),
    ("hanaikada", ROOT / "examples" / "hanaikada_taishiki.gaku"),
]
for name, path in pieces:
    if path is None or not path.exists():
        print(f"skip {name}: 譜面ファイルがありません")
        continue
    sc = score.parse(path.read_text(encoding="utf-8"))
    data = render.render(sc, reverb=0.3)
    # 余韻の無音部分を切り詰め、最後を軽くフェード
    loud = np.where(np.abs(data).max(axis=1) > 1e-3)[0]
    data = data[: min(len(data), loud[-1] + int(0.5 * render.SR))] if len(loud) else data
    fade = min(len(data), int(0.8 * render.SR))
    data[-fade:] *= np.linspace(1, 0, fade)[:, None]
    out = OUT / f"{name}.mp3"
    sf.write(out, data, render.SR, format="MP3", subtype="MPEG_LAYER_III", compression_level=0.5)
    print(f"{name}: {sc.title} {len(data) / render.SR:.0f}秒 → {out.name} {out.stat().st_size / 1e6:.2f}MB")
