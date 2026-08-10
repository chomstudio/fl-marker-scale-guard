"""Marker Scale GuardのFL Studio非依存部分とscore操作を検証する。"""

from pathlib import Path
import sys
import types
import unittest


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "Marker Scale Guard.pyscript"


class FakeNote:
    """テストで使用するノートオブジェクト。"""

    def __init__(self, number=60, time=0, length=96, selected=False):
        # FL StudioのNoteで本実装が参照するプロパティを初期化する。
        self.number = number
        self.time = time
        self.length = length
        self.selected = selected
        self.velocity = 0.8
        self.color = 0


class FakeMarker:
    """テストで使用するマーカーオブジェクト。"""

    def __init__(self, name, time):
        # FL StudioのMarkerで本実装が参照するプロパティを初期化する。
        self.name = name
        self.time = time


class FakeScore:
    """必要最小限のscore APIを再現する。"""

    def __init__(self, notes=None, markers=None):
        # テストごとに独立したノートとマーカーを保持する。
        self.notes = list(notes or [])
        self.markers = list(markers or [])
        self.PPQ = 96

    @property
    def noteCount(self):
        # 現在保持しているノート数を返す。
        return len(self.notes)

    @property
    def markerCount(self):
        # 現在保持しているマーカー数を返す。
        return len(self.markers)

    def getNote(self, index):
        # 指定インデックスのノートを参照として返す。
        return self.notes[index]

    def getMarker(self, index):
        # 指定インデックスのマーカーを参照として返す。
        return self.markers[index]

    def deleteNote(self, index):
        # 指定インデックスのノートを削除する。
        del self.notes[index]

    def addNote(self, note):
        # 渡されたノートをscoreの末尾へ追加する。
        self.notes.append(note)


class FakeUtils:
    """ログとメッセージを記録するUtils代替。"""

    def __init__(self):
        # 表示結果をテストから検査できるリストへ保存する。
        self.logs = []
        self.messages = []

    def log(self, message):
        # Debugging log相当の文字列を記録する。
        self.logs.append(message)

    def ShowMessage(self, message):
        # モーダルメッセージ相当の文字列を記録する。
        self.messages.append(message)


class FakeDialog:
    """コンボボックスの値を保持するScriptDialog代替。"""

    def __init__(self, title, description):
        # ダイアログの表示文字列と入力定義を保存する。
        self.title = title
        self.description = description
        self.values = {}

    def addInputCombo(self, name, options, default_index):
        # 指定された既定値を入力値として記録する。
        self.values[name] = default_index
        self.options = list(options)

    def addInputCheckbox(self, name, default_value):
        # チェックボックスの既定値を入力値として記録する。
        self.values[name] = bool(default_value)

    def getInputValue(self, name):
        # apply()が参照する現在値を返す。
        return self.values[name]


def load_script(notes=None, markers=None):
    # 偽のflpianorollモジュールを注入し、pyscriptを通常実行と同じ順序で読み込む。
    fake_flp = types.ModuleType("flpianoroll")
    fake_flp.score = FakeScore(notes, markers)
    fake_flp.Utils = FakeUtils()
    fake_flp.Note = FakeNote
    fake_flp.ScriptDialog = FakeDialog

    previous_module = sys.modules.get("flpianoroll")
    sys.modules["flpianoroll"] = fake_flp
    try:
        namespace = {
            "__name__": "marker_scale_guard_under_test",
            "__file__": str(SCRIPT_PATH),
        }
        source = SCRIPT_PATH.read_text(encoding="utf-8")
        exec(compile(source, str(SCRIPT_PATH), "exec"), namespace)
    finally:
        if previous_module is None:
            del sys.modules["flpianoroll"]
        else:
            sys.modules["flpianoroll"] = previous_module
    return namespace, fake_flp


