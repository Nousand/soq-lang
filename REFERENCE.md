# soq language reference

## Running

```
python3 soq.py run FILE [args]    run a program
python3 soq.py -e CODE [args]     run a one-liner
python3 soq.py json FILE [CODE]   load JSON into `input` (default: print input)
python3 soq.py tokens FILE        print the token stream with positions
```

## Lexical structure

**Comments** run from `//` to end of line. There are no block comments.

**Identifiers** start with a letter or `_`, then letters, digits or `_`.

**Keywords**: `let` `def` `fn` `if` `then` `else` `for` `in` `do` `and` `or`
`not` `true` `false` `null`. Anything else is an identifier.

**Numbers** are decimal, with an optional fraction and an optional exponent.
`007`, `1.5`, `1e3` and `1.5e-2` are all valid. There is no hex and no leading
dot, so `.5` is a parse error and `1.` reads as the number `1` followed by a
field access.

**Strings** use `"` or `'`. The escapes are `\n` `\t` `\r` `\0` `\\` `\"` `\'`.
Anything else, including `\u`, is an error.

**Newlines** end statements. A newline is ignored when you are inside `(`, `[`
or `{`, or when the previous token cannot end a statement, which is why
operators sit at the end of a line. `;` also separates statements. The one
exception is a line starting with `|>`, which continues a pipeline.

```
print(1 +
  2)                 # 3

orders
  |> filter(fn(o) = o.ok)
  |> map(fn(o) = o.total)
```

## Values

Six types plus functions. `type_of` returns the name in the third column.

| Literal        | `type_of`  | Printed as     |
| -------------- | ---------- | -------------- |
| `null`         | `null`     | `null`         |
| `true` `false` | `boolean`  | `true` `false` |
| `1` `1.5`      | `number`   | `1` `1.5`      |
| `"a"`          | `string`   | `a`            |
| `[1]`          | `array`    | `[1, a]`       |
| `{a: 1}`       | `object`   | `{a: 1}`       |
| `fn(x) = x`    | `function` | `<fn None>`    |

Numbers with no fractional part print without one, so `3.0` prints as `3`.
Strings print bare inside arrays and objects, which means `["a"]` and `[a]` are
printed the same way. Use `to_json` when you need quoting and structure back.

Object keys print unquoted when they look like identifiers, so
`{a_b: 1, "a b": 2}` prints as `{a_b: 1, "a b": 2}`.

Arrays and objects are mutable. Everything else behaves the way it prints.

**Only `false` and `null` are falsey.** `0`, `""` and `[]` are all true, which
matches jq and avoids an empty result silently disappearing.

```
print(if 0 then "t" else "f")        # t
print(if [] then "t" else "f")       # t
print(null or 7)                     # 7
print(0 or "fallback")               # 0
```

## Variables

`let` declares, plain `=` assigns. Assigning to an undeclared name is an error.

```
let x = 1
x = 2
zz = 3                              # cannot assign to undefined variable 'zz'
```

Blocks have no scope of their own. A `for` loop variable is visible in the body
and gone afterwards, so it does not clobber an outer variable of the same name.
A function body captures the environment it was defined in, by reference, so it
sees later assignments to those names.

```
let x = 0
for x in [1, 2] do print(x)         # prints 1 then 2
print(x)                            # 0, the outer x survived

let n = 1
let f = fn() = n
n = 99
print(f())                          # 99, not 1
```

## Statements

```
let x = 1                 declare
x = 2                     assign to a variable, field or element
def f(a) = a * 2          named function
for item in xs do print(item)
any other expression
```

`for` loops over arrays only. A string or an object is an error, not a silent
one element pass.

Functions have no `do`/`end`, no `return`, and the body is a single expression,
so a function is a value you can pass to `map`.

## Expressions

Loosest binding first.

|                | Operators            |
| -------------- | -------------------- |
| pipe           | `\|>`                |
| or             | `or`                 |
| and            | `and`                |
| not            | `not`                |
| equality       | `==` `!=`            |
| comparison     | `<` `<=` `>` `>=`    |
| additive       | `+` `-`              |
| multiplicative | `*` `/` `%`          |
| unary          | `-x`                 |
| postfix        | `f(x)` `xs[i]` `o.k` |

