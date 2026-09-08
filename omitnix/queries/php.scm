; omitnix -- the PHP shapes the adapter looks for.
;
; The adapter itself holds no PHP syntax. Every construct it reacts to is named here, so
; correcting or widening a pattern is a change to this file rather than to Python code.
; Capture names are the contract between this file and omitnix/adapters/php.py.

; ---------------------------------------------------------------------------
; call.name -- every name this file invokes, however it invokes it.
;
; Used twice: to recognise the authentication and authorization functions the
; repository named in its configuration, and to decide which function body in an
; included file is worth following one hop.
; ---------------------------------------------------------------------------
(function_call_expression function: (name) @call.name)
(member_call_expression name: (name) @call.name)
(nullsafe_member_call_expression name: (name) @call.name)
(scoped_call_expression name: (name) @call.name)

; ---------------------------------------------------------------------------
; definition.* -- where a called name is defined, so one hop can be followed.
; ---------------------------------------------------------------------------
(function_definition
  name: (name) @definition.name
  body: (compound_statement) @definition.body)
(method_declaration
  name: (name) @definition.name
  body: (compound_statement) @definition.body)

; ---------------------------------------------------------------------------
; include.path -- the argument of require/include. Followed one hop when the path
; is a literal; counted as unresolved when it is assembled at run time.
; ---------------------------------------------------------------------------
(require_expression (_) @include.path)
(require_once_expression (_) @include.path)
(include_expression (_) @include.path)
(include_once_expression (_) @include.path)

; ---------------------------------------------------------------------------
; sql.* -- candidate SQL. Which of the three a string lands in decides whether the
; statement can be read as written, or only as a fragment assembled at run time.
;
;   sql.literal        a single-quoted string or nowdoc: fully static
;   sql.interpolated   a double-quoted string or heredoc: holds run-time values
;   sql.concatenated   an expression built with '.', so parts are missing here
; ---------------------------------------------------------------------------
(string) @sql.literal
(nowdoc) @sql.literal
(encapsed_string) @sql.interpolated
(heredoc) @sql.interpolated
(binary_expression) @sql.concatenated

; ---------------------------------------------------------------------------
; comment -- the run of comments at the head of the file supplies the summary.
; ---------------------------------------------------------------------------
(comment) @comment
