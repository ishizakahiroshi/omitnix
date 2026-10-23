# walk benchmark: Rust

基準 commit: `374e5bb337ec0f7e0f4a47d97c70083a306eb1ed`。
このフォルダだけの独立した実験。製品コード、`build_report`、索引生成物は変更しない。

## 比較する処理

候補を `start` 昇順・同じ `start` なら `end` 降順にソートした後、毎回空の
`accepted` を作る。候補ごとに `accepted` を挿入順の先頭から走査し、
`outer.start <= candidate.start && candidate.end <= outer.end` を評価する。
この包含述語全体の評価を 1 比較と数える。最初に包含されたところで止め、
包含されなければ末尾に追加する。逆順走査、区間木、二分探索、sweep は使わない。

| 入力 | 生成方法 | 候補数 | 比較数 | 残る数 |
| --- | --- | ---: | ---: | ---: |
| S | `i=0..824` の `[i,i+1]` | 825 | 339900 | 825 |
| N | `i=0..199` ごとに `[i*1000,i*1000+500]` と、`j=0..19` の `[i*1000+1+j,i*1000+2+j]` | 4200 | 421900 | 200 |
| M | `i=0..3999` の `[i,i+1]` | 4000 | 7998000 | 4000 |

生成・ソートは計測外。各ケースは warm-up 1 回、計測 5 回の最小値を
`Instant` で取り、ミリ秒・小数 1 桁で出す。各回の比較数・残存数を検証する。
空の accepted の生成、追加、走査、破棄は計測内。
`#[inline(never)]` と入出力の `std::hint::black_box` で定数化・不要処理除去を防ぐ。
1 桁に丸めるため、短い実測が `0.0` と表示される場合もある。

## Benchmark 2: tree-sitter の実 AST

- Rust binding: `tree-sitter = 0.27.0`
- Python grammar: `tree-sitter-python = 0.25.0`
- grammar ノード種別: `string`, `concatenated_string`
- 基準 commit の全 tracked `.py` / `.pyi`: **68 ファイル**（67 + 1）
- 基準 commit 全体: **158 ファイル**。残る **90 ファイル**は対象 grammar 外として除外

`git ls-tree -r --name-only -z <base>` で対象を列挙し、各ファイルの bytes を
`git show <base>:<path>` で読む。変更中の working tree や追加した benchmark
ファイルを入力に混ぜない。文字列範囲は AST の `start_byte/end_byte` から取得し、
正規表現による文字列抽出や regex への fallback は行わない。

今回 grammar を導入した対象は Python のみ。他のソース言語を解析済みとは扱わない。
除外拡張子は `.php`, `.rs`, `.md`, `.scm`, `.html`, `.flow`, `.sql`, `.go`,
`.yml`, `.mjs`, `.sh`, `.yaml`, `.json`, `.ps1`, `.js`, `.jpg`, `.toml`, `.htm`,
`.vue`, `.css`, `.note`, `.unmapped`, `.cjs`, `.ts`, `.tsx` と拡張子なし。

子ノードも最後まで訪問するので、隣接文字列の子や f-string 内の文字列も候補に入る。
包含除外は合成入力と同じ `walk` 関数で行う。別ファイルの byte offset 同士を
比較しないよう、ファイルごとに accepted をリセットし、件数と計測時間を合算する。
各計測は全 68 ファイルの walk 1 周で、warm-up 1 周後の 5 周の最小値。
Git 読取、parse、AST traversal、range 抽出、ソートはすべて計測外。
**`parse` 行の ms は parse 自体の所要時間ではなく、抽出済み範囲の walk 時間。**

Tree-sitter の recovery AST も対象から落とさない。この基準では
`tests/fixtures/python/broken.py` に構文エラーがあり、stderr で名前を報告したうえで
生成された AST の文字列ノードを数える。`ok` は binding と抽出が動いた意味で、
全入力の構文が正しいという意味ではない。grammar の初期化に実際に失敗した場合は
4 行目に `parse rust BINDING_FAILED` を出す。Git 読取失敗などは成功扱いせず終了する。
今回 binding の build・parse は成功しており、fallback 結果は使用していない。

## 再実行

Rust/Cargo と C compiler、Git が必要。リポジトリルートから実行する。
base commit の Git object が必要なので、shallow clone ではその object を用意する。
生成される `target/` はこのフォルダ内に限定し、gitignore している。

```sh
cargo build --release --locked --manifest-path bench-walk/rust/Cargo.toml
bench-walk/rust/target/release/omitnix-bench-walk-rust > bench-walk/rust/RESULT.txt
cargo test --release --locked --manifest-path bench-walk/rust/Cargo.toml
cargo clippy --release --locked --manifest-path bench-walk/rust/Cargo.toml -- -D warnings
cargo fmt --manifest-path bench-walk/rust/Cargo.toml -- --check
```

`RESULT.txt` は実行時の stdout をそのまま保存した **4 行**。診断は stderr へ分離する。
Cargo.lock を含め、依存解決を固定する。実測環境は 2026-10-01 UTC、Linux x86_64、
`rustc 1.98.1 (48a229cea 2026-09-01)`、`cargo 1.98.1 (797e8a9bc 2026-08-05)`、
release `opt-level=3`, `lto=false`。測定値はこの環境の結果で、他環境の速度は保証しない。

6 テストで S/N/M の契約値、先頭からの走査、同開始位置のソート、重複候補、
ファイル間の独立性、実 tree-sitter による隣接文字列の抽出、warm-up + 5 回を検証する。

参考: [tree-sitter Rust binding](https://docs.rs/tree-sitter/0.27.0/tree_sitter/)、
[Python grammar binding](https://docs.rs/tree-sitter-python/0.25.0/tree_sitter_python/)
