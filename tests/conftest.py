import pytest


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    """テストが本物の ~/.gagaku_player(プラグイン・設定)に触れないようにする。"""
    home = tmp_path / "gagaku_home"
    monkeypatch.setenv("GAGAKU_PLAYER_HOME", str(home))
    return home
