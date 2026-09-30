# `soq` — written report

## (a) What I built

`soq` is a small data-oriented scripting language inspired by **jq**. It keeps jq's
execution model — a value flows left to right through a pipeline of filters, and every
builtin takes its data as the final argument — but replaces jq's filter syntax with a
statement-based syntax, so an ordinary script reads top to bottom. It is written in
Python 3.8+ with no dependencies: 1,384 lines across four files, plus 47 tests.

```
source ──▶ lexer.py ──▶ parser.py ──▶ interp.py ──▶ value
            tokens        AST          tree-walk
```

Imports run in one direction. Each stage is testable on its own: `test_soq.py` calls
`tokenize` on a raw string and asserts on the token kinds, calls `parse` and asserts on
the resulting value, and only then runs a complete program.

**Data representation.**

- **Values are Python values.** `int`/`float`, `str`, `list`, `dict`, `None`, `bool`,
  plus one `Function` class. There is no tagged union and no boxing. The direct
  consequence is that arrays and objects are mutable and reference-aliased: with
  `let b = a`, a later `b[0] = 99` also changes `a`.
- **The AST is a single `Node` class** with `kind`, `line`, `col`, and up to four generic
  slots `a, b, c, d`. Adding a form of syntax means adding a `kind` string rather than a
  class. The cost is that slots are positional: `bin` is `(a=op, b=lhs, c=rhs)`, `call`
  is `(a=callee, b=args)`. `Node.__repr__` is what makes that legible in a debugger.
- **Environments are a linked list of dicts.** Lookup walks up the parent chain. A
  closure is `(params, body, defining environment)` — twelve words of Python. `for`
  builds a fresh `Env` per iteration, so a closure created inside a loop captures a
  distinct binding each time:

  ```soq
  let fs = [null, null, null]
  for x in [1, 2, 3] do fs[x - 1] = fn() = x
  print([fs[0](), fs[1](), fs[2]()])   # [1, 2, 3]
  ```

**Parsing.** Expressions use precedence climbing (a Pratt parser). The whole precedence
table is the single dict `LEFT_BINDING`, mapping a token kind to a binding power.
`parse_expr(rbp)` parses a primary, then absorbs any infix form whose power exceeds
`rbp`. Calls, indexing, field access and `|>` are all infix forms at power 70 handled in
the same loop, so an expression like `f(xs)[0].a |> g` required no additional machinery.
Statements use ordinary recursive descent.

**Evaluation.** The interpreter is a tree walker: `Interp.eval` dispatches on
`node.kind` and recurses.

**Design decisions, and where they came from.**

- **No block syntax.** `def f(x) = <expr>`, with no `do`/`end` and no `return`. Because
  the body is a value, `fn` is an ordinary expression that can be passed to `map`.
- **Pipes append the value as the last argument**, so `xs |> map(f)` is `map(f, xs)` and
  every builtin is written data-last.
- **`if` is an expression, `for` is a statement.** `if c then a else b` has a value and
  can appear in a function body; `for x in xs do <statement>` runs statements and can
  accumulate. The `else` branch is optional and yields `null`.
- **Only `false` and `null` are falsey.** `0`, `""` and `[]` are all true.
- **Newlines end statements**, with two exceptions: inside `(`, `[` or `{`, and when the
  line begins with `|>` so a pipeline can wrap. Operators therefore sit at the end of a
  line.

**Relative to the textbook version.** Donovan and Kernighan's _Writing an Interpreter in
Go_ goes lexer → Parser → AST → `eval` → bytecode VM, where a `Compiler` emits opcodes
that a stack machine executes. I stopped at `eval` and did not implement the bytecode
tier. The trade is that a tree walker pays a Python function call per AST node and
reuses the host's frame size, while a VM centralises dispatch and can add fast paths
such as fused index-and-jump instructions. I did not need those for a language over JSON.

