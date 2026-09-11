---
schemaVersion: 1
color: "#2f5c8f"
initials: "om"
cat:
  ja: "CLI / Python"
  en: "CLI / Python"
tagline:
  ja: "読めなかったファイルを、読めなかったと書き残す。"
  en: "The files it could not read are still in the report, by name."
short:
  ja: "発見したファイルを全部解析できたかを毎回数え、できなかったものを理由付きで残す静的コード索引 CLI。"
  en: "A static code inventory CLI that counts whether every discovered file was analyzed, and records the ones that were not."
tech: ["Python", "CLI", "tree-sitter", "sqlglot", "PyPI"]
store: null
live: null
guide: "https://ishizakahiroshi.com/articles/omitnix/usage.html"
featured: false
features:
  - icon: "◱"
    title: { ja: "数が合わなければ落ちる", en: "Fails when the numbers disagree" }
    desc:  { ja: "発見数と、解析済み・未解決・読めなかった・担当なしの合計が一致しない実行は失敗させる。", en: "A run fails unless discovered equals analyzed plus unresolved plus unknown plus unclaimed." }
  - icon: "▲"
    title: { ja: "空欄にしない", en: "No blank cells" }
    desc:  { ja: "追えなかった箇所は理由付きで残す。参照 0 件を「未使用」と書かない。", en: "What could not be followed is kept with a reason, and zero references is never written as “unused.”" }
  - icon: "◎"
    title: { ja: "言語は置くだけで増える", en: "Languages are drop-in" }
    desc:  { ja: "11 言語ぶんのアダプタ。追加はファイルを置くだけで、本体に登録表を持たない。", en: "Eleven language adapters. Adding one is dropping in a file; the core holds no registry." }
---
## ja

静的解析でコードの目録を作ること自体は難しくありません。難しいのは、その目録が「全量である」と言い切れる状態を保つことです。よくある生成器はパーサが解釈できないファイルを黙って飛ばすので、出てくるのは「読めた範囲の目録」なのに、読み手にはそれが「全量の目録」と区別できません。

omitnix はこれを成果物の側で解いています。走査で発見した数と、解析できた数・一部を追えなかった数・読もうとして読めなかった数・担当するアダプタが無い数の合計が一致しなければ、その実行を失敗させます。読めなかったファイルは結果から消えず、理由付きで名前が残ります。

「探したが見つからなかった」と「そもそも探していない」も別の状態として書き分けます。認可関数の名前を設定していないリポジトリで「認可呼び出しは観測されませんでした」と出力するのは、何も探していないのに探した顔をすることなので、それ専用の状態を持たせました。

DB には接続しません。スキーマが要るときは別のツールが出力した JSON を読みます。

## en

Building a code inventory with static analysis is not the hard part. Keeping it honest is. A typical generator skips the files its parser cannot read, so what comes out is an inventory of the readable subset — indistinguishable, to whoever reads it later, from an inventory of everything.

omitnix solves that in the artifact. Every run checks that the number of files discovered equals the sum of those analyzed, those whose details could not be followed, those an adapter claimed and failed to read, and those no adapter claimed. If the equation does not hold, the run fails. Nothing drops out quietly, and a file that could not be read is still named, with the reason.

"Looked and found nothing" and "never looked" are also kept apart. Reporting "no authorization calls observed" for a repository that never said which functions count as authorization is a search that never happened, so it gets a state of its own.

The tool never connects to a database. Where schema information is needed, it reads a JSON snapshot another tool produced.
