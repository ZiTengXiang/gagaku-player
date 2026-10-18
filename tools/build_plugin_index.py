"""紹介サイトにプラグインの一覧(docs/plugins/index.json)を作る。

    python tools/build_plugin_index.py

gagaku/bundled_plugins/<id>/ の plugin.json と plugin.py を docs/plugins/<id>/ に写し、
各ファイルの SHA-256 を index.json に書く。アプリはこの一覧で検索し、インストール時に
ハッシュを照合する。新しいプラグインは bundled_plugins に置いてからこれを実行する。
"""
import hashlib
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from gagaku.plugins import API_VERSION, BUNDLED_DIR, PLUGIN_FILES  # noqa: E402

OUT = ROOT / "docs" / "plugins"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    entries = []
    for src in sorted(p for p in BUNDLED_DIR.iterdir() if (p / "plugin.json").is_file()):
        manifest = json.loads((src / "plugin.json").read_text(encoding="utf-8"))
        dst = OUT / manifest["id"]
        dst.mkdir(exist_ok=True)
        files = {}
        for name in PLUGIN_FILES:
            data = (src / name).read_bytes()
            (dst / name).write_bytes(data)
            files[name] = hashlib.sha256(data).hexdigest()
        entries.append({**{k: manifest[k] for k in ("id", "name", "version", "description", "tags")},
                        "api": manifest.get("api", API_VERSION), "path": f"{manifest['id']}/", "files": files})
        print(f"{manifest['id']} {manifest['version']}: {files}")
    # 一覧から消えたプラグインのフォルダを片付ける
    keep = {e["id"] for e in entries}
    for d in OUT.iterdir():
        if d.is_dir() and d.name not in keep:
            shutil.rmtree(d)
    index = {"api": API_VERSION, "plugins": entries}
    (OUT / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("wrote", OUT / "index.json")


if __name__ == "__main__":
    main()