class MarkerParsingTests(unittest.TestCase):
    """マーカー文法と音集合の変換を検証する。"""

    def test_supported_chord_forms_are_parsed(self):
        # 基本品質と各修飾が仕様どおり受理されることを確認する。
        module, _ = load_script()
        valid_names = [
            "C",
            "Cm",
            "Cdim",
            "Caug",
            "C6",
            "Cm7",
            "CM7",
            "CdimM7",
            "Caugsus4",
            "Cm-5",
            "Bb7_(ad5)",
            "Am_(101011010101)",
            "F#_(G)",
        ]
        for name in valid_names:
            with self.subTest(name=name):
                parsed, reason = module["_parse_marker_name"](name, 0, 0)
                self.assertIsNotNone(parsed)
                self.assertIsNone(reason)

    def test_invalid_marker_forms_are_rejected(self):
        # 空白、テンション、非ASCII表記、情報の桁違いを拒否することを確認する。
        module, _ = load_script()
        invalid_names = [
            " C",
            "C ",
            "C9",
            "H",
            "c",
            "C_(ad)",
            "C_(minor)",
            "C_(10101101010)",
            "C_(101011010102)",
        ]
        for name in invalid_names:
            with self.subTest(name=name):
                parsed, reason = module["_parse_marker_name"](name, 0, 0)
                self.assertIsNone(parsed)
                self.assertIsNotNone(reason)

    def test_scale_masks_match_specification(self):
        # CメジャーとGメジャーのキー指定が仕様書の16進数と一致することを確認する。
        module, _ = load_script()
        parse = module["_parse_marker_name"]
        c_key, _ = parse("C_(C)", 0, 0)
        c_binary, _ = parse("C_(101011010101)", 0, 0)
        g_key, _ = parse("G_(G)", 0, 0)
        g_hex, _ = parse("G_(ab5)", 0, 0)
        self.assertEqual(c_key["scale_mask"], 0xAD5)
        self.assertEqual(c_binary["scale_mask"], 0xAD5)
        self.assertEqual(g_key["scale_mask"], 0xAB5)
        self.assertEqual(g_key["scale_mask"], g_hex["scale_mask"])

    def test_chord_modifiers_follow_mechanical_rules(self):
        # sus4と減5度の置換、および7度追加をピッチクラスで確認する。
        module, _ = load_script()
        parse = module["_parse_marker_name"]
        sus4, _ = parse("Cmsus4", 0, 0)
        diminished_fifth, _ = parse("Cdim-5", 0, 0)
        minor_seventh, _ = parse("Cm7", 0, 0)
        self.assertEqual(sus4["chord_pitch_classes"], {0, 5, 7})
        self.assertEqual(diminished_fifth["chord_pitch_classes"], {0, 3, 5})
        self.assertEqual(minor_seventh["chord_pitch_classes"], {0, 3, 7, 10})


