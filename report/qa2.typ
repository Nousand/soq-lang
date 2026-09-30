= (a) What I Built

I built _soq_, a small JSON-oriented scripting language in the style of jq,
with a lexer, parser, tree-walking interpreter, standard library, command-line
interface and tests. It is 1,384 lines of Python across four files with no
third-party dependencies, backed by 396 lines of tests.

The four stages import strictly in one direction, so each can be exercised
without the ones after it:

#table(
  columns: 3,
  [*File*], [*Transforms*], [*Lines*],
  [`lexer.py`], [source text to a token stream], [243],
  [`parser.py`], [token stream to a syntax tree], [284],
  [`interp.py`], [syntax tree to values], [755],
  [`soq.py`], [command line and JSON file I/O], [102],
)


== The Explanation

*Parsing.* Expressions use precedence climbing driven by one table,
`LEFT_BINDING` at `parser.py:3`. `parse_expr` takes a right-binding-power
floor and stops as soon as the next operator binds too loosely, which makes
every binary operator left-associative for free. This is the technique the
interpreter-building literature calls Pratt parsing \[1\] \[2\]: instead of one
function per precedence level, the whole precedence structure collapses into a
single table of numeric binding powers that the parser consults. The usual
textbook arrangement \[4\] instead spends one function per precedence level,
which means a new tier costs a new function _and_ an edit to every function
above it. Here it costs a single row. Statements are plain recursive descent,
one function per statement form.

*Data representation.* The syntax tree is a single `Node` class with a `kind`
string and up to four generic fields `a`, `b`, `c`, `d`, rather than a class
per form. There are twenty-four node kinds. This keeps the grammar compact and
means a new form is added in exactly two places, but the field names carry no
information: `node.b` is the right operand of a `bin` node and the parameter
list of a `def` node, and nothing in the type system says so. Runtime values
are Python's own `None`, `bool`, `int`/`float`, `str`, `list` and `dict`, so
soq's `null` is `None` and arithmetic and JSON encoding are inherited rather
than reimplemented. Scope is a parent-chained dictionary, so a function can
update a binding in an enclosing frame.

*The pipe is resolved late.* `xs |> f a b` means `f a b xs` — data always
travels last, which is what lets `map` and friends compose without a
placeholder. The pipe stays a node in the tree and is resolved in the
interpreter rather than desugared during parsing, because the right-hand side
is a restricted postfix expression and desugaring would need a separate rewrite
per shape.

== Where soq Differs from jq

soq is a deliberate subset of jq, not a reimplementation of it. The reductions:
no regular expressions (`test`, `match`, `sub`, `scan`), no error handling
(`try`, `?`, `//` as an operator), no path expressions (`..`, `paths`,
`getpath`), no `del` or update assignments, no `import`, no date and time
builtins, and no `.` identity shorthand — `map` requires an explicit
`fn(o) = o.a`. Dropping `.` removes the implicit-input plumbing from the
evaluator entirely, at the cost of verbosity.

Five builtins are renamed, deliberately, so a jq script cannot be ported by
accident and appear to work: `length` to `len`, `add` to `sum`, `tostring` to
`str`, `ascii_upcase` to `upper`, `ascii_downcase` to `lower`.

The additions go the other way: `let`, `def` and `for` exist as statements, so
a script reads top to bottom rather than as one chain; variables are mutable
within scope once introduced by `let`; `//` is a comment to end of line; and
every error carries a line and column, where jq generally produces empty
output and continues.

== Finding Your Way Around

Start at `soq.py:48` and follow a call downwards. `interp.py:212` is the
`eval` dispatch and `parser.py:140` is `parse_nud`; every form appears in
exactly one branch of each. The places worth editing are concentrated in
tables rather than spread through logic:

#table(
  columns: 2,
  [*To change*], [*Edit*],
  [operator precedence], [`LEFT_BINDING`, `parser.py:3`],
  [a keyword], [`KEYWORDS`, `lexer.py:1`],
  [an operator], [`TWO_CHAR`, `ONE_CHAR`, `lexer.py:7` and `lexer.py:11`],
  [when newlines are significant], [`ENDS_STATEMENT`, `lexer.py:18`],
  [a string escape], [`ESCAPES`, `lexer.py:26`],
  [a syntax form], [`parse_nud`, `parse_led`, then `eval`],
  [a standard-library function], [a `@_b` decorated function, `interp.py:425`],
)

Every parse and runtime error carries a line and column, and `soq.py tokens`
prints the token stream, so the fastest way to localise a problem is to shave
the program down until the error is the only output.

== References

+ Ball, T. _Writing an Interpreter in Go._ Leanpub, 2016. Builds a scanner, a
  Pratt parser and a tree-walking interpreter from scratch; the treatment of
  Pratt parsing and of environments is the closest published match to the two
  halves of soq's front end.
+ Nystrom, R. _Crafting Interpreters._ 2020. The same territory, with fuller
  treatment of scoping and of running a scanner that must track position.
+ _The Go Programming Language Specification_, §Semicolons.
  #link("https://go.dev/ref/spec#Semicolons")[go.dev/ref/spec\#Semicolons]
+ Aho, A. V., Lam, M. S., Sethi, R. and Ullman, J. D. _Compilers: Principles,
  Techniques, and Tools._ 2nd ed., Addison-Wesley, 2006. The recursive-descent
  baseline that precedence climbing and `ENDS_STATEMENT` are measured against.
