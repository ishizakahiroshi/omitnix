; omitnix -- the TypeScript/JavaScript shapes the adapter looks for.
;
; One query, three grammars. TypeScript, TSX and JavaScript are separate grammar entry
; points that share a node vocabulary, so this file is compiled once against each of them
; (see load_grammar's query_name argument). Every pattern below therefore has to name only
; nodes all three have -- nothing that exists solely in the TypeScript grammar.
;
; Capture names are the contract between this file and omitnix/adapters/tsjs.py.

; ---------------------------------------------------------------------------
; call.name -- every name this file invokes, however it invokes it.
; ---------------------------------------------------------------------------
(call_expression function: (identifier) @call.name)
(call_expression function: (member_expression property: (property_identifier) @call.name))

; ---------------------------------------------------------------------------
; sql.* -- candidate SQL.
;
;   sql.literal        a quoted string
;   sql.interpolated   a template literal: its substitutions are run-time holes
;   sql.concatenated   an expression built with '+', so parts of it are missing here
; ---------------------------------------------------------------------------
(string) @sql.literal
(template_string) @sql.interpolated
(binary_expression) @sql.concatenated

; ---------------------------------------------------------------------------
; endpoint.* -- a call and its whole argument list, so the adapter can decide which
; calls are requests and read the first argument of those.
;
; The argument list is captured whole rather than anchored to its first child: an anchor
; counts anonymous nodes in some grammar versions, and picking the first *named* child in
; the adapter is the same answer without depending on that.
; ---------------------------------------------------------------------------
(call_expression
  function: (identifier) @endpoint.callee
  arguments: (arguments) @endpoint.arguments)

(call_expression
  function: (member_expression
    object: (identifier) @endpoint.object
    property: (property_identifier) @endpoint.property)
  arguments: (arguments) @endpoint.arguments)

; ---------------------------------------------------------------------------
; comment -- the run of comments at the head of the file supplies the summary.
; ---------------------------------------------------------------------------
(comment) @comment
