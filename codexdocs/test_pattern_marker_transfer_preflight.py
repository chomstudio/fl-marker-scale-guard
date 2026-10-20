"""実機検証スクリプトの入力検査と置換対象の限定を代替APIで確認する。"""

import copy
import json
import runpy
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPT = Path(__file__).with_name("Pattern Marker Transfer - Preflight Check.pyscript")


class Marker:
    """種別ごとの追加属性を持つ代替マーカー。"""

    def __init__(self, time=0, name="", mode=0):
        self.time = time
        self.name = name
        self.mode = mode
        self.tsnum = 3
        self.tsden = 4
        self.scale_root = 2
        self.scale_helper = "0,1,0,1,0,0,1,0,1,0,1,0"


class Score:
    """ノート操作を提供せず、呼ばれた場合はテストを失敗させる。"""

    PPQ = 96

    def __init__(self):
        self.markers = [
            Marker(0, "元の名前"),
            Marker(96, "拍子", 8),
            Marker(192, "キー", 12),
        ]

    @property
    def markerCount(self):
        """その時点のマーカー数を返す。"""
        return len(self.markers)

    def getMarker(self, index):
        """指定位置のマーカーを返す。"""
        return self.markers[index]

    def deleteMarker(self, index):
        """指定位置のマーカーだけを削除する。"""
        del self.markers[index]

    def addMarker(self, marker):
        """時刻順にマーカーを追加する。"""
        self.markers.append(marker)
        self.markers.sort(key=lambda m: m.time)


class PreflightTests(unittest.TestCase):
    """破壊的操作に進む条件と、ラベルの往復を確認する。"""

    def setUp(self):
        self.score = Score()
        self.logs = []
        api = types.SimpleNamespace(
            Marker=Marker,
            score=self.score,
            Utils=types.SimpleNamespace(log=self.logs.append, ShowMessage=self.fail),
        )
        with patch.dict(sys.modules, {"flpianoroll": api}):
            self.script = runpy.run_path(str(SCRIPT))
        self.initial = copy.deepcopy(self.score.markers)

    def apply_data(self, text):
        """必要な入力値を代替フォームへ渡す。"""
        values = {
            self.script["DATA"]: text,
        }
        self.script["apply"](types.SimpleNamespace(getInputValue=values.__getitem__))

    def data(self, rows):
        """入力検証用の暫定データを組み立てる。"""
        return json.dumps(
            {"format": "PMT-preflight-1", "ppq": 96, "mode": 0, "markers": rows}
        )

    def assert_unchanged(self):
        """全種別のマーカー値が保持されたことを確認する。"""
        self.assertEqual(
            [vars(m) for m in self.score.markers], [vars(m) for m in self.initial]
        )

    def test_empty_and_invalid_input_do_not_delete(self):
        for text in (
            "",
            " ",
            "{",
            "[]",
            self.data([{"time": -1, "name": "x"}]),
            self.data([{"time": True, "name": "x"}]),
            self.data([{"time": 0, "name": "x"}, {"time": 1, "name": None}]),
        ):
            with self.subTest(text=text):
                self.apply_data(text)
                self.assert_unchanged()

    def test_initial_data_does_not_replace(self):
        with patch.object(
            self.score, "deleteMarker", side_effect=AssertionError("削除不可")
        ):
            self.apply_data(self.script["_INITIAL_TEXT"])
        self.assert_unchanged()

    def test_ppq_and_mode_mismatch(self):
        for field, value in (("ppq", 480), ("mode", 8)):
            data = json.loads(self.data([]))
            data[field] = value
            self.apply_data(json.dumps(data))
            self.assert_unchanged()

    def test_replace_repeatedly_preserves_other_types(self):
        rows = [{"time": 48, "name": '日本語 | ; : " \\ 😀'}, {"time": 240, "name": ""}]
        for _ in range(3):
            self.apply_data(self.data(rows))
            actual = [
                {"time": m.time, "name": m.name}
                for m in self.score.markers
                if m.mode == 0
            ]
            self.assertEqual(actual, rows)
            self.assertEqual(
                [vars(m) for m in self.score.markers if m.mode != 0],
                [vars(m) for m in self.initial if m.mode != 0],
            )

    def test_empty_array_deletes_only_target_type(self):
        self.apply_data(self.data([]))
        self.assertEqual([m.mode for m in self.score.markers], [8, 12])

    def test_export_excludes_other_types_and_roundtrips(self):
        text = self.script["_INITIAL_TEXT"]
        rows = self.script["_decode"](text, 96, 0)
        self.assertEqual(rows, [{"time": 0, "name": "元の名前", "mode": 0}])

    def test_single_field_and_new_pattern_initial_value(self):
        controls = {}

        def dialog_factory(title, description):
            return types.SimpleNamespace(addInputText=controls.__setitem__)

        api = self.script["flp"]
        api.ScriptDialog = dialog_factory
        self.script["createDialog"]()
        self.assertEqual(controls, {self.script["DATA"]: self.script["_INITIAL_TEXT"]})
        self.score.markers[0].name = "別パターンの現在値"
        with patch.dict(sys.modules, {"flpianoroll": api}):
            other = runpy.run_path(str(SCRIPT))
        self.assertNotEqual(other["DATA"], self.script["DATA"])
        controls.clear()
        other["createDialog"]()
        self.assertEqual(len(controls), 1)
        self.assertIn("別パターンの現在値", controls[other["DATA"]])


if __name__ == "__main__":
    unittest.main()
