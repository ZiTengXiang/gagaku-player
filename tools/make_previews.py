"""楽器ごとの試聴用WAVを previews/ に書き出す:  python tools/make_previews.py"""
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from gagaku import instruments, render, score  # noqa: E402

DEMO = (ROOT / "examples" / "demo_hyojo.gaku").read_text(encoding="utf-8")
OUT = ROOT / "previews"
OUT.mkdir(exist_ok=True)

sc = score.parse(DEMO)
keys = list(instruments.INSTRUMENTS)
for key in keys:
    t = time.time()
    data = render.render(sc, mute=set(keys) - {key}, reverb=0.3)
    name = instruments.INSTRUMENTS[key].display
    render.write_wav(OUT / f"{name}.wav", data)
    rms = float(np.sqrt(np.mean(data ** 2)))
    print(f"{name}: {len(data) / render.SR:.1f}秒  rms={rms:.3f}  ({time.time() - t:.1f}s)")

t = time.time()
render.write_wav(OUT / "合奏.wav", render.render(sc, reverb=0.3))
print(f"合奏: ({time.time() - t:.1f}s)")
