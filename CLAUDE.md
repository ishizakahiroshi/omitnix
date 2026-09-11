<!-- このファイルはプロジェクト固有ルールのみを書く。個人/グローバル AI ルール
（言語・確認スタイル・出力フォーマット等）は各 AI ツールのグローバル設定へ。
fresh public clone でも有効な内容に保つこと。 -->

# omitnix 開発ガイド

> **このファイルは索引であって本文ではない。** 全 AI セッションで全文がロードされるので、
> ルールの本文はここへ書かず、破る人が必ず開く場所（コード・検査スクリプト・skill・guide・台帳）へ置き、
> ここには索引の 1 行だけを残す。新しいルールを足す前に既存の CLAUDE.md・skill・guide・台帳を検索し、
> 正本が既にあれば参照だけにする。詳細は下記「設計原則の索引」。

## プロジェクト概要

コードベースを静的に走査し、ファイル単位の索引（機能概要・認証・認可・読み書きするテーブル）と、テーブルからの逆引きを生成する Python 製の CLI。DB へは接続せず、スキーマは別ツールが出力した JSON を読む。

**一覧を作ることが目的ではない。「発見した対象を全部解析できたか」を保証することが目的。** アダプタが claim したのに読めなかったファイルは `unknown` として 1 件ずつ名指しし、どのアダプタも claim していない拡張子は `unclaimed` として拡張子ごとに数える（どちらも必ず数に入れる。落とすのは失敗ではなく嘘）。非ゼロで終了するかは `fail_on_unknown` 次第で、対象は `unknown` のみ。追えなかった箇所は空欄ではなく `unresolved` に理由付きで残す。生成物には必ず生成元 commit とカバレッジを刻み、参照 0 件を「未使用」と書かない。

## やらないこと（スコープ外）

- DB への接続（スキーマは JSON snapshot を入力にする）
- 差分キャッシュ・stale 判定のための独自メタデータ（毎回フル生成で足りる。実測で数百ファイル規模は 0.1 秒未満）
- SQL パーサの自作（sqlglot に任せる）
- 2 段以上の間接呼び出しの追跡（追えないことを正しく数えるほうを優先する）
- 可視化・GUI・Web UI
- 汎用の静的解析基盤化（契約検査は semgrep、PHP の意味解析は PHPStan へ逃がす）

## 技術スタック

| 種別 | 内容 |
|---|---|
| 言語 | Python 3.11+ |
| 依存 | sqlglot（SQL のテーブル名正規化）/ tree-sitter（各言語の構文解析） |
| 連携（外部ツール） | tbls（スキーマ snapshot）/ semgrep（契約検査）/ PHPStan（PHP の意味解析） |
| 対応言語アダプタ | PHP（第一段階）→ Python / Go / TS・JS / SQL / HTML / CSS / Rust / Shell / PowerShell / Vue。能力で 3 段（完全・逆引き・最小）。1 言語 = アダプタ + クエリ + fixture の 3 点で core は編集しない |

## ディレクトリ構成

- `omitnix/` — 実装。core（`config` / `scan` / `analyze` / `render` / `cli` / `registry`）
- `omitnix/adapters/` — 言語アダプタ。**置くだけで発見される**（登録表は core に無い）。契約は `adapters/base.py`。先頭 `_` は共有部品で発見対象外
- `omitnix/queries/` — tree-sitter のクエリ（`<lang>.scm`）
- `.semgrep/` — 契約検査のルール例（索引生成には使わない）
- `tests/` — pytest。合成アダプタと架空スキーマの fixture は `tests/fixtures/`
- `scripts/` — secrets-scan と CLAUDE.md 検査（house 標準の配線）
- `docs/local/` — 作業 plan（gitignored・Drive 同期領域へのジャンクション）

## 主要コマンド

- secrets-scan（手動）: `node scripts/secrets-scan.mjs --staged --block`
- CLAUDE.md 検査: `node scripts/check-claude-md.mjs`
- テスト: `python -m pytest`（リポジトリ直下で実行する）
- lint: `python -m ruff check .`
- 新規ファイルの gate: `python -m omitnix --gate`（終了コード 4 で拒否）
- PHP アダプタの依存: `python -m pip install "omitnix[php]"`（tree-sitter / tree-sitter-php / sqlglot）

## 設計原則の索引（本文は正本にある）

事故から生まれた設計ルールを追記する表。**本文はここに書かず、破る人が必ず開く場所に置く。**
機械検査があるものは、それが最終的な歯止め（`scripts/check-claude-md.mjs` があれば CI/hook で検査）。

