"""雅楽譜プレイヤー 起動スクリプト:  python main.py [譜面ファイル.gaku]

pythonw(コンソールなし)で起動して落ちた場合は、error.log に記録してダイアログを出す。
"""
import sys
import traceback
from pathlib import Path


def _report_crash():
    log = Path(__file__).resolve().parent / "error.log"
    log.write_text(traceback.format_exc(), encoding="utf-8")
    try:
        from tkinter import Tk, messagebox
        root = Tk()
        root.withdraw()
        messagebox.showerror("雅楽譜プレイヤー", f"起動に失敗しました。詳細: {log}")
        root.destroy()
    except Exception:  # noqa: BLE001
        pass


if __name__ == "__main__":
    try:
        from gagaku.gui import main
        main(sys.argv[1] if len(sys.argv) > 1 else None)
    except Exception:  # noqa: BLE001
        _report_crash()
        raise
