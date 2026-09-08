; omitnix -- the Python shapes the adapter looks for.
;
; The adapter holds no Python syntax. Every construct it reacts to is named here, so
; correcting or widening a pattern is a change to this file rather than to Python code.
; Capture names are the contract between this file and omitnix/adapters/python.py.

; ---------------------------------------------------------------------------
; call.name -- every name this file invokes, however it invokes it.
;
; Both spellings matter: a repository names `require_session` in its configuration and
; then calls it either directly or as `auth.require_session()`. Capturing only the
; attribute means the module it came from is not recorded, which is deliberate -- the
; configuration lists function names, and matching on the name is what it asked for.
; ---------------------------------------------------------------------------
(call function: (identifier) @call.name)
(call function: (attribute attribute: (identifier) @call.name))

; ---------------------------------------------------------------------------
; sql.* -- candidate SQL.
;
; Every string is a candidate; whether it is really SQL is decided by shape, not by the
; node type it arrived in. An f-string is a `string` holding an `interpolation`, and the
; walker turns that interpolation into a run-time hole, so the same pattern covers static
; and interpolated strings alike.
;
;   sql.literal        a string, or several written adjacent to each other
;   sql.concatenated   an expression built with '+', so parts of it are missing here
; ---------------------------------------------------------------------------
(string) @sql.literal
(concatenated_string) @sql.literal
(binary_operator) @sql.concatenated

; ---------------------------------------------------------------------------
; comment -- the run of comments at the head of the file, used for the summary when
; the module has no docstring. The docstring itself is found on the tree rather than
; here: what makes it a docstring is its position, which a capture cannot express.
; ---------------------------------------------------------------------------
(comment) @comment
