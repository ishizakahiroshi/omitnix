; omitnix -- the Rust shapes the adapter looks for.
;
; The adapter holds no Rust syntax. Every construct it reacts to is named here, so
; correcting or widening a pattern is a change to this file rather than to Python code.
; Capture names are the contract between this file and omitnix/adapters/rust.py.

; ---------------------------------------------------------------------------
; call.name -- every name this file invokes, however it invokes it.
;
; `require_session()`, `auth::require_session()` and `session.require_session()` all
; land here as the bare name, because a repository's configuration lists function names
; and matching on the name is what it asked for. A turbofish (`load::<Order>()`) wraps
; the function in `generic_function`, so that shape is named too.
; ---------------------------------------------------------------------------
(call_expression function: (identifier) @call.name)
(call_expression function: (scoped_identifier name: (identifier) @call.name))
(call_expression function: (field_expression field: (field_identifier) @call.name))
(call_expression function: (generic_function function: (identifier) @call.name))
(call_expression
  function: (generic_function
    function: (scoped_identifier name: (identifier) @call.name)))
(call_expression
  function: (generic_function
    function: (field_expression field: (field_identifier) @call.name)))
(macro_invocation macro: (identifier) @call.name)
(macro_invocation macro: (scoped_identifier name: (identifier) @call.name))

; ---------------------------------------------------------------------------
; sql.* -- candidate SQL.
;
; Rust spells a statement as a string, a raw string, the pieces of `concat!`, or a
; chain joined with `+` (usually through `to_owned` or `to_string`). A `format!` hole
; is a property of the string's text, so it is handled in the adapter.
;
;   sql.literal   "..." or r#"..."#, including a string passed to a macro
;   sql.add       an expression built with '+', so parts of it are missing here
;   sql.concat    a `concat!` invocation; `sql.concat.name` is the macro's name
; ---------------------------------------------------------------------------
(string_literal) @sql.literal
(raw_string_literal) @sql.literal
(binary_expression operator: "+") @sql.add
(macro_invocation macro: (identifier) @sql.concat.name) @sql.concat

; ---------------------------------------------------------------------------
; builder.* -- calls that may be a query builder rather than SQL text.
;
; The adapter decides which of these name Diesel, SeaORM or SeaQuery. The query only
; finds the shapes; inventing a table from a method name is not its job.
; ---------------------------------------------------------------------------
(use_declaration) @builder.use
(call_expression function: (scoped_identifier) @builder.scoped)
(macro_invocation macro: (scoped_identifier) @builder.scoped)
(call_expression
  function: (generic_function function: (scoped_identifier) @builder.scoped))
(call_expression function: (identifier) @builder.bare)
(macro_invocation macro: (identifier) @builder.bare)
(call_expression
  function: (generic_function function: (identifier) @builder.bare))
(call_expression
  function: (field_expression field: (field_identifier) @builder.method))
(call_expression
  function: (generic_function
    function: (field_expression field: (field_identifier) @builder.method)))

; ---------------------------------------------------------------------------
; comment -- the run of comments at the head of the file supplies the summary.
; `//!` is a line comment in this grammar, with the marker as its own child.
; ---------------------------------------------------------------------------
(line_comment) @comment
(block_comment) @comment