Their lexer is table-driven over byte values with a longest-match rule. Mine is a
hand-written scanner whose named token sets — `OPENERS`, `CLOSERS`, `ENDS_STATEMENT` —
exist to serve the newline rule rather than to drive a DFA. From the book and from K&R I
kept the hand-written scanner and the practice of carrying `line`/`col` through the token
stream into every AST node. From SICP I took the `eval` loop and the
closure-as-environment model. From jq I took the pipeline model and the two-value
truthiness rule.

I dropped several things the book implements: variable-length string tokens, a `switch`
statement, a `while` loop, and multi-statement function bodies. I also dropped what the
README lists as absent — no `while`, `break`/`continue`, regex, slices, optional
chaining, modules or pattern matching.

**Orientation for a reader.** The lexer owns layout, the parser owns syntax, the
interpreter owns semantics. `BUILTINS` at the bottom of `interp.py` is a flat registry,
so adding a function is a single `@_b("name")` line. `parse_pipe` and `Interp.pipe` are
the two places where the central design decision — pipe as argument reordering — is
actually implemented, and they are worth reading together.

## (b) The tool

`soq.py` exposes four subcommands: `run FILE`, `-e CODE`, `json FILE [CODE]`, and
`tokens FILE`. The last one prints the raw token stream with positions, which is how the
newline rules can be inspected directly.

The pipeline is the algorithm, and there is no separate algorithm inside the language.
`|>` is argument reordering: `xs |> map(f)` is exactly `map(f, xs)`, so a pipeline is a
chain of ordinary calls, and the evaluator has no concept of a pipeline beyond the single
`Interp.pipe` method. The relevant code is therefore in three places: `parse_pipe`
(grammar), `Interp.pipe` (the desugaring), and the `@_b` builtins that form the
pipeline's vocabulary — `map`, `select`, `reduce`, `sort_by`, `group_by`.

**Interface decisions.**

- **The pipe appends the value as the last argument.** The consequence is that the
  convention is uniform and checkable by eye: `def add(a, b) = a - b` with
  `print(10 |> add(3))` prints `-7`, since the piped value becomes the second argument.
- **Function bodies are expressions, so `fn` is first-class.** `map(double)` and
  `map(fn(x) = x * 2)` are interchangeable, and `select`, `sort_by`, `group_by`, `any`
  and `all` all accept a function through the same mechanism. There is one calling
  convention and no special-casing.
- **Errors carry source positions.** `SoqError(msg, line, col)`, with line and column
  stored on every token and every node. The CLI catches `SoqError` once and reports
  `-e: 2:3: index 3 out of range`. `TypeError`, `IndexError` and `ZeroDivisionError`
  raised inside a builtin are re-wrapped with the builtin name, so a program never
  produces a Python traceback. `RecursionError` is caught separately and reported as
  `call stack too deep (is a function recursing forever?)`.
- **`load_json` and `dump_json` live in `soq.py`, not `interp.py`**, so the interpreter
  has no knowledge of the filesystem.
- **`print` and `println` buffer into `interp.out`** rather than writing to stdout, which
  lets tests assert on output without capturing it.
- **`tokens` exists as a debugging subcommand.** It is the only way to see the newline
  rules act on a given program.

**Worked example.** `examples/orders.json` holds four orders;
`examples/orders.soq` summarises them.

```soq
# Summarise a set of orders. Reads examples/orders.json.
let orders = load_json("examples/orders.json")

let expensive = orders
  |> select(fn(o) = o.total > 100)
  |> map(fn(o) = { customer: o.customer, total: o.total })

let revenue = expensive
  |> reduce(fn(acc, o) = acc + o.total, 0)

println(len(expensive), "expensive orders, revenue", revenue)
```

```console
$ python3 soq.py run examples/orders.soq
1 expensive orders, revenue 240
all 4 orders, total 334.5
[
  {
    "customer": "alan",
    "total": 240
  }
]
```

