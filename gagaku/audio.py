"""再生バックエンド。Windows では標準の winsound、それ以外は sounddevice があれば使う。"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from .render import write_wav


class Player:
    def __init__(self):
        self._tmp = Path(tempfile.gettempdir()) / "gagaku_player_preview.wav"
        self._sd = None
        if sys.platform != "win32":
            try:
                import sounddevice as sd  # type: ignore
                self._sd = sd
            except ImportError:
                pass

    @property
    def available(self) -> bool:
        return sys.platform == "win32" or self._sd is not None

    def play(self, data):
        self.stop()
        if sys.platform == "win32":
            import winsound
            write_wav(self._tmp, data)
            winsound.PlaySound(str(self._tmp), winsound.SND_FILENAME | winsound.SND_ASYNC)
        elif self._sd is not None:
            from .render import SR
            self._sd.play(data, SR)
        else:
            raise RuntimeError("再生には sounddevice が必要です (pip install sounddevice)")

    def stop(self):
        if sys.platform == "win32":
            import winsound
            winsound.PlaySound(None, winsound.SND_PURGE)
        elif self._sd is not None:
            self._sd.stop()
