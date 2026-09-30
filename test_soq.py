import unittest

from interp import Interp, SoqError, show
from lexer import tokenize
from parser import parse


def kinds(src):
    got = [t.kind for t in tokenize(src)]
    if got and got[-1] == "EOF":
        got = got[:-1]
    if got and got[-1] == "NEWLINE":
        got = got[:-1]
    return got


def run(src):
    interp = Interp()
    interp.run(parse(src))
    return interp


def value(src):
    return run("let out = " + src).global_env.lookup("out", (0, 0))


def out(src):
    return run(src).out


class TestLexer(unittest.TestCase):
    def test_kinds(self):
        self.assertEqual(kinds("let x = 1")[:4],
                         ["LET", "IDENT", "ASSIGN", "NUMBER"])
        self.assertEqual(kinds("|> . [ ] { }"), ["PIPE", "DOT", "LBRACK",
                                                 "RBRACK", "LBRACE", "RBRACE"])
        self.assertEqual(kinds("a == b != c"), ["IDENT", "EQ", "IDENT",
                                                "NEQ", "IDENT"])
        self.assertEqual(kinds("a <= b >= c"), ["IDENT", "LE", "IDENT",
                                                "GE", "IDENT"])

    def test_numbers(self):
        self.assertEqual(value("42"), 42)
        self.assertEqual(value("3.5"), 3.5)
        self.assertEqual(value("1e3"), 1000.0)
        self.assertEqual(value("2.5e-2"), 0.025)
        self.assertEqual(kinds("1..5"), ["NUMBER", "DOT", "DOT", "NUMBER"])
        self.assertEqual(kinds("x.0"), ["IDENT", "DOT", "NUMBER"])
        self.assertEqual(kinds("1e"), ["NUMBER", "IDENT"])

    def test_strings(self):
        self.assertEqual(value(r'"a\nb"'), "a\nb")
        self.assertEqual(value(r'"A"'), "A")
        self.assertEqual(value("'hi'"), "hi")
        self.assertEqual(value(r'"\""'), '"')

    def test_literal_unicode(self):
        self.assertEqual(value('"héllo"'), "héllo")
        self.assertEqual(value('"✓ 🎉"'), "✓ 🎉")
        self.assertEqual(value('len("✓🎉")'), 2)

    def test_comments(self):
        self.assertEqual(kinds("a # hi"), ["IDENT"])
        self.assertEqual(kinds("a // hi"), ["IDENT"])
        self.assertEqual(kinds("# whole line"), [])

    def test_newlines(self):
        self.assertEqual(kinds("a\nb"), ["IDENT", "NEWLINE", "IDENT"])
        self.assertEqual(kinds("a +\nb"), ["IDENT", "PLUS", "IDENT"])
        self.assertEqual(kinds("a |>\nb"), ["IDENT", "PIPE", "IDENT"])
        self.assertEqual(kinds("f(a,\nb)"),
                         ["IDENT", "LPAREN", "IDENT", "COMMA", "IDENT",
                          "RPAREN"])
        self.assertEqual(kinds("[\n1\n]"), ["LBRACK", "NUMBER", "RBRACK"])
        self.assertEqual(kinds("a\n\nb"), ["IDENT", "NEWLINE", "IDENT"])

    def test_leading_pipe_continues_a_pipeline(self):
        self.assertEqual(kinds("a\n|> b"), ["IDENT", "PIPE", "IDENT"])
        self.assertEqual(kinds("a\n  |> b\n  |> c"),
                         ["IDENT", "PIPE", "IDENT", "PIPE", "IDENT"])
        self.assertEqual(kinds("a\n\n  |> b"), ["IDENT", "PIPE", "IDENT"])
        self.assertEqual(kinds("a\n  # note\n  |> b"),
                         ["IDENT", "PIPE", "IDENT"])
        self.assertEqual(kinds("a\n  // note\n  |> b"),
                         ["IDENT", "PIPE", "IDENT"])
        self.assertEqual(kinds("a\nb"), ["IDENT", "NEWLINE", "IDENT"])
        self.assertEqual(kinds("a\n  + b"), ["IDENT", "NEWLINE", "PLUS", "IDENT"])

    def test_positions(self):
        toks = tokenize("let x = 1\nlet y = 2\n")
        self.assertEqual((toks[0].line, toks[0].col), (1, 1))
        self.assertEqual((toks[1].line, toks[1].col), (1, 5))
        self.assertEqual((toks[5].line, toks[5].col), (2, 1))

    def test_errors(self):
        for src, frag in [('"abc', "unterminated string"),
                          (r'"\q"', "unknown escape"),
                          (r'"\u0041"', "unknown escape"),
                          ("a @ b", "unexpected character"),
                          ("a | b", "did you mean"),
                          ("'a\nb'", "unterminated string")]:
            with self.assertRaises(SoqError, msg=src):
                tokenize(src)


