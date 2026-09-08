; omitnix -- the HTML shapes the adapter looks for.
;
; Capture names are the contract between this file and omitnix/adapters/html.py.
;
; Every pattern here captures a single node, and that is not a stylistic choice.
; Measured on 2026-09-08 with tree-sitter-html 0.23.2 and py-tree-sitter 0.26.0, on
; generated pages of 2,000 to 16,000 rows:
;
;   (start_tag (tag_name) @t (attribute (attribute_name) @n
;              (quoted_attribute_value (attribute_value) @v)))   0.064 -> 3.550 s  (x4.2)
;   (attribute (attribute_name) @n
;              (quoted_attribute_value (attribute_value) @v))    0.041 -> 1.368 s  (x3.9)
;   (start_tag) @tag                                             0.019 -> 0.109 s  (x1.9)
;
; Doubling the page quadrupled the time for the patterns that capture several nodes at
; different depths, and doubled it for the single-node ones -- while the number of
; captures grew linearly in every case, so the cost is not in what came back. One real
; page of 2.6 MB took 27.3 seconds and accounted for 44% of a 52-repository run.
;
; So the query asks only for whole nodes, and omitnix/adapters/html.py walks their
; children itself. That is more Python for the same answers, and it is linear.

; ---------------------------------------------------------------------------
; start_tag -- the adapter reads the tag name and the attributes from each one.
;
; It is `action` on a `form` and `src` on a `script` that name a request, while `action`
; on anything else and `src` on an image do not, so neither the tag nor the attribute
; means anything without the other. The pairing is done in the adapter.
; ---------------------------------------------------------------------------
(start_tag) @start_tag

; ---------------------------------------------------------------------------
; script.body -- the source inside a <script> element, handed to the JavaScript
; grammar. A page's requests are far more often written here than in a form action.
; ---------------------------------------------------------------------------
(script_element (raw_text) @script.body)

; ---------------------------------------------------------------------------
; comment -- the comment at the head of the document supplies the summary when the
; page has no <title>.
; ---------------------------------------------------------------------------
(comment) @comment
