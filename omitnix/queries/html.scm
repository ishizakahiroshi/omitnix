; omitnix -- the HTML shapes the adapter looks for.
;
; Capture names are the contract between this file and omitnix/adapters/html.py.

; ---------------------------------------------------------------------------
; attribute.* -- a tag name together with one of its attributes.
;
; The tag is captured alongside the attribute because neither alone means anything: it is
; `action` on a `form` and `src` on a `script` that are requests, while `action` on
; anything else and `src` on an image are not.
;
; Two patterns, because an unquoted attribute value has no wrapping node.
; ---------------------------------------------------------------------------
(start_tag
  (tag_name) @attribute.tag
  (attribute
    (attribute_name) @attribute.name
    (quoted_attribute_value (attribute_value) @attribute.value)))

(start_tag
  (tag_name) @attribute.tag
  (attribute
    (attribute_name) @attribute.name
    (attribute_value) @attribute.value))

; ---------------------------------------------------------------------------
; element.* -- an element's tag and its text, which is where <title> is read from.
; ---------------------------------------------------------------------------
(element
  (start_tag (tag_name) @element.tag)
  (text) @element.text)

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