class TestParser(unittest.TestCase):
    def test_precedence(self):
        self.assertEqual(value("1 + 2 * 3"), 7)
        self.assertEqual(value("(1 + 2) * 3"), 9)
        self.assertEqual(value("2 * 3 + 1"), 7)
        self.assertEqual(value("10 - 2 - 3"), 5)
        self.assertEqual(value("2 + 3 * 4 - 6 / 3"), 12)

    def test_not_binds_looser_than_comparison(self):
        self.assertEqual(value("not 1 == 2"), True)
        self.assertEqual(value("not 1 == 1"), False)

    def test_and_or(self):
        self.assertEqual(value("true and false"), False)
        self.assertEqual(value("true or false"), True)
        self.assertEqual(value("1 and 2"), 2)
        self.assertEqual(value("null or 7"), 7)

    def test_collections(self):
        self.assertEqual(value("[]"), [])
        self.assertEqual(value("[1, 2, 3]"), [1, 2, 3])
        self.assertEqual(value("{}"), {})
        self.assertEqual(value("{a: 1, b: 2}"), {"a": 1, "b": 2})
        self.assertEqual(value('{"a b": 1}'), {"a b": 1})
        self.assertEqual(value("[[1, 2], [3]]"), [[1, 2], [3]])

    def test_access(self):
        self.assertEqual(value("[10, 20, 30][1]"), 20)
        self.assertEqual(value("[10, 20, 30][-1]"), 30)
        self.assertEqual(value("{a: {b: 7}}.a.b"), 7)
        self.assertEqual(value('{a: 1}["a"]'), 1)

    def test_if(self):
        self.assertEqual(value("if true then 1 else 2"), 1)
        self.assertEqual(value("if false then 1 else 2"), 2)
        self.assertEqual(value("if false then 1"), None)
        self.assertEqual(value("if 1 then 2 else 3"), 2)

    def test_comments_and_newlines_in_brackets(self):
        self.assertEqual(value("[\n  1,  # one\n  2  # two\n]"), [1, 2])
        self.assertEqual(value("{\n a: 1,\n b: 2\n}"), {"a": 1, "b": 2})

    def test_statements(self):
        self.assertEqual(out("let a = 1\nlet a = a + 1\nprint(a)"), ["2"])
        self.assertEqual(out("let x = 1; print(x)"), ["1"])
        self.assertEqual(out("print(1)\n\n\nprint(2)"), ["1", "2"])

    def test_errors(self):
        for src, frag in [("let = 1", "expected"),
                          ("let x = ", "expected an expression"),
                          ("f(1", "expected"),
                          ("1 +", "expected an expression"),
                          ("[1, 2", "expected"),
                          ("if true 1", "expected")]:
            with self.assertRaises(SoqError, msg=src):
                parse(src)


class TestPipe(unittest.TestCase):
    def test_basics(self):
        self.assertEqual(value("[1, 2, 3] |> len"), 3)
        self.assertEqual(value("[1, 2, 3] |> sum"), 6)
        self.assertEqual(value("[1, 2, 3] |> map(fn(x) = x * 2)"), [2, 4, 6])
        self.assertEqual(value("[1, 2, 3] |> select(fn(x) = x > 1)"), [2, 3])
        self.assertEqual(value("[1, 2] |> first"), 1)

    def test_pipe_calls_a_function(self):
        self.assertEqual(out("let a = {b: [1, 2]}\n"
                             "def get(o) = o.b\n"
                             "print(a |> get |> len)"), ["2"])

    def test_spans_several_lines(self):
        self.assertEqual(
            out("let xs = [1, 2, 3]\n"
                "let r = xs\n"
                "  |> map(fn(x) = x * 3)\n"
                "  |> sum\n"
                "print(r)"),
            ["18"])

    def test_value_is_the_last_argument(self):
        self.assertEqual(out("def add(a, b) = a - b\nprint(10 |> add(3))"),
                         ["-7"])

    def test_chain(self):
        self.assertEqual(
            value("[1, 2, 3, 4] |> map(fn(x) = x * 2) "
                  "|> select(fn(x) = x > 4) |> sum"),
            14)

    def test_equivalent_to_call(self):
        self.assertEqual(value("[1, 2] |> sum"), value("sum([1, 2])"))
        self.assertEqual(value("[1, 2] |> len"), value("len([1, 2])"))


