# stacks

ドキュメント（PDF/PPTX/DOCX/XLSX）をSQLiteに取り込み、embeddingで意味検索する。

## 特徴

- **ネイティブテキスト抽出** — PPTX（オートシェイプ含む）、DOCX、XLSXは直接解析。PDFはpdfminer.sixでCJKエンコーディングにも対応
- **ハイブリッド検索** — ベクトル類似度（multilingual-e5-small + sqlite-vec）と全文検索（FTS5 + fugashi形態素解析）を統合。意味的な検索とキーワード一致の両方に対応。日本語は形態素単位でインデックスされるため「東京」で「東京都」がヒットする
- **HTMLレポート** — 検索結果をページ画像付きでブラウザ表示。前後ページナビゲーション、クエリ語ハイライト、元ファイル・PDFページへのリンク
- **品質スコア** — 取り込み時にページごとの品質を自動計算。文字化け・ゴミページを後から特定可能
- **一括取り込み** — `ingest` コマンドでディレクトリ配下のファイルをまとめて処理

## セットアップ

```bash
git clone https://github.com/Flowers-of-Romance/stacks.git
cd stacks
pip install -e .
```

依存パッケージ（`sentence-transformers`, `sqlite-vec`, `openpyxl`, `pdfminer.six`, `python-pptx`, `python-docx`, `pymupdf`, `fugashi`, `unidic-lite`）は `pip install -e .` で自動インストールされる。

初回のembedding計算時にモデル（multilingual-e5-small, 約100MB）が自動ダウンロードされる。

## 使い方

### 1. 初期化

```bash
stacks init
```

`stacks.db`がカレントディレクトリに作成される。`STACKS_ROOT`環境変数で場所を変更可能。

既存データを全削除してやり直す場合:

```bash
stacks init --reset
```

### 2. ドキュメントの取り込み

```bash
# ディレクトリ配下を一括取り込み
stacks ingest docs/

# 単一ファイル
stacks ingest report.pdf

# 画像生成なし（テキスト+embeddingのみ、高速）
stacks ingest docs/ --no-images
```

処理の流れ: ファイル検出 → テキスト抽出（ページ単位）→ ページ画像生成 → embedding計算 → SQLiteに保存。

同一ファイル（SHA-256ハッシュで判定）は重複取り込みしない。

取り込み中はファイル番号とフェーズ（テキスト抽出・画像生成・embedding）が表示される:

```
[1/5] docs/report.pdf
  extracting text...
  generating images...
  images: 31 pages
  embed: 31/31
```

### 3. 検索

```bash
stacks search "政府相互運⽤性フレームワーク"
stacks search "フォローアップの実施" --limit 10
```

ベクトル類似度と全文検索を組み合わせたハイブリッド検索。意味的に近いページも、キーワードが一致するページもヒットする。トップスコアの30%未満の低関連度結果は自動で除外される。

#### CLI出力

```
📄 report.pdf (p.8) [score: 0.548]
  …政府相互運⽤性フレームワーク（GIF）との整合性確保…
  -> C:\stacks\file\report.pdf
```

#### HTMLレポート

検索すると自動でHTMLレポートが生成される（`.stacks/search_<クエリ>.html`）。
ページ画像がある場合はブラウザが自動で開く。

```bash
# ブラウザ自動オープンを抑制
stacks search "query" --no-browser
```

HTMLレポートの機能:

- **ページ画像** — ヒットしたページのサムネイル画像をテキストと横並び表示
- **前後ナビゲーション** — ◀ ▶ ボタンで前後ページの画像を確認
- **クエリ語ハイライト** — 検索語が黄色で強調表示
- **PDFハイライト** — `PDF p.N` リンクをクリックすると、検索語が黄色でハイライトされたPDFコピーが開く（元PDFは変更しない。`.stacks/highlighted/` にキャッシュ）。ベクトル検索のみでヒットした結果（exact termなし）はハイライトなしの元PDFにリンク
- **元ファイルパスコピー** — ファイル名クリックでパスをクリップボードにコピー（XLSX/PPTX/DOCXはブラウザから直接開けないため）
- **クエリ別保存** — 検索ごとに別ファイルで保存。同じクエリなら上書き

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
| `init` | データベースを初期化（`--reset` で全削除して再作成） |
| `ingest <path>` | ファイル/ディレクトリを一括取り込み（`--no-images` で画像スキップ） |
| `prepare <path>` | ファイルの検出・変換（取り込みはしない） |
| `store <doc_id> <page_num>` | JSONからページを個別保存 |
| `search <query>` | 意味検索（`--limit N`, `--no-browser`） |
| `list` | 取り込み済みドキュメント一覧 |
| `info <doc_id>` | ドキュメント詳細 |
| `quality` | 低品質ページ一覧（`--threshold` で閾値変更） |
| `serve` | embeddingサーバー起動（`--port` でポート変更） |
| `rebuild-fts` | FTSインデックスを形態素解析で再構築 |
| `remove <doc_id>` | ドキュメントとページを削除 |

## 対応形式

| 形式 | テキスト抽出 | ページ画像 |
|------|------------|-----------|
| PDF | pdfminer.six（CJK対応） | PyMuPDF直接レンダリング |
| PPTX | python-pptx（オートシェイプ・テーブル含む） | LibreOffice→PDF→PyMuPDF |
| DOCX | python-docx（段落・テーブル） | LibreOffice→PDF→PyMuPDF |
| XLSX | openpyxl + drawing XML（大きなシートは自動チャンク分割） | LibreOffice→PDF→PyMuPDF |

## ディレクトリ構成

```
$STACKS_ROOT/
├── stacks.db                    # メインDB（テキスト・embedding・メタデータ）
└── .stacks/
    ├── converted/               # LibreOfficeで変換されたPDF
    ├── highlighted/             # 検索語ハイライト付きPDFコピー（キャッシュ）
    ├── images/                  # ページ画像（サムネイルPNG、幅600px）
    │   ├── 1/                   # doc_id=1
    │   │   ├── 1.png            # ページ1
    │   │   ├── 2.png            # ページ2
    │   │   └── ...
    │   └── 2/
    └── search_<query>.html      # 検索結果HTMLレポート
```

## 設定

| 環境変数 | 説明 | デフォルト |
|---------|------|-----------|
| `STACKS_ROOT` | ルートディレクトリ | カレントディレクトリ |

## 技術スタック

- Python 3.10+
- SQLite + [sqlite-vec](https://github.com/asg017/sqlite-vec)
- [sentence-transformers](https://www.sbert.net/)（multilingual-e5-small, 384次元）
- [PyMuPDF](https://pymupdf.readthedocs.io/)（PDF→PNG画像レンダリング）
- [fugashi](https://github.com/polm/fugashi)（MeCab形態素解析 → FTS5トークナイズ）
- pdfminer.six / python-pptx / python-docx / openpyxl