The pipeline spans three source lines. Each `|>` begins its line rather than ending the
previous one, so the lexer must look past the newline to decide whether to emit a
statement terminator. The `for` loop below it accumulates the grand total by ordinary
mutation, since `for` is a statement and the loop variable is rebound each iteration.

The same query as a one-liner, with no named function and no intermediate binding:

```console
$ python3 soq.py json examples/orders.json \
    'input |> map(fn(o) = o.total) |> sum |> print'
334.5

$ python3 soq.py json examples/orders.json \
    'input |> group_by(fn(o) = o.customer) |> keys |> print'
{ada: [...], alan: [...], grace: [...]}
```

`group_by` is worth noting for a jq reader: it returns an object keyed by the _printed_
form of the key, so a numeric key such as `x % 2` becomes the string `"0"` or `"1"`.
That matches jq, where object keys are strings by definition, but it is not what a Python
reader expects from `group_by`.

## (c) What I learned

### The layout rule

My first approach was automatic semicolon insertion: keep parser state recording whether
a newline might terminate a statement, and hedge. That is a state machine with several
interacting conditions. What I ended up with is one predicate and one integer:

```python
if c == "\n":
    self.bump()
    if self.depth > 0 or self.last not in ENDS_STATEMENT:
        return self.next_token()          # inside brackets, or cannot end: not a terminator
    if self.next_line_starts_pipe():
        return self.next_token()          # pipeline continues: not a terminator
    return self.emit("NEWLINE", "\n", None, at)
```

`ENDS_STATEMENT` answers "could the previous token end a statement?" and `depth` answers
"are we inside brackets?". Every expression that legitimately spans lines does so inside
brackets, so nesting needs no bookkeeping. The third condition is a two-character
lookahead for `|>`.

Every newline is decided by that one `if`. Layout is not inherently the messy part of an
implementation; it is messy only when the decision is global to the parse rather than
local to one token pair.

### Mistakes

**Every type error in the standard library is reported in the wrong language.**
`SoqError.__init__` takes `(msg, line, col)`. All 49 `raise SoqError(...)` sites in
`interp.py` pass one argument, so the constructor raises before the error is delivered:

```console
$ python3 soq.py -e 'len(1)'
-e: 1:10: len: SoqError.__init__() missing 2 required positional arguments: 'line' and 'col'
```

The CLI catches the `TypeError` and re-wraps it with the builtin name, so there is no
traceback and the exit code is right. The message is a complaint about my own exception
class. `_num`, `_str`, `_list` and `_obj` are built this way, so it covers every builtin
that validates an argument, and the tests miss it because the only two assertions on these
strings check the prefix. The builtins receive `(interp, *args)` with no access to the
call node, so they have nothing to pass. Fixing it means threading the call site through
the call path.

**A pipe into a field reads the wrong object.** `xs |> d.a` should be `d.a` on the piped
value. It returns `d.a` on the global `d`:

```console
$ python3 soq.py -e 'let d = {a: 1}
let xs = {a: 99}
print(xs |> d.a)'
1
```

`Interp.pipe` sends a `field` target to `field_chain`, which does
`env.lookup(target.a.a)` when the base is a name and never reads the value `pipe` passes
in. I had written this down as an unreachable branch. It is reachable, and wrong. `xs |>
(fn(a) = ...)` reaches the lambda branch too, but only with parentheses.

**A two-character token silently consumed an existing one.** I wanted `//` for floor
division. The lexer already treats `//` as a comment, so `print(7 // 2)` lexes as
`print(7` and fails with `expected ')', found EOF`, a parser error pointing at the wrong
stage. Any two-character token I add can silently eat a pair that already means something.
Carrying positions on every token is why this surfaced in one run.

**The bracket-depth counter was not sufficient, and not for the reason I expected.** Depth
handles a multi-line object literal correctly. It does not handle a line _ending_ in an
operator at depth 0. My first rule asked whether the next token could begin a statement,
which has no useful answer, because `+ 2` is a legal unary expression.