class TestFunctions(unittest.TestCase):
    def test_def(self):
        self.assertEqual(out("def f(x) = x * 2\nprint(f(3))"), ["6"])
        self.assertEqual(out("def add(a, b) = a + b\nprint(add(2, 3))"), ["5"])
        self.assertEqual(out("def f() = 1\nprint(f())"), ["1"])

    def test_recursion(self):
        self.assertEqual(
            out("def fib(n) = if n < 2 then n else fib(n - 1) + fib(n - 2)\n"
                "print(fib(10))"),
            ["55"])

    def test_closure(self):
        self.assertEqual(
            out("def outer(a) = fn(b) = a + b\n"
                "let add5 = outer(5)\nprint(add5(3))"),
            ["8"])

    def test_early_binding(self):
        self.assertEqual(out("def g() = 7\ndef f() = g()\nprint(f())"), ["7"])

    def test_shadowing(self):
        self.assertEqual(out("def f(x) = 1\nprint(f(9))"), ["1"])

    def test_deep_recursion(self):
        self.assertEqual(
            out("def down(n) = if n == 0 then 0 else down(n - 1)\n"
                "print(down(400))"),
            ["0"])

    def test_runaway_recursion_is_reported(self):
        with self.assertRaises(RecursionError):
            run("def loop(n) = loop(n + 1)\nloop(0)")

    def test_errors(self):
        for src, frag in [("def f(x) = x\nf()", "expects 1"),
                          ("def f(x) = x\nf(1, 2)", "expects 1"),
                          ("1(2)", "cannot call")]:
            with self.assertRaises(SoqError, msg=src):
                Interp().run(parse(src))


class TestStatements(unittest.TestCase):
    def test_for(self):
        self.assertEqual(
            out("let s = 0\nfor x in [1, 2, 3] do s = s + x\nprint(s)"),
            ["6"])

    def test_assign_targets(self):
        self.assertEqual(out("let a = [1]\na[0] = 9\nprint(a)"), ["[9]"])
        self.assertEqual(out("let a = {x: 1}\na.x = 9\nprint(a)"), ["{x: 9}"])

    def test_scoping(self):
        self.assertEqual(
            out("let x = 1\nfor x in [9, 9] do print(x)\nprint(x)"),
            ["9", "9", "1"])

    def test_errors(self):
        for src, frag in [("print(nope)", "undefined"),
                          ("nope = 1", "undefined"),
                          ("let a = 1\nfor x in a do print(x)", "cannot loop")]:
            with self.assertRaises(SoqError, msg=src):
                Interp().run(parse(src))


class TestValues(unittest.TestCase):
    def test_truthiness(self):
        self.assertEqual(value("if 0 then 1 else 2"), 1)
        self.assertEqual(value('if "" then 1 else 2'), 1)
        self.assertEqual(value("if [] then 1 else 2"), 1)
        self.assertEqual(value("if null then 1 else 2"), 2)
        self.assertEqual(value("if false then 1 else 2"), 2)

    def test_equality(self):
        self.assertEqual(value("[1, [2]] == [1, [2]]"), True)
        self.assertEqual(value("{a: 1, b: 2} == {b: 2, a: 1}"), True)
        self.assertEqual(value("{a: 1} == {a: 2}"), False)
        self.assertEqual(value("1 == 1.0"), True)
        self.assertEqual(value("true == 1"), False)

    def test_operators(self):
        self.assertEqual(value("7 / 2"), 3.5)
        self.assertEqual(value("7 % 3"), 1)
        self.assertEqual(value('"a" + "b"'), "ab")
        self.assertEqual(value("[1] + [2]"), [1, 2])
        self.assertEqual(value("-5"), -5)
        self.assertEqual(value('"b" > "a"'), True)

    def test_errors(self):
        for src, frag in [('1 + "a"', "cannot add"),
                          ("1 - 'a'", "cannot subtract"),
                          ('1 < "a"', "cannot compare"),
                          ("1 / 0", "division by zero"),
                          ("[1][5]", "out of range"),
                          ("[1][0.5]", "cannot index"),
                          ("{}.a", "has no key"),
                          ("1.a", "cannot read field"),
                          ('"ab"[9]', "out of range")]:
            with self.assertRaises(SoqError, msg=src):
                value(src)


