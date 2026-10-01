# soq

A small data-oriented scripting language based on jq's pipeline model with a
statement-based syntax, so everyday scripts read top to bottom.

```soq
let orders = load_json("orders.json")

let big_spenders = orders
  |> select(fn(o) = o.total > 100)
  |> map(fn(o) = { customer: o.customer, total: o.total })
  |> sort_by(fn(o) = o.total)

for o in big_spenders do println(o.customer, "spent", o.total)
```

## Running it

No dependencies, no build step, Python 3.8+.

```
python3 soq.py run examples/tour.soq        # run a program
python3 soq.py run examples/tour.soq a b c  # ...with arguments
python3 soq.py -e 'print(1 + 1)'            # one-liner
python3 soq.py json data.json 'print(input |> len)'
python3 soq.py tokens examples/tour.soq     # dump the token stream
python3 -m unittest test_soq                 # run the tests
```

## The language

Values are `null`, booleans, numbers, strings, arrays, and objects. Arrays and
objects are mutable; everything else behaves the way it prints.

```soq
let x = 1                 # declare, then assign later
x = 2
def f(a, b) = a + b       # named function
let g = fn(x) = x * 2     # anonymous
for item in xs do ...     # one-statement loop body
```

Operators, loosest to tightest:

|                |                  |
| -------------- | ---------------- |
| pipe           | `\|>`            |
| or             | `or`             |
| and            | `and`            |
| not            | `not`            |
| equality       | `== !=`          |
| comparison     | `< <= > >=`      |
| additive       | `+ -`            |
| multiplicative | `* / %`          |
| unary          | `-x`             |
| postfix        | `f(x) xs[i] o.k` |

`and` and `or` short-circuit and return one of their operands, so
`x or default` picks a fallback when `x` is falsey or `null`.

## Standard library

All of it takes data as the final argument, so it composes with `|>`.

- **Data** `len` `keys` `values` `has` `get` `set` `type_of` `is_null`
- **Transform** `map` `select` `filter` `reject` `reduce` `sort` `sort_by` `group_by` `unique` `reverse` `take` `skip` `flatten`
- **Aggregate** `range` `min` `max` `sum` `first` `last` `any` `all`
- **Objects** `to_entries` `from_entries`
- **Strings** `upper` `lower` `trim` `split` `join` `replace` `starts_with` `ends_with` `contains`
- **Convert** `str` `int` `float` `to_json` `is_null` `not` `print` `println`
- **I/O** `load_json` `dump_json` (in `soq.py`, since they touch the filesystem)

`args` holds the arguments passed after the script name. The full reference,
including the signature and behaviour of every builtin, is in `REFERENCE.md`.

## Deliberately absent

No `while`, no `break`/`continue`, no regex, no slices, no optional chaining,
no modules, no pattern matching. Loops with a single-statement body plus
`map`/`reduce` and recursion cover iteration, and every feature that is gone
is one the report does not need.
