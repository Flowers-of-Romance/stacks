# Changelog

## 0.0.3 — 2026-03-19

- ハイブリッド検索（ベクトル + FTS5全文検索）。短いキーワードでも確実にヒット
- `serve` コマンド追加（embeddingサーバー常駐で検索高速化）
- 検索結果のsnippetをクエリ語の周辺から切り出すように改善
- scoreを関連度表示（1に近いほど良い）に変更
- torch/safetensorsの警告出力を抑制

## 0.0.2 — 2026-03-19

- xlsxのオートシェイプからテキスト抽出（drawing XML直接解析）
- PDFテキスト抽出をpypdfからpdfminer.sixに切り替え（CJKエンコーディング対応）
- pptx/docx/xlsxのネイティブテキスト抽出（LibreOffice不要に）
- `ingest` コマンド追加（一括取り込み）
- ページ品質スコア記録・`quality` コマンド追加
- ingest時のページ数上限（1000ページ）

## 0.0.1 — 2026-03-18

- 初版
- PDF/PPTX/DOCX/XLSX対応
- SQLite + sqlite-vec によるベクトル検索
- multilingual-e5-small (384次元) embedding
- CLI: init, prepare, store, search, list, remove, info