**The README documented a command that prints nothing.** `python3 soq.py json data.json
'input |> len'` is in the README and prints nothing, because `exec_stmt` evaluates a bare
expression and discards the value. I designed the subcommand expecting an implicit final
print, then built `run()` to return a value the way a textbook eval loop does, and never
reconciled the two. I did fix the no-CODE case: `soq json FILE` now runs `print(input)`,
the only source change I made while writing these reports. The explicit case is
outstanding, because printing the return value only when the program produced no output
sets a precedence between implicit and explicit output I am not satisfied with.

### Other findings

**A tree-walking interpreter inherits the host's recursion limit.** Each soq call costs
roughly five Python frames, so I set `sys.setrecursionlimit(20000)`. `fib(24)` is 150,049
calls at about 2.3 µs. Recursion to 3,300 works and 3,400 does not; 100,000 is caught and
reported rather than crashing. This is the concrete argument for the bytecode tier, where
a VM has its own stack and frame size. A `while` loop would have sidestepped the limit
here, which is an argument for having one.

**Removing block syntax removed four separate problems.** Without blocks there is no
dangling-else ambiguity, no block-versus-object-literal ambiguity at `{`, no question of
what a function body's value is, and no `do`/`end` versus `{}` delimiter to choose. I
expected to cut features and pay for it in expressiveness. The reduction in parser
complexity was larger than the cost.

**Source positions are the cheapest feature in the language.** Six slots and two branches
in `bump()` are the whole cost, and they are the difference between `expected an
expression` and `2:3: expected an expression`.

**Only `false` and `null` are falsey, which changes what `or` means.** `0 or "fallback"` is
`0`. I took this from jq to stop an empty result silently disappearing, as Python's `if xs:`
does. The connection I missed is that it is what makes `or` useful as a fallback: `and`
and `or` return an operand, not a boolean, so `x or default` only works if truthiness
means "not null" rather than "not empty".

**Two known differences from jq.** Numbers are Python `int` and `float`, so `1 == 1.0` is
`true` and `0.1 + 0.2` prints `0.30000000000000004`. And `keys`, `values` and `to_entries`
iterate sorted, costing O(k log k) per call and buying deterministic output, which makes
the tests reliable.

### References

- Ball, T. _Writing an Interpreter in Go._ Leanpub, 2016. Correcting an earlier draft that
  credited Donovan and Kernighan and gave Manning as the publisher.
- Nystrom, R. _Crafting Interpreters._ 2020.
- Kernighan and Ritchie. _The C Programming Language._ 2nd ed., 1988.
- Abelson and Sussman. _Structure and Interpretation of Computer Programs._ 2nd ed., 1996.

# (D) Ai Use

I wrote the lexer portion of the program by hand and wrote the spec for the language. However, for the parser, interpreter, standard library and test suite, I used GLM 4.6 to write me the implementation from the spec I wrote. I also used GLM 4.6 to also help me format and reword my report: I first wrote down all of my thoughts, ideas and references I had during the project as dot points so that all of the neccessary information was noted down. Then I worked through with the AI to create a structure for the report, and to then convert all of my dot points and loose paragraphs into a proper report following the structure.

**Issues I encounted with the AI**
The first issue I encountered with AI use was overbloating of the report, the Ai would extrapolate too much from the core information, and intersperse the text with narrative speech and connective sentences that provided no value to the report. That meant that I had to go through the report and trim the fat on most of the content so that the report would not be too long in the end.
The second major issue i had was with the `SoqError` error logging helper. Despite the parameter explicitly requiring three inputs (row, column, message), all instances of the exception being raised in `interp.py` only passed the message. Leading to every debug statement causing a function call arity error rather than the actually helpful function specific error message.

**What Im still not sure about**
While most of the project remains intuitive for me to understand, I have been reliant on the AI to provide test suites for the project, and thus I am not sure whether all edge cases are handled or not. Since the project is quite large, I am not able to vet every function myself for errors and for correctness according to the assumptions I had whilst writing the specification.