class DetectionTests(unittest.TestCase):
    """マーカー区間とミストーン検出を検証する。"""

    def test_invalid_markers_do_not_split_intervals(self):
        # 無効マーカーを無視し、次の有効マーカーまで前区間が続くことを確認する。
        notes = [
            FakeNote(61, 50),
            FakeNote(61, 150),
            FakeNote(66, 250),
        ]
        markers = [
            FakeMarker("C_(ad5)", 100),
            FakeMarker("invalid", 200),
            FakeMarker("G_(ab5)", 300),
        ]
        module, fake_flp = load_script(notes, markers)
        detected_indices = [note["score_index"] for note in module["_STATE"]["mistones"]]
        self.assertEqual(detected_indices, [1, 2])
        self.assertTrue(any("無効なマーカー" in line for line in fake_flp.Utils.logs))

    def test_marker_at_same_time_uses_later_score_index(self):
        # 同時刻の後方マーカーがノート開始時刻ちょうどから適用されることを確認する。
        notes = [FakeNote(66, 100)]
        markers = [
            FakeMarker("C_(ad5)", 100),
            FakeMarker("G_(ab5)", 100),
        ]
        module, _ = load_script(notes, markers)
        self.assertEqual(module["_STATE"]["mistones"], [])
        self.assertEqual(module["_STATE"]["active_markers"][0]["name"], "G_(ab5)")

    def test_note_uses_marker_at_its_start(self):
        # 区間をまたぐノートと最初のマーカー前のノートを開始位置だけで判定する。
        notes = [
            FakeNote(61, 50, 200),
            FakeNote(61, 100, 200),
            FakeNote(66, 290, 100),
        ]
        markers = [
            FakeMarker("C_(ad5)", 100),
            FakeMarker("G_(ab5)", 300),
        ]
        module, _ = load_script(notes, markers)
        detected_indices = [note["score_index"] for note in module["_STATE"]["mistones"]]
        self.assertEqual(detected_indices, [1, 2])

    def test_chromatic_marker_detects_nothing(self):
        # コード名だけのマーカーがクロマチックスケールとして扱われることを確認する。
        module, fake_flp = load_script(
            [FakeNote(61, 0)],
            [FakeMarker("C", 0)],
        )
        self.assertEqual(module["_STATE"]["mistones"], [])
        self.assertIn("対象のノートは見つかりませんでした。", fake_flp.Utils.messages)

    def test_no_valid_marker_finishes_without_dialog_or_message(self):
        # 有効マーカーがない場合、処理用関数も通常メッセージも生成しないことを確認する。
        module, fake_flp = load_script(
            [FakeNote(61, 0)],
            [FakeMarker("invalid", 0)],
        )
        self.assertNotIn("createDialog", module)
        self.assertNotIn("apply", module)
        self.assertEqual(fake_flp.Utils.messages, [])

    def test_c_major_detects_only_outside_pitch_classes(self):
        # Cメジャーの12音から仕様で定めた5つのスケール外音だけを検出する。
        notes = [FakeNote(60 + pitch_class, pitch_class * 96) for pitch_class in range(12)]
        module, _ = load_script(notes, [FakeMarker("C_(ad5)", 0)])
        detected_pitch_classes = {
            note["number"] % 12 for note in module["_STATE"]["mistones"]
        }
        self.assertEqual(detected_pitch_classes, {1, 3, 6, 8, 10})

    def test_conflict_warning_is_combined(self):
        # 複数の矛盾をマーカー名、tick、構成音付きの1メッセージへ集約する。
        markers = [
            FakeMarker("D7_(C)", 100),
            FakeMarker("E_(C)", 200),
        ]
        _, fake_flp = load_script([], markers)
        self.assertEqual(len(fake_flp.Utils.messages), 2)
        warning = fake_flp.Utils.messages[0]
        self.assertIn("D7_(C) / tick 100: F#", warning)
        self.assertIn("E_(C) / tick 200: G#", warning)