class TestBuiltins(unittest.TestCase):
    def test_data(self):
        self.assertEqual(value("len([1, 2])"), 2)
        self.assertEqual(value('len("abc")'), 3)
        self.assertEqual(value('keys({b: 1, a: 2})'), ["a", "b"])
        self.assertEqual(value("values({b: 1, a: 2})"), [2, 1])
        self.assertEqual(value('has({a: 1}, "a")'), True)
        self.assertEqual(value('get({a: 1}, "b")'), None)
        self.assertEqual(value('set({}, "a", 1)'), {"a": 1})
        self.assertEqual(value("sort([3, 1, 2])"), [1, 2, 3])
        self.assertEqual(value("sort_by(fn(x) = -x, [1, 3, 2])"), [3, 2, 1])
        self.assertEqual(value("group_by(fn(x) = x % 2, [1, 2, 3])"),
                         {"1": [1, 3], "0": [2]})
        self.assertEqual(value("unique([1, 1, 2])"), [1, 2])
        self.assertEqual(value("reverse([1, 2])"), [2, 1])
        self.assertEqual(value("take(2, [1, 2, 3])"), [1, 2])
        self.assertEqual(value("skip(1, [1, 2, 3])"), [2, 3])
        self.assertEqual(value("flatten([[1], [2, 3]])"), [1, 2, 3])
        self.assertEqual(value("range(3)"), [0, 1, 2])
        self.assertEqual(value("range(1, 4)"), [1, 2, 3])
        self.assertEqual(value("range(3, 0, -1)"), [3, 2, 1])
        self.assertEqual(value("min([3, 1])"), 1)
        self.assertEqual(value("max([3, 1])"), 3)
        self.assertEqual(value("sum([1, 2])"), 3)
        self.assertEqual(value("first([1, 2])"), 1)
        self.assertEqual(value("last([1, 2])"), 2)
        self.assertEqual(value("any(fn(x) = x > 2, [1, 3])"), True)
        self.assertEqual(value("all(fn(x) = x > 2, [1, 3])"), False)
        self.assertEqual(value('to_entries({a: 1})'), [{"key": "a", "value": 1}])
        self.assertEqual(value('from_entries([{key: "a", value: 1}])'), {"a": 1})

    def test_strings(self):
        self.assertEqual(value('upper("ab")'), "AB")
        self.assertEqual(value('lower("AB")'), "ab")
        self.assertEqual(value('trim("  a  ")'), "a")
        self.assertEqual(value('split(",", "a,b")'), ["a", "b"])
        self.assertEqual(value('join("-", [1, 2])'), "1-2")
        self.assertEqual(value('replace("a", "b", "aa")'), "bb")
        self.assertEqual(value('starts_with("ab", "abc")'), True)
        self.assertEqual(value('ends_with("bc", "abc")'), True)
        self.assertEqual(value('contains("b", "abc")'), True)
        self.assertEqual(value('contains(2, [1, 2])'), True)

    def test_types(self):
        self.assertEqual(value("type_of(1)"), "number")
        self.assertEqual(value('type_of("a")'), "string")
        self.assertEqual(value("type_of([])"), "array")
        self.assertEqual(value("type_of({})"), "object")
        self.assertEqual(value("type_of(null)"), "null")
        self.assertEqual(value("type_of(true)"), "boolean")
        self.assertEqual(value("str(1)"), "1")
        self.assertEqual(value('int("42")'), 42)
        self.assertEqual(value('int(1.9)'), 1)
        self.assertEqual(value('float("1.5")'), 1.5)
        self.assertEqual(value("is_null(null)"), True)
        self.assertEqual(value("not false"), True)

    def test_display(self):
        self.assertEqual(value("str([1, 2])"), "[1, 2]")
        self.assertEqual(value("str({a: 1})"), "{a: 1}")
        self.assertEqual(value("str({'a b': 1})"), '{"a b": 1}')
        self.assertEqual(value("str(null)"), "null")
        self.assertEqual(value("str(1.5)"), "1.5")
        self.assertEqual(value("str(3.0)"), "3")

    def test_errors(self):
        for src, frag in [("len(1)", "does not work"),
                          ("keys(1)", "does not work"),
                          ("map(1, [1])", "expects a function"),
                          ("map(fn(x) = x)", "expects 2"),
                          ('upper(1)', "expects a string")]:
            with self.assertRaises(SoqError, msg=src):
                value(src)


