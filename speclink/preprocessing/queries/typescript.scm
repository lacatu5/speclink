(class_declaration
  name: (type_identifier) @class.name) @class.node

(function_declaration
  name: (identifier) @function.name) @function.node

; Top-level variable declarations (including exports)
(program
  [
    (lexical_declaration)
    (variable_declaration)
    (export_statement
      declaration: [(lexical_declaration) (variable_declaration)])
  ] @variable.node)

; Capture names within declarations
(variable_declarator
  name: [
    (identifier) @variable.name
    (object_pattern [
      (pair_pattern value: (identifier) @variable.name)
      (shorthand_property_identifier_pattern) @variable.name
    ])
    (array_pattern (identifier) @variable.name)
  ])

; Top-level significant calls (initialization, wiring)
(program
  (expression_statement
    (call_expression
      function: [
        (identifier) @variable.name
        (member_expression object: (identifier) @variable.name)
      ]
      (#not-match? @variable.name "^(require|console|expect|describe|test|it|beforeEach|afterEach|beforeAll|afterAll|Object|Array|String|Number|Boolean|Symbol|Promise|Map|Set|Error|process|window|document)$")
    )) @variable.node)

(class_declaration
  name: (type_identifier) @method.parent
  body: (class_body
    (method_definition
      name: (property_identifier) @method.name) @method.node))

; Mark true private stuff (started with # or marked private directly on the property/method identifier)
((property_identifier) @private
 (#match? @private "^_.*"))

((private_property_identifier) @private)

(method_definition
  (accessibility_modifier) @private.modifier
  (#match? @private.modifier "(private|protected)"))

(interface_declaration
  name: (type_identifier) @interface.name) @interface.node

(type_alias_declaration
  name: (type_identifier) @typeAlias.name) @typeAlias.node

(enum_declaration
  name: (identifier) @enum.name) @enum.node

; import { name } from 'mod'
(import_statement
  (import_clause (named_imports
    (import_specifier name: (identifier) @import.name)))
  source: (string (string_fragment) @import.mod))

; import * as X from 'mod'
(import_statement
  (import_clause (namespace_import) @import.wildcard)
  source: (string (string_fragment) @import.mod))

; import defaultExport from 'mod'
(import_statement
  (import_clause (identifier) @import.wildcard)
  source: (string (string_fragment) @import.mod))

; require('mod')
(call_expression
  function: (identifier) @_req
  (#eq? @_req "require")
  arguments: (arguments (string (string_fragment) @import.mod)))

; Function calls - capture caller and callee
(call_expression
  function: (identifier) @call.callee) @call.site

; Method calls - obj.method() or obj.method?.()
(call_expression
  function: (member_expression
    object: (identifier) @call.receiver
    property: (property_identifier) @call.callee)) @call.site

; Chained method calls - obj.a.b.method()
(call_expression
  function: (member_expression
    object: (member_expression) @call.receiver
    property: (property_identifier) @call.callee)) @call.site

; Calls through subscripts - obj[key]()
(call_expression
  function: (subscript_expression
    object: (identifier) @call.receiver)) @call.site
