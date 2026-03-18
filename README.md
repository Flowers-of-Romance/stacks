# stacks

ドキュメント（PDF/PPTX/DOCX/XLSX）をSQLiteに取り込み、embeddingで意味検索する。

## 特徴

- **ネイティブテキスト抽出** — PPTX（オートシェイプ含む）、DOCX、XLSXは直接解析。PDFはpdfminer.sixでCJKエンコーディングにも対応
- **ベクトル検索** — multilingual-e5-small (384次元) + sqlite-vec によるセマンティック検索
- **品質スコア** — 取り込み時にページごとの品質を自動計算。文字化け・ゴミページを後から特定可能
- **一括取り込み** — `ingest` コマンドでディレクトリ配下のファイルをまとめて処理

## セットアップ

```bash
pip install -e .
pip install python-pptx python-docx pdfminer.six
```

## 使い方

```bash
# データベース初期化
stacks init

# ファイルを一括取り込み（テキスト抽出 → embedding → 保存）
stacks ingest docs/

# 意味検索
stacks search "暇"

# 取り込み済みドキュメント一覧
stacks list

# ドキュメント詳細
stacks info 1

# 低品質ページの確認
stacks quality                  # スコア 0.5 未満
stacks quality --threshold 0.7  # スコア 0.7 未満

# ドキュメント削除
stacks remove 1
```

## コマンド一覧

| コマンド | 説明 |
|---------|------|
| `init` | データベースを初期化 |
| `ingest <path>` | ファイル/ディレクトリを一括取り込み |
| `prepare <path>` | ファイルの検出・変換（取り込みはしない） |
| `store <doc_id> <page_num>` | JSONからページを個別保存 |
| `search <query>` | 意味検索（`--limit N` で件数指定） |
| `list` | 取り込み済みドキュメント一覧 |
| `info <doc_id>` | ドキュメント詳細 |
| `quality` | 低品質ページ一覧（`--threshold` で閾値変更） |
| `remove <doc_id>` | ドキュメントとページを削除 |

## 対応形式

| 形式 | 抽出方法 |
|------|---------|
| PDF | pdfminer.six（CJK対応） |
| PPTX | python-pptx（オートシェイプ・テーブル含む） |
| DOCX | python-docx（段落・テーブル） |
| XLSX | openpyxl + drawing XML（シートごとに1ページ、オートシェイプ含む） |

## 設定

| 環境変数 | 説明 | デフォルト |
|---------|------|-----------|
| `STACKS_ROOT` | ルートディレクトリ | カレントディレクトリ |

データベースは `$STACKS_ROOT/stacks.db` に作成される。

## 技術スタック

- Python 3.10+
- SQLite + [sqlite-vec](https://github.com/asg017/sqlite-vec)
- [sentence-transformers](https://www.sbert.net/)（multilingual-e5-small, 384次元）
- pdfminer.six / python-pptx / python-docx / openpyxl
