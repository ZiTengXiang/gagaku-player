from fractions import Fraction as F

import pytest

staffview = pytest.importorskip("gagaku.staffview")  # tkinter がない環境では飛ばす


def test_note_step():
    assert staffview.note_step("C4") == (28, False)
    assert staffview.note_step("F#4") == (31, True)


@pytest.mark.parametrize("start, dur, expected", [
    (F(0), F(4), [(F(0), F(4))]),
    (F(0), F(3), [(F(0), F(3))]),
    (F(1), F(2), [(F(1), F(1)), (F(2), F(1))]),            # 2拍目からの2分音符は拍で切る
    (F(1, 2), F(1), [(F(1, 2), F(1, 2)), (F(1), F(1, 2))]),  # 拍をまたぐ音
    (F(3), F(2), [(F(3), F(1)), (F(4), F(1))]),            # 小節をまたぐ音
])
def test_split_values(start, dur, expected):
    bars = [(F(0), F(4)), (F(4), F(8))]
    assert staffview.split_values(start, dur, bars) == expected