class TestErrorPositions(unittest.TestCase):
    def error(self, src):
        with self.assertRaises(SoqError, msg=src):
            run(src)
        try:
            run(src)
        except SoqError as e:
            return e

    def test_builtin_type_errors_carry_a_position(self):
        for src, frag in [("len(1)", "len does not work on number"),
                          ("keys(1)", "keys does not work on number"),
                          ("upper(1)", "upper expects a string, got number"),
                          ("sum(1)", "sum expects an array, got number"),
                          ('int("x")', 'cannot read a number from "x"')]:
            e = self.error(src)
            self.assertEqual(e.msg, frag, msg=src)
            self.assertEqual((e.line, e.col), (1, src.index("(") + 1), msg=src)
            self.assertEqual(str(e), f"1:{src.index('(') + 1}: {frag}", msg=src)

    def test_builtin_arity_errors_are_soq_errors(self):
        for src, frag in [("sort_by(1)", "sort_by expects 2 argument(s), got 1"),
                          ("len()", "len expects 1 argument(s), got 0"),
                          ("upper()", "upper expects 1 argument(s), got 0"),
                          ("range(1, 2, 3, 4)", "range expects 1 to 3 argument(s), got 4")]:
            e = self.error(src)
            self.assertEqual(e.msg, frag, msg=src)
            self.assertEqual((e.line, e.col), (1, src.index("(") + 1), msg=src)

    def test_errors_from_inside_a_higher_order_builtin_are_positioned(self):
        for src in ["map(1, [1])", "any(1, [1])", "select(1, [1])",
                    "reduce(1, 1, [1])", "sort_by(1, [1])", "group_by(1, [1])",
                    "all(1, [1])", "filter(1, [1])"]:
            e = self.error(src)
            self.assertEqual((e.line, e.col), (1, src.index("(") + 1), msg=src)
            self.assertIn("cannot call a", e.msg, msg=src)

    def test_error_text_is_the_raw_message(self):
        self.assertNotIn("SoqError", str(self.error("len(1)")))
        self.assertNotIn("Traceback", str(self.error("len(1)")))

    def test_variadic_builtins_still_accept_any_arity(self):
        self.assertEqual(out("print(1, 2, 3)"), ["1 2 3"])
        self.assertEqual(out('print()'), [""])


class TestPipeField(unittest.TestCase):
    def test_piped_value_is_the_receiver(self):
        self.assertEqual(out("let xs = {a: 99}\nprint(xs |> d.a)"), ["99"])

    def test_placeholder_may_be_undefined(self):
        self.assertEqual(out("let xs = {a: 99}\nprint(xs |> nope.a)"), ["99"])

    def test_postfix_chain_applies_to_the_piped_value(self):
        self.assertEqual(out("let xs = {a: {b: 7}}\nprint(xs |> d.a.b)"), ["7"])
        self.assertEqual(out("let xs = {a: [1, 2]}\nprint(xs |> d.a[1])"), ["2"])

    def test_matches_the_index_branch(self):
        self.assertEqual(out("let xs = [1, 2]\nprint(xs |> d[0])"), ["1"])

    def error(self, src):
        with self.assertRaises(SoqError, msg=src):
            run(src)
        try:
            run(src)
        except SoqError as e:
            return e

    def test_type_and_key_errors(self):
        for src, frag in [("print([1,2] |> d.a)",
                           "cannot read field 'a' of a array value"),
                          ("let xs = {a: 1}\nprint(xs |> d.zz)",
                           "object has no key 'zz'"),
                          ("print(1 |> d.a)",
                           "cannot read field 'a' of a number value")]:
            e = self.error(src)
            self.assertIn(frag, e.msg, msg=src)
            self.assertNotEqual(e.line, 0, msg=src)


class TestExamples(unittest.TestCase):
    def test_tour_runs(self):
        import soq
        with open("examples/tour.soq") as fh:
            interp = soq.run_source(fh.read(), [])
        self.assertIn("fib(10) = 55", interp.out)
        self.assertIn("pipeline: 10", interp.out)
        self.assertIn("acc: 2", interp.out)

    def test_orders_runs(self):
        import soq
        with open("examples/orders.soq") as fh:
            interp = soq.run_source(fh.read(), [])
        self.assertIn("1 expensive orders, revenue 240", interp.out)
        self.assertIn("all 4 orders, total 334.5", interp.out)


if __name__ == "__main__":
    unittest.main(verbosity=2)
