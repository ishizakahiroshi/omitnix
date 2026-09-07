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

**一覧を作ることが目的ではない。「発見した対象を全部解析できたか」を保証することが目的。** 解析できないファイルが 1 つでもあれば `unknown` として数え、非ゼロで終了する。追えなかった箇所は空欄ではなく `unresolved` に理由付きで残す。生成物には必ず生成元 commit とカバレッジを刻み、参照 0 件を「未使用」と書かない。

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
| 依存 | sqlglot（SQL のテーブル名正規化） |
| 連携（外部ツール） | tbls（スキーマ snapshot）/ semgrep（契約検査）/ PHPStan（PHP の意味解析） |
| 対応言語アダプタ | PHP（第一段階）。TypeScript / Go / Python は後続 |

## ディレクトリ構成

- `scripts/` — secrets-scan と CLAUDE.md 検査（house 標準の配線）
- `docs/local/` — 作業 plan（gitignored・Drive 同期領域へのジャンクション）
- 実装コードは未着手

## 主要コマンド

- secrets-scan（手動）: `node scripts/secrets-scan.mjs --staged --block`
- CLAUDE.md 検査: `node scripts/check-claude-md.mjs`
- テスト: 未整備（実装着手時に追記する）

## 設計原則の索引（本文は正本にある）

事故から生まれた設計ルールを追記する表。**本文はここに書かず、破る人が必ず開く場所に置く。**
機械検査があるものは、それが最終的な歯止め（`scripts/check-claude-md.mjs` があれば CI/hook で検査）。

| ルール | 正本（本文はここ） | 機械検査 |
|---|---|---|
| 発見した対象を全部解析できたかを検査し、できなければ非ゼロで終了する | `docs/local/plan_progmap-oss_c2_core.md` | 実装後に完全性テスト |
| 追えなかったものを空欄にせず理由付きで `unresolved` に残す | `docs/local/plan_progmap-oss_c3_php-adapter.md` | 実装後に単体テスト |
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