Operators of the same level are left associative, except `and` and `or`, which
short circuit and return one of their operands.

```
print(-2 + 3)                  # 1
print("a" + "b" == "ab")       # true
print(true and 1 == 1)        # true
print(not 1 == 2)              # true
```

**Arithmetic.** `+` adds numbers and joins strings. `-`, `*`, `/` and `%` are
numbers only, and there is no string repetition. Division is exact, so `1 / 2`
is `0.5`. Modulo follows Python, so `-7 % 3` is `2`.

**Comparison** works on numbers and strings, on nothing else. Arrays and objects
have no order.

**Equality is by value**, recursively, and a boolean never equals a number, so
`true == 1` is `false`.

**Indexing** with an integer reads an array or a string and accepts negatives,
counting from the end. Indexing an object requires a string. Out of range is an
error, unlike `get`.

```
print([1, 2, 3][1], [1, 2, 3][-1])     # 2 3
print("abc"[-1])                       # c
print({a: 1}["a"])                     # 1
```

**Field access** `.name` is only for objects. A missing key is an error, unlike
`get`.

```
print({a: {b: 1}}.a.b)                 # 1
print({a: 1}.zz)                       # object has no key 'zz'
```

**Pipes** pass the left value to the right as the final argument, so
`xs |> map(f)` is `map(f, xs)`. The right side must be a name, a parenthesised
expression, or one of those followed by `.field`, `[index]` or `(args)`.

```
print([1, 2] |> reverse |> last)       # 1
print("a,b" |> split(","))             # [a, b]
```

A field target needs a placeholder name, because there is no bare `.a` form for
the parser to latch onto. The name is never looked up, so the pipe supplies the
receiver and `xs |> anything.a` means `xs.a`. Chained postfix reads along the
piped value.

```
let xs = {a: {b: 7}}
print(xs |> d.a)                       # {b: 7}
print(xs |> d.a.b)                     # 7
print([1, 2] |> d[1])                  # 2
```

**`if` is an expression** and the `else` branch is optional, yielding `null`.

```
print(if false then 1)                 # null
```

## Standard library

Every builtin takes its data as the final argument, so each one pipes.

### One argument

|                                 |                                                         |
| ------------------------------- | ------------------------------------------------------- |
| `len(x)`                        | length of a string, array or object                     |
| `keys(o)`                       | object keys, sorted; array indices                      |
| `values(o)`                     | object values in key order; array elements              |
| `to_entries(x)`                 | `{key, value}` for objects, `{index, value}` for arrays |
| `from_entries(xs)`              | rebuild an object from `key` or `index`                 |
| `sort(xs)`                      | numbers or strings, all of one kind                     |
| `unique(xs)`                    | drops repeats by value, keeping first occurrence        |
| `reverse(x)`                    | array or string                                         |
| `flatten(xs)`                   | one level only                                          |
| `sum(xs)`                       | numbers, `0` when empty                                 |
| `min(xs)` `max(xs)`             | `null` when empty                                       |
| `first(xs)` `last(xs)`          | `null` when empty                                       |
| `upper(s)` `lower(s)` `trim(s)` | whitespace at both ends for `trim`                      |
| `str(v)`                        | the printed form, as a string                           |
| `int(v)` `float(v)`             | also parse a number out of a string                     |
| `type_of(v)`                    | type name                                               |
| `to_json(v)`                    | pretty JSON string                                      |
| `is_null(v)`                    | true only for `null`                                    |
| `not(v)`                        | flips truthiness                                        |

```
print(keys({b: 1, a: 2}), values({b: 1, a: 2}))   # [a, b] [2, 1]
print(flatten([[1], [2, [3]]]))                   # [1, 2, [3]]
print(first([]), sum([]))                         # null 0
print(min([]), max([]))                           # null null
```

`int` and `float` reject a boolean, and `int` truncates: `int("3.7")` is `3`.

### Two arguments

