; omitnix -- the Go shapes the adapter looks for.
;
; The adapter holds no Go syntax. Every construct it reacts to is named here, so
; correcting or widening a pattern is a change to this file rather than to Python code.
; Capture names are the contract between this file and omitnix/adapters/go.py.

; ---------------------------------------------------------------------------
; call.name -- every name this file invokes, however it invokes it.
;
; `requireSession()` and `auth.RequireSession()` both land here as the bare name,
; because a repository's configuration lists function names and matching on the name
; is what it asked for.
; ---------------------------------------------------------------------------
(call_expression function: (identifier) @call.name)
(call_expression function: (selector_expression field: (field_identifier) @call.name))

; ---------------------------------------------------------------------------
; sql.* -- candidate SQL.
;
; Go has no string interpolation, so a statement is either written out in full or built
; with '+' or fmt.Sprintf. The first two are captured here; the third is handled by
; substituting Go's formatting verbs, which is done in the adapter because it is a
; property of the string's text rather than of its shape in the tree.
;
;   sql.literal        "..." or a `raw string`, which is how multi-line SQL is written
;   sql.concatenated   an expression built with '+', so parts of it are missing here
; ---------------------------------------------------------------------------
(interpreted_string_literal) @sql.literal
(raw_string_literal) @sql.literal
(binary_expression) @sql.concatenated

; ---------------------------------------------------------------------------
; comment -- the run of comments above the package clause supplies the summary.
; ---------------------------------------------------------------------------
(comment) @comment