| ルール | 正本（本文はここ） | 機械検査 |
|---|---|---|
| 発見数と 4 区分の合計が一致しなければ実行を落とす。解析できなかったものは `unknown`（claim したのに読めなかった・1 件ずつ名指し・非ゼロ終了の対象）と `unclaimed`（誰も claim していない・拡張子ごとに集計）に分けるが、**どちらも数から消さない**。文法が厳しすぎるだけのものを壊れたファイルと同じに扱わない（実測で正当化した範囲だけ例外にする） | `omitnix/model.py`（`Status` / `Coverage.holds`）/ `omitnix/analyze.py`（`assemble_report` の不変条件）/ `omitnix/adapters/html.py`（`TEXT_LEVEL_CHARACTERS`） | `tests/test_analyze.py` / `tests/test_cli.py` / `tests/test_workspace.py` / `tests/test_adapter_html.py` |
| 追えなかったものを空欄にせず理由付きで `unresolved` に残す | `omitnix/adapters/base.py`（`AnalysisResult.add_unresolved`） | `tests/test_analyze.py` |
| 能力の外の項目を「欠落」「0 件」と同じ表現にしない | `omitnix/render.py`（`n/a` / `none observed` / `not analyzed`） | `tests/test_render.py` |
| 新規ファイルの必須項目は能力宣言から決める（能力の外の欠落で落とさない） | `omitnix/gate.py` | `tests/test_gate.py` |
| SQL パーサを自作しない（sqlglot に任せる） | `omitnix/adapters/_sql.py` | `tests/test_php_adapter.py` |
| 同じソースからは同じ生成物（捕捉は文書順・set を経由しない。走査集合の外は追わず、理由もディスクの有無で変えない） | `omitnix/adapters/_treesitter.py` / `omitnix/adapters/base.py`（`AnalysisRequest.in_scope`） | `tests/test_determinism.py` / `tests/test_php_adapter.py` |
| 生成物に OS を出さない（改行は LF 固定・プラットフォーム分岐を書かない） | `omitnix/cli.py` | `tests/test_cli.py` |
| 参照 0 件を「未使用」と書かない | `README.md` の Why it exists 節 | なし（レビューで見る） |
| README・設定サンプル・fixture に実在するテーブル名や関数名を書かない | `docs/local/plan_progmap-oss_c1_naming-init.md` | `scripts/secrets-scan.mjs`（layer 2/3） |

**新しいルールを足す前に、まずこの表に 1 行足せる形にできないかを考える。** できないもの
（機械検査も、決まったファイルも無いもの）だけが本文を持ってよい。

## AI 作業共通ルール

ビルド・コミット禁止、secrets-scan 責務、plan/bugfix/pending md の作成ルール等の AI 作業共通ルールは、各利用者のグローバル AI 設定に従う（作者環境の例: `~/.claude/CLAUDE.md` および `~/.claude/guides/`）。

- **public リポである。** README・設定サンプル・テスト fixture に、実在するシステムのテーブル名・関数名・画面名・会社名を書かない。例は架空のスキーマ（orders / customers 等）で書く
- リポ固有の値（認可関数名・対象パス）はコードへ直書きせず、設定ファイルで受ける

## Obsidian artifacts

If `docs/obsidian/README.md` exists, use it as an index for related knowledge artifacts.
Use the repository-relative `docs/obsidian` entry. Do not write to a central absolute
path and do not silently fall back to `docs/local` when the entry is missing.

## secrets-scan（このリポジトリの配線）

書く瞬間の責務（固有名詞の一般化・fixture は合成データ等）は上記「AI 作業共通ルール」の参照先に従う。このリポジトリ固有の配線は以下:

- scanner: `scripts/secrets-scan.mjs`（手動実行: `node scripts/secrets-scan.mjs --staged --block`）
- layer 2: pre-commit hook（husky or `.githooks/`）/ layer 3: `.github/workflows/secrets-scan.yml` / layer 4: release ゲート
- env (full coverage に必要・未設定なら構造 regex のみで継続): `KB_ROOT` / `FAMILY_ROOT`。設定詳細は `scripts/secrets-scan.mjs` の冒頭コメント
- 参照実装・設計詳細: `worklog-bridge` リポの `docs/local/secrets-scan-design/`（gitignored・公開しない）

## 関連ドキュメント

| 項目 | パス |
|---|---|
| ユーザー向け README | `README.md` |
| Codex/他 AI 用入口 | `AGENTS.md` |
| ローカル作業ノート（非公開） | `docs/local/`（存在する場合） |
| Obsidian knowledge artifacts | `docs/obsidian/`（存在する場合。作業キューではない） |
