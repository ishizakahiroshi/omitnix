# walk benchmark: TypeScript (Node)

基準 commit: `374e5bb337ec0f7e0f4a47d97c70083a306eb1ed`。
このフォルダだけの独立した benchmark。製品コード・`build_report` は変更しない。

## 実行

Node **v24.19.0**、Linux x86_64 で計測した。`.mts` を Node の組み込み
TypeScript type stripping で実行し、外部 TypeScript compiler や transpiler は不要。
Type stripping は型検査ではない。静的な `tsc` 検査は実行していない。

リポジトリルートから:

```sh
node bench-walk/typescript/bench.mts --self-test
node bench-walk/typescript/bench.mts > bench-walk/typescript/RESULT.txt
```

通常実行の stdout は **4 行だけ**。`RESULT.txt` は実測 stdout をそのまま保存したもの。
診断は stderr へ出す。時刻は `process.hrtime.bigint()`、ms 小数 1 桁で表示する。

## Benchmark 1: 指定された walk

全候補を start 昇順・同じ start なら end 降順でソートする。各 run で空の accepted
を作り、候補ごとに accepted を**挿入順の先頭から**走査する。
`outer.start <= candidate.start && candidate.end <= outer.end` 全体を 1 比較と数え、
最初の包含で止め、包含されなければ末尾に追加する。逆順走査・sweep・index 等への
置換はしない。

| ケース | 候補生成 | 候補数 | 比較数 | 残る数 |
| --- | --- | ---: | ---: | ---: |
| S | i=0..824: [i,i+1] | 825 | 339900 | 825 |
| N | i=0..199: 外側 [i*1000,i*1000+500]、j=0..19: 内側 [i*1000+1+j,i*1000+2+j] | 4200 | 421900 | 200 |
| M | i=0..3999: [i,i+1] | 4000 | 7998000 | 4000 |

生成とソートは計測外。warm-up 1 回、その後 5 回を計測し最小値を採用する。
accepted の生成・append・走査を含む同じ処理を毎回実行する。結果の消費と検証は
計測外にあり、全 run の件数が一致することを確認する。追加の JIT warm-up は行わない。

## Benchmark 2: binding を実際に試す

今回 `tree-sitter` と `tree-sitter-python` は実際の Node module resolution で
ともに `MODULE_NOT_FOUND`。benchmark 本体でも `require('tree-sitter')` を実行し、
失敗を確認した。そのため 4 行目は `parse typescript BINDING_FAILED`。
parser/grammar のインストール済みバージョンはなく、parse 成功・件数・時間は記載しない。
network のパッケージ取得制限を迂回せず、regex による代替抽出もしていない。

実装した成功経路は、native Node binding と Python grammar が利用できれば
固定 commit の全 tracked `.py` / `.pyi`（68 ファイル）を対象にする。
`string` と `concatenated_string` ノードを AST から取得し、JavaScript string index
との一致を検査して UTF-8 byte range へ変換する。Unicode・隣接文字列の probe が
通った場合だけ解析へ進む。この成功経路は今回の環境では未検証。

ファイル列挙は `git ls-tree`、内容は `git show <base>:<path>` から取り、working tree
や追加した benchmark ファイルを混ぜない。別ファイルの byte range 同士を比較せず、
ファイルごとに accepted をリセットして合計する。Git 読取・parse・AST traversal・
抽出・sort は計測外。成功した場合の parse 行の ms も抽出後の **walk の時間**。
回復 AST はエラーファイル名を stderr へ出して含める。Python 以外の拡張子は対象外。

すでに利用可能な binding が別の package root にある場合のみ、
`BENCH_BINDING_ROOT` にそのディレクトリを指定できる。自動 download はしない。

## 検証

self-test は S/N/M の全契約値、先頭からの走査、同開始位置の end 降順、重複候補、
ファイル間の独立性、部分的な重なり、warm-up + 計測の合計 6 回、空入力を確認する。

参考: [Node の TypeScript 実行](https://nodejs.org/docs/latest-v24.x/api/typescript.html)、
[Node tree-sitter](https://tree-sitter.github.io/node-tree-sitter/)