|                                                              |                                                       |
| ------------------------------------------------------------ | ----------------------------------------------------- |
| `range(a, b)` `range(a, b, step)`                            | step defaults to `1`, or `-1` when `b` is smaller     |
| `has(key, o)`                                                | object only                                           |
| `get(key, x)`                                                | object or array, `null` when absent                   |
| `take(n, xs)` `skip(n, xs)`                                  | `n` must be a whole number                            |
| `split(sep, s)`                                              | separator must not be empty                           |
| `join(sep, xs)`                                              | renders each element the way `print` does             |
| `contains(needle, data)`                                     | substring, member, or object key                      |
| `starts_with(pre, s)` `ends_with(suf, s)`                    |                                                       |
| `map(f, xs)` `select(f, xs)` `filter(f, xs)` `reject(f, xs)` | `filter` is `select`, `reject` is the inverse         |
| `sort_by(f, xs)`                                             | ascending on `f`                                      |
| `group_by(f, xs)`                                            | keys are the printed form of `f`, so they are strings |
| `any(f, xs)` `all(f, xs)`                                    | short circuit; `false` and `true` when empty          |

```
print(range(1, 10, 3))                  # [1, 4, 7]
print(range(0, 5, -1))                  # []
print(group_by(fn(x) = x > 1, [1, 2]))  # {false: [1], true: [2]}
print(any(fn(x) = x > 2, [1, 2, 3]))    # true
```

`filter` exists only so a pipeline can be written either way round. It is the
same function as `select`.

`take` and `skip` clamp rather than complain at the end of the array, and treat
a negative count as zero, so `take(-1, [1, 2, 3])` is `[]` and
`skip(-1, [1, 2, 3])` is the whole array. A fractional count is an error, not
rounded.

### Three arguments

|                        |                                            |
| ---------------------- | ------------------------------------------ |
| `reduce(f, init, xs)`  | `f(acc, item)`, `init` returned when empty |
| `set(key, value, o)`   | mutates and returns the object             |
| `replace(old, new, s)` | every occurrence                           |

```
print(reduce(fn(a, b) = a + b, 0, [1, 2, 3]))   # 6
print(set("b", 2, {a: 1}))                      # {a: 1, b: 2}
```

`set` mutates. Assignment through a name, a field or an index does the same, and
objects are references, so this is visible everywhere:

```
let d = {a: {b: 1}}
d.a.b = 2
print(d)                               # {a: {b: 2}}
```

### Variadic, and I/O

`print(...)` joins its arguments with a space, `println` is the same. Both buffer
into an array and the CLI prints it, so output order is program order.

```
print(1, "a", true, null)              # 1 a true null
```

`load_json(path)` and `dump_json(value, path)` live in the CLI rather than the
interpreter, so the interpreter never touches the filesystem. `dump_json` writes
to stdout when given no path.

## Errors

Errors are soq errors, not Python tracebacks, and every one carries a line and
column. They stop the program and exit 1.

```
$ python3 soq.py -e 'print(len(1))'
-e: 1:10: len does not work on number

$ python3 soq.py -e 'let xs = [1]
> print(xs |> d.a)'
-e: 2:14: cannot read field 'a' of a array value

$ python3 soq.py -e 'print(1 / 0)'
-e: 1:9: division by zero
```

Wrong arity is checked before the call runs, and reports the accepted range:

```
print(sort_by(1))        # sort_by expects 2 argument(s), got 1
print(range(1, 2, 3, 4)) # range expects 1 to 3 argument(s), got 4
```

Runaway recursion is reported separately, since it is a limit and not a mistake:

```
$ python3 soq.py -e 'def f(n) = f(n)
f(1)'
-e: call stack too deep (is a function recursing forever?)
```

The interpreter raises CPython's recursion limit, so the usable depth depends on
how many frames a call costs. A plain recursive call reaches about 3,900 levels
and reports the friendly message past that.

## Not in the language

No `while`, no `break` or `continue`, no `do`/`end` blocks, no slices, no regex,
no `try`, no optional chaining, no modules, no pattern matching, no trailing
commas in arrays or objects, and no string interpolation. Iteration is `for`,
`map`, `reduce` and recursion, which between them cover the programs here need.
