# stacks

ドキュメント（PDF/PPTX/DOCX/XLSX）をSQLiteに取り込み、embeddingで意味検索する。

## 特徴

- **ネイティブテキスト抽出** — PPTX（オートシェイプ含む）、DOCX、XLSXは直接解析。PDFはpdfminer.sixでCJKエンコーディングにも対応
- **ハイブリッド検索** — ベクトル類似度（multilingual-e5-small + sqlite-vec）と全文検索（FTS5）を統合。意味的な検索とキーワード一致の両方に対応
- **品質スコア** — 取り込み時にページごとの品質を自動計算。文字化け・ゴミページを後から特定可能
- **一括取り込み** — `ingest` コマンドでディレクトリ配下のファイルをまとめて処理

## セットアップ

```bash
git clone https://github.com/Flowers-of-Romance/stacks.git
cd stacks
pip install -e .
```

依存パッケージ（`sentence-transformers`, `sqlite-vec`, `openpyxl`, `pdfminer.six`, `python-pptx`, `python-docx`）は `pip install -e .` で自動インストールされる。

初回のembedding計算時にモデル（multilingual-e5-small, 約100MB）が自動ダウンロードされる。

## 使い方

### 1. 初期化

```bash
stacks init
```

`stacks.db`がカレントディレクトリに作成される。`STACKS_ROOT`環境変数で場所を変更可能。

### 2. ドキュメントの取り込み

```bash
# ディレクトリ配下を一括取り込み
stacks ingest docs/

# 単一ファイル
stacks ingest report.pdf
```

処理の流れ: ファイル検出 → テキスト抽出（ページ単位）→ embedding計算 → SQLiteに保存。

1000ページを超えるファイルは自動でスキップされる。同一ファイル（SHA-256ハッシュで判定）は重複取り込みしない。

### 3. 検索

```bash
stacks search "政府相互運⽤性フレームワーク"
stacks search "フォローアップの実施" --limit 10
```

ベクトル類似度と全文検索を組み合わせたハイブリッド検索。意味的に近いページも、キーワードが一致するページもヒットする。スコアは1.0に近いほど関連度が高い。

検索を高速化するには、別ターミナルでembeddingサーバーを起動する。

```bash
stacks serve
```

### 4. 管理

```bash
# 取り込み済みドキュメント一覧
stacks list

# ドキュメント詳細（ページ一覧）
stacks info 1

# ドキュメント削除（ページ・embeddingも削除）
stacks remove 1
```

### 5. 品質チェック

```bash
# 品質スコア 0.5 未満のページを表示
stacks quality

# 閾値を変更
stacks quality --threshold 0.7
```

取り込み時にページごとの品質スコア（0.0〜1.0）を自動計算・記録している。文字化けや内容が薄いページを後から特定できる。

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
| `serve` | embeddingサーバー起動（`--port` でポート変更） |
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
