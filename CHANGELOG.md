# Changelog

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