class ProcessingTests(unittest.TestCase):
    """移動、選択、削除と衝突判定を検証する。"""

    def test_adjacent_chord_tone_prefers_upward(self):
        # 半音上下がともにコード音なら高音側へ移動することを確認する。
        notes = [FakeNote(61, 0)]
        markers = [FakeMarker("D7_(000)", 0)]
        module, fake_flp = load_script(notes, markers)
        module["_move_or_delete_mistones"](
            module["_STATE"]["mistones"], module["_STATE"]["note_count"]
        )
        self.assertEqual(fake_flp.score.notes[0].number, 62)

    def test_adjacent_collision_uses_other_direction(self):
        # 高音側が衝突するとき、衝突しない低音側のコード音を選ぶことを確認する。
        notes = [FakeNote(61, 0, 96), FakeNote(62, 0, 96)]
        markers = [FakeMarker("Cdim_(000)", 0)]
        module, fake_flp = load_script(notes, markers)
        mistone = module["_STATE"]["mistones"][0]
        destination = module["_choose_destination"](mistone, len(notes))
        self.assertEqual(destination, 60)

    def test_touching_intervals_do_not_collide(self):
        # 一方の終了と他方の開始が一致するだけなら同音程候補を許可する。
        notes = [FakeNote(61, 0, 96), FakeNote(62, 96, 96)]
        markers = [FakeMarker("D7_(000)", 0)]
        module, _ = load_script(notes, markers)
        mistone = module["_STATE"]["mistones"][0]
        destination = module["_choose_destination"](mistone, len(notes))
        self.assertEqual(destination, 62)

    def test_partially_overlapping_interval_collides(self):
        # 発音区間が一部分だけ重なる同音程ノートも衝突として扱う。
        notes = [FakeNote(61, 0, 96), FakeNote(62, 48, 96)]
        markers = [FakeMarker("D7_(000)", 0)]
        module, _ = load_script(notes, markers)
        mistone = module["_STATE"]["mistones"][0]
        destination = module["_choose_destination"](mistone, len(notes))
        self.assertEqual(destination, 60)

    def test_fallback_scale_tone_prefers_upward_at_equal_distance(self):
        # 隣接コード音がない場合、同距離の非コード・スケール音から高音側を選ぶ。
        notes = [FakeNote(70, 0)]
        markers = [FakeMarker("C_(ad5)", 0)]
        module, _ = load_script(notes, markers)
        mistone = module["_STATE"]["mistones"][0]
        destination = module["_choose_destination"](mistone, len(notes))
        self.assertEqual(destination, 71)

    def test_unmovable_note_is_deleted(self):
        # スケール音がなく隣接コード音も衝突するとき、対象ノートを削除する。
        notes = [
            FakeNote(61, 0, 96),
            FakeNote(62, 0, 96),
            FakeNote(60, 0, 96),
        ]
        markers = [FakeMarker("Cdim_(000)", 0)]
        module, fake_flp = load_script(notes, markers)
        first_mistone = [module["_STATE"]["mistones"][0]]
        module["_move_or_delete_mistones"](first_mistone, len(notes))
        self.assertEqual([note.number for note in fake_flp.score.notes], [62, 60])

    def test_processing_order_includes_previous_move(self):
        # 同時刻の検出ノートをscore順に処理し、先行する移動結果を次の衝突判定へ含める。
        notes = [FakeNote(61, 0, 96), FakeNote(61, 0, 96)]
        markers = [FakeMarker("D7_(000)", 0)]
        module, fake_flp = load_script(notes, markers)
        module["_move_or_delete_mistones"](
            module["_STATE"]["mistones"], module["_STATE"]["note_count"]
        )
        self.assertEqual([note.number for note in fake_flp.score.notes], [62, 60])

    def test_forced_chord_uses_nearest_candidate(self):
        # 強制時は通常のスケール音ではなく最寄りのコード構成音を選ぶ。
        notes = [FakeNote(66, 0, 96)]
        markers = [FakeMarker("C_(ad5)", 0)]
        module, _ = load_script(notes, markers)
        mistone = module["_STATE"]["mistones"][0]
        destination = module["_choose_forced_chord_destination"](mistone, len(notes))
        self.assertEqual(destination, 67)

    def test_forced_chord_tries_next_candidate_after_collision(self):
        # 最寄りのコード音が衝突する場合は、次に近いコード音を使用する。
        notes = [FakeNote(66, 0, 96), FakeNote(67, 0, 96)]
        markers = [FakeMarker("C_(ad5)", 0)]
        module, _ = load_script(notes, markers)
        mistone = module["_STATE"]["mistones"][0]
        destination = module["_choose_forced_chord_destination"](mistone, len(notes))
        self.assertEqual(destination, 64)

    def test_forced_chord_prefers_upward_at_equal_distance(self):
        # 強制候補が同距離で上下にある場合は高音側を優先する。
        notes = [FakeNote(61, 0, 96)]
        markers = [FakeMarker("D7_(000)", 0)]
        module, _ = load_script(notes, markers)
        mistone = module["_STATE"]["mistones"][0]
        destination = module["_choose_forced_chord_destination"](mistone, len(notes))
        self.assertEqual(destination, 62)

    def test_forced_chord_deletes_when_all_candidates_collide(self):
        # ±6以内にあるすべてのコード音が埋まっている場合は対象ノートを削除する。
        notes = [
            FakeNote(66, 0, 96),
            FakeNote(67, 0, 96),
            FakeNote(64, 0, 96),
            FakeNote(72, 0, 96),
            FakeNote(60, 0, 96),
        ]
        markers = [FakeMarker("C_(ad5)", 0)]
        module, fake_flp = load_script(notes, markers)
        first_mistone = [module["_STATE"]["mistones"][0]]
        module["_move_or_delete_mistones"](first_mistone, len(notes), True)
        self.assertEqual([note.number for note in fake_flp.score.notes], [67, 64, 72, 60])

    def test_forced_chord_keeps_existing_chord_tone(self):
        # 矛盾スケールで検出された音がすでにコード音なら距離0の候補として維持する。
        notes = [FakeNote(60, 0, 96)]
        markers = [FakeMarker("C_(000)", 0)]
        module, _ = load_script(notes, markers)
        mistone = module["_STATE"]["mistones"][0]
        destination = module["_choose_forced_chord_destination"](mistone, len(notes))
        self.assertEqual(destination, 60)

    def test_selection_replaces_existing_selection(self):
        # 既存選択を解除し、検出されたノートだけを選択することを確認する。
        notes = [FakeNote(60, 0, selected=True), FakeNote(61, 96)]
        markers = [FakeMarker("C_(ad5)", 0)]
        module, fake_flp = load_script(notes, markers)
        module["_select_mistones"](
            module["_STATE"]["mistones"], module["_STATE"]["note_count"]
        )
        self.assertEqual([note.selected for note in fake_flp.score.notes], [False, True])

    def test_delete_removes_only_detected_notes(self):
        # 複数の検出ノートを降順で削除し、スケール内ノートを残すことを確認する。
        notes = [FakeNote(61, 0), FakeNote(60, 96), FakeNote(63, 192)]
        markers = [FakeMarker("C_(ad5)", 0)]
        module, fake_flp = load_script(notes, markers)
        module["_delete_mistones"](module["_STATE"]["mistones"])
        self.assertEqual([note.number for note in fake_flp.score.notes], [60])

    def test_dialog_defaults_to_move_operation(self):
        # ミストーンがある場合だけ3項目のダイアログを作り、移動を既定値にする。
        module, _ = load_script(
            [FakeNote(61, 0)],
            [FakeMarker("C_(ad5)", 0)],
        )
        form = module["createDialog"]()
        self.assertEqual(form.options, module["PROCESS_OPTIONS"])
        self.assertEqual(form.getInputValue(module["PROCESS_INPUT_NAME"]), 0)
        self.assertFalse(form.getInputValue(module["FORCE_CHORD_INPUT_NAME"]))

    def test_apply_uses_forced_chord_checkbox_for_move(self):
        # 移動処理でチェックをオンにすると通常候補ではなくコード音へ強制する。
        module, fake_flp = load_script(
            [FakeNote(70, 0)],
            [FakeMarker("C_(ad5)", 0)],
        )
        form = module["createDialog"]()
        form.values[module["FORCE_CHORD_INPUT_NAME"]] = True
        module["apply"](form)
        self.assertEqual(fake_flp.score.notes[0].number, 72)

    def test_force_checkbox_does_not_change_selection_operation(self):
        # 選択処理では強制チェックを無視し、音程を変えず検出ノートだけを選択する。
        module, fake_flp = load_script(
            [FakeNote(70, 0)],
            [FakeMarker("C_(ad5)", 0)],
        )
        form = module["createDialog"]()
        form.values[module["PROCESS_INPUT_NAME"]] = 1
        form.values[module["FORCE_CHORD_INPUT_NAME"]] = True
        module["apply"](form)
        self.assertEqual(fake_flp.score.notes[0].number, 70)
        self.assertTrue(fake_flp.score.notes[0].selected)


if __name__ == "__main__":
    # ファイルを直接実行した場合も標準のunittestランナーを使用する。
    unittest.main()
