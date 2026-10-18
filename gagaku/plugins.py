"""プラグインの仕組み。

プラグインは `<ホーム>/plugins/<id>/` に置かれた次の2ファイルからなる:

    plugin.json  {"id", "name", "version", "description": {"ja", "en"}, "tags", "api": 1}
    plugin.py    class Plugin:  def activate(self, api): ...   def deactivate(self, api): ... (任意)

`activate` に渡される `PluginAPI` を通して、画面の文言・譜字ボタンの表示名・
ボタンのポップアップ説明・楽器名を差し替えられる。プラグインが登録したものは
無効にしたとき自動で取り除かれる。

ホームは既定で `~/.gagaku_player`(環境変数 GAGAKU_PLAYER_HOME で変更可)。
有効・無効は `<ホーム>/settings.json` に保存する。

プラグインの一覧(カタログ)は、アプリ同梱のもの(gagaku/bundled_plugins)と、
紹介サイトの plugins/index.json を合わせたもの。オンラインから入れるときは、
一覧に載っている SHA-256 とファイルを照合してから保存する。
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
import sys
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

API_VERSION = 1
CATALOG_URL = "https://zitengxiang.github.io/gagaku-player/plugins/index.json"
BUNDLED_DIR = Path(__file__).resolve().parent / "bundled_plugins"
PLUGIN_FILES = ("plugin.json", "plugin.py")


def home_dir() -> Path:
    return Path(os.environ.get("GAGAKU_PLAYER_HOME") or (Path.home() / ".gagaku_player"))


def plugins_dir() -> Path:
    return home_dir() / "plugins"


def settings_path() -> Path:
    return home_dir() / "settings.json"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class PluginError(Exception):
    pass


@dataclass
class PluginInfo:
    id: str
    name: str
    version: str
    description: dict = field(default_factory=dict)
    tags: list = field(default_factory=list)
    api: int = API_VERSION
    source: str = "bundled"           # "bundled" / "online" / "installed"
    files: dict = field(default_factory=dict)   # オンライン: ファイル名 → SHA-256
    base_url: str = ""

    @classmethod
    def from_manifest(cls, m: dict, **kw) -> "PluginInfo":
        return cls(id=m["id"], name=m.get("name", m["id"]), version=str(m.get("version", "0")),
                   description=m.get("description", {}), tags=list(m.get("tags", [])),
                   api=int(m.get("api", API_VERSION)), **kw)

    def describe(self, lang: str = "ja") -> str:
        d = self.description
        return d.get(lang) or d.get("ja") or d.get("en") or ""

    def matches(self, query: str) -> bool:
        q = query.strip().lower()
        if not q:
            return True
        hay = " ".join([self.id, self.name, *self.description.values(), *self.tags]).lower()
        return all(word in hay for word in q.split())


def _version_key(v: str):
    return tuple(int(p) if p.isdigit() else 0 for p in v.split("."))


class PluginAPI:
    """1つのプラグインに渡す窓口。登録したものはこのオブジェクトごとに管理する。"""

    def __init__(self, manager: "PluginManager", plugin_id: str):
        self._manager = manager
        self.plugin_id = plugin_id
        self.texts: dict[str, str] = {}
        self.palette_labelers: list = []
        self.palette_tooltips: list = []
        self.instrument_labelers: list = []

    # --- プラグインから使う関数 ---
    @property
    def instruments(self):
        from . import instruments
        return instruments

    def set_texts(self, mapping: dict[str, str]):
        """画面の文言を差し替える(キーは App.t() に渡しているもの)。"""
        self.texts.update(mapping)

    def add_palette_label(self, func):
        """func(楽器キー, 譜字) -> 表示名 または None。"""
        self.palette_labelers.append(func)

    def add_palette_tooltip(self, func):
        """func(楽器キー, 譜字, 調子) -> ポップアップの文 または None。"""
        self.palette_tooltips.append(func)

    def add_instrument_label(self, func):
        """func(楽器キー) -> 楽器の表示名 または None。"""
        self.instrument_labelers.append(func)

    def current_mode(self) -> str:
        return self._manager.current_mode()


class PluginManager:
    def __init__(self, current_mode=lambda: "平調", on_change=lambda: None):
        self.current_mode = current_mode
        self.on_change = on_change
        self.active: dict[str, tuple[object, PluginAPI]] = {}
        self.errors: dict[str, str] = {}

    # ------------------------------------------------------------ 設定
    def _load_settings(self) -> dict:
        try:
            return json.loads(settings_path().read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def _save_settings(self, data: dict):
        settings_path().parent.mkdir(parents=True, exist_ok=True)
        settings_path().write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def is_enabled(self, plugin_id: str) -> bool:
        return bool(self._load_settings().get("plugins", {}).get(plugin_id, {}).get("enabled"))

    def _remember(self, plugin_id: str, enabled: bool | None):
        data = self._load_settings()
        plugins = data.setdefault("plugins", {})
        if enabled is None:
            plugins.pop(plugin_id, None)
        else:
            plugins.setdefault(plugin_id, {})["enabled"] = enabled
        self._save_settings(data)

    # ------------------------------------------------------------ 入っているプラグイン
    def installed(self) -> list[PluginInfo]:
        out = []
        d = plugins_dir()
        if d.is_dir():
            for sub in sorted(d.iterdir()):
                mf = sub / "plugin.json"
                if mf.is_file():
                    try:
                        out.append(PluginInfo.from_manifest(json.loads(mf.read_text(encoding="utf-8")),
                                                            source="installed"))
                    except (ValueError, KeyError):
                        continue
        return out

    def installed_info(self, plugin_id: str) -> PluginInfo | None:
        return next((p for p in self.installed() if p.id == plugin_id), None)

    def load_enabled(self):
        """起動時: 有効になっているプラグインをすべて読み込む。"""
        for info in self.installed():
            if self.is_enabled(info.id):
                try:
                    self._activate(info.id)
                except PluginError as e:
                    self.errors[info.id] = str(e)

    def set_enabled(self, plugin_id: str, enabled: bool):
        if enabled:
            self._activate(plugin_id)
        else:
            self._deactivate(plugin_id)
        self._remember(plugin_id, enabled)
        self.on_change()

    def _activate(self, plugin_id: str):
        if plugin_id in self.active:
            return
        folder = plugins_dir() / plugin_id
        info = self.installed_info(plugin_id)
        if info is None:
            raise PluginError(f"プラグイン '{plugin_id}' は入っていません")
        if info.api > API_VERSION:
            raise PluginError(f"プラグイン '{plugin_id}' はこの版のアプリには対応していません")
        name = f"gagaku_plugin_{plugin_id}"
        spec = importlib.util.spec_from_file_location(name, folder / "plugin.py")
        try:
            module = importlib.util.module_from_spec(spec)
            sys.modules[name] = module
            spec.loader.exec_module(module)
            plugin = module.Plugin()
            api = PluginAPI(self, plugin_id)
            plugin.activate(api)
        except Exception as e:  # noqa: BLE001  プラグインの不具合でアプリを落とさない
            sys.modules.pop(name, None)
            raise PluginError(f"プラグイン '{plugin_id}' を読み込めませんでした: {e!r}") from e
        self.active[plugin_id] = (plugin, api)
        self.errors.pop(plugin_id, None)

    def _deactivate(self, plugin_id: str):
        entry = self.active.pop(plugin_id, None)
        if entry is None:
            return
        plugin, api = entry
        if hasattr(plugin, "deactivate"):
            try:
                plugin.deactivate(api)
            except Exception:  # noqa: BLE001
                pass
        sys.modules.pop(f"gagaku_plugin_{plugin_id}", None)

    # ------------------------------------------------------------ インストール
    def install_bundled(self, plugin_id: str):
        src = BUNDLED_DIR / plugin_id
        if not (src / "plugin.json").is_file():
            raise PluginError(f"同梱のプラグイン '{plugin_id}' が見つかりません")
        self._write_files(plugin_id, {f: (src / f).read_bytes() for f in PLUGIN_FILES})

    def install_online(self, info: PluginInfo, fetch=None):
        """一覧に載っている SHA-256 と照合してから保存する。"""
        fetch = fetch or _http_get
        data = {}
        for fname in PLUGIN_FILES:
            expected = info.files.get(fname)
            if not expected:
                raise PluginError(f"一覧に {fname} のハッシュがありません")
            body = fetch(info.base_url + fname)
            if sha256_bytes(body) != expected:
                raise PluginError(f"{fname} のハッシュが一覧と一致しません(改ざん・破損のおそれ)")
            data[fname] = body
        manifest = json.loads(data["plugin.json"].decode("utf-8"))
        if manifest.get("id") != info.id:
            raise PluginError("プラグインの id が一覧と一致しません")
        self._write_files(info.id, data)

    def _write_files(self, plugin_id: str, files: dict[str, bytes]):
        if not plugin_id.replace("-", "").replace("_", "").isalnum():
            raise PluginError(f"プラグイン id '{plugin_id}' が不正です")
        was_active = plugin_id in self.active
        self._deactivate(plugin_id)
        folder = plugins_dir() / plugin_id
        folder.mkdir(parents=True, exist_ok=True)
        for name, body in files.items():
            (folder / name).write_bytes(body)
        if was_active:
            self._activate(plugin_id)

    def uninstall(self, plugin_id: str):
        self._deactivate(plugin_id)
        shutil.rmtree(plugins_dir() / plugin_id, ignore_errors=True)
        self._remember(plugin_id, None)
        self.on_change()

    # ------------------------------------------------------------ カタログ(検索)
    def bundled_catalog(self) -> list[PluginInfo]:
        out = []
        if BUNDLED_DIR.is_dir():
            for sub in sorted(BUNDLED_DIR.iterdir()):
                mf = sub / "plugin.json"
                if mf.is_file():
                    out.append(PluginInfo.from_manifest(json.loads(mf.read_text(encoding="utf-8")),
                                                        source="bundled"))
        return out

    def online_catalog(self, url: str = CATALOG_URL, fetch=None) -> list[PluginInfo]:
        fetch = fetch or _http_get
        index = json.loads(fetch(url).decode("utf-8"))
        base = url.rsplit("/", 1)[0] + "/"
        out = []
        for p in index.get("plugins", []):
            out.append(PluginInfo.from_manifest(p, source="online", files=p.get("files", {}),
                                                base_url=base + p.get("path", p["id"] + "/")))
        return out

    @staticmethod
    def merge_catalogs(*catalogs: list[PluginInfo]) -> list[PluginInfo]:
        """同じ id は新しい版を優先(同じ版なら先に渡したほう)。"""
        best: dict[str, PluginInfo] = {}
        for cat in catalogs:
            for p in cat:
                cur = best.get(p.id)
                if cur is None or _version_key(p.version) > _version_key(cur.version):
                    best[p.id] = p
        return sorted(best.values(), key=lambda p: p.name.lower())

    # ------------------------------------------------------------ 有効なプラグインの登録内容
    def _apis(self):
        return [api for _, api in self.active.values()]

    def texts(self) -> dict[str, str]:
        merged: dict[str, str] = {}
        for api in self._apis():
            merged.update(api.texts)
        return merged

    def _first(self, attr, *args):
        for api in reversed(self._apis()):   # 後から有効にしたものを優先
            for func in getattr(api, attr):
                try:
                    r = func(*args)
                except Exception:  # noqa: BLE001
                    r = None
                if r:
                    return r
        return None

    def palette_label(self, inst_key: str, sym: str) -> str | None:
        return self._first("palette_labelers", inst_key, sym)

    def palette_tooltip(self, inst_key: str, sym: str, mode: str) -> str | None:
        return self._first("palette_tooltips", inst_key, sym, mode)

    def instrument_label(self, inst_key: str) -> str | None:
        return self._first("instrument_labelers", inst_key)


def _http_get(url: str, timeout: float = 8.0) -> bytes:
    if not url.startswith("https://"):
        raise PluginError("https 以外からは取得しません")
    req = urllib.request.Request(url, headers={"User-Agent": "gagaku-player"})
    with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 (https のみ)
        return r.read()
