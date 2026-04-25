(class_definition
  name: (identifier) @class.name) @class.node

(function_definition
  name: (identifier) @function.name) @function.node

; Methods (including decorated ones like @property)
(class_definition
  name: (identifier) @method.parent
  body: (block
    [(function_definition
      name: (identifier) @method.name) @method.node
     (decorated_definition
       (function_definition
         name: (identifier) @method.name) @method.node)]))

; from X import name
(import_from_statement
  module_name: [(dotted_name)(relative_import)] @import.mod
  (dotted_name) @import.name)

; from X import name as alias
(import_from_statement
  module_name: [(dotted_name)(relative_import)] @import.mod
  (aliased_import (dotted_name) @import.name))

; from X import *
(import_from_statement
  module_name: [(dotted_name)(relative_import)] @import.mod
  (wildcard_import) @import.wildcard)

; import X  /  import X as Y
(import_statement
  name: [(dotted_name) @import.mod
         (aliased_import (dotted_name) @import.mod)])

; Function calls - capture caller and callee
(call
  function: (identifier) @call.callee) @call.site

; Method calls - obj.method()
(call
  function: (attribute
    object: (identifier) @call.receiver
    attribute: (identifier) @call.callee)) @call.site

; Chained method calls - obj.attr.method()
(call
  function: (attribute
    object: (attribute) @call.receiver
    attribute: (identifier) @call.callee)) @call.site

; Calls through subscripts - obj[key]()
(call
  function: (subscript
    value: (identifier) @call.receiver)) @call.site
