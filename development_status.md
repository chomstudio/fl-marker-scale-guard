# 開発状況書

## 現在の段階

Marker Scale Guard本体のローカル実装と自動テストが完了し、FL Studio上での受け入れ確認待ちです。

## 実装済み

- 実機確認用スクリプト`Marker Scale Guard - Preflight Check.pyscript`
- 実機確認ガイド`Marker Scale Guard - Preflight Check.md`
- 本体スクリプト`Marker Scale Guard.pyscript`
- 利用ガイド`Marker Scale Guard.md`
- FL Studio APIの代替オブジェクトを使用した自動テスト`tests/test_marker_scale_guard.py`

## 検証済み

- 公式Piano roll Scripting APIと、使用するAPIの名称・公開仕様を照合済み
- 実機確認用スクリプトのローカルPython構文検証に合格
- `createDialog()`定義前にノートとマーカーを走査可能
- `getNote()`で取得したノートの`number`と`selected`を直接変更可能
- ノート番号`131`をscoreへ追加し、同じ番号で読み戻し可能
- 同一パターンの異なる2チャンネルから、通常マーカー`384:C_(ad5)`および`1152:G_(ab5)`を同じ順序で取得可能
- ダイアログ操作中の変更プレビューが、右上の閉じるボタンで閉じた後にロールバックされることを確認
- FL Studio `v26.1.3 [build 5570]`、PPQ 96で実機確認を完了
- `markerCount`は走査前にローカル変数へ保存し、走査中は保存した値を使用する方針を確定
- マーカー文法、コード構成音、メジャースケール変換を自動テスト済み
- マーカー区間、同時刻マーカー、開始位置判定、無効マーカー無視を自動テスト済み
- 矛盾警告、ミストーン検出、移動、衝突判定、選択、削除を自動テスト済み
- 自動テスト21件がすべて成功
- 本体、実機確認用スクリプト、テストコードのPython構文検証に合格

## 未実装

- FL Studio上での本体受け入れ確認

## 既知の問題

- 現時点で既知の問題なし

## 次に行う作業

1. `Marker Scale Guard.pyscript`をFL Studioのユーザースクリプトフォルダへ配置する
2. FL Studio上で3種類の処理とキャンセル時ロールバックを確認する
3. 仕様書第13節の受け入れ条件を実機で確認する

## 保留中の判断

- FL Studio実機上での本体スクリプト最終確認結果
