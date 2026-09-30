import sys

from lexer import SoqError

# A tree-walking evaluator needs roughly five Python frames per soq call, so
# CPython's default of 1000 only buys about 200 levels of recursion.
sys.setrecursionlimit(20000)


class Function:
    __slots__ = ("name", "params", "body", "env")

    def __init__(self, name, params, body, env):
        self.name, self.params, self.body, self.env = name, params, body, env


class Env:
    def __init__(self, parent=None):
        self.vars = {}
        self.parent = parent

    def get(self, name):
        env = self
        while env is not None:
            if name in env.vars:
                return env
            env = env.parent
        return None

    def lookup(self, name, at):
        env = self.get(name)
        if env is None:
            raise SoqError(f"undefined variable '{name}'", at[0], at[1])
        return env.vars[name]

    def declare(self, name, value):
        self.vars[name] = value

    def assign(self, name, value, at):
        env = self.get(name)
        if env is None:
            raise SoqError(f"cannot assign to undefined variable '{name}'", at[0], at[1])
        env.vars[name] = value


def _is_num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def type_name(v):
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "boolean"
    if isinstance(v, (int, float)):
        return "number"
    if isinstance(v, str):
        return "string"
    if isinstance(v, list):
        return "array"
    if isinstance(v, dict):
        return "object"
    if isinstance(v, Function):
        return "function"
    return "unknown"


def truthy(v):
    return v is not None and v is not False


def equal(a, b):
    if isinstance(a, bool) != isinstance(b, bool):
        return False
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(equal(x, y) for x, y in zip(a, b))
    if isinstance(a, dict) and isinstance(b, dict):
        return set(a) == set(b) and all(equal(a[k], b[k]) for k in a)
    return a == b


def show_key(k):
    if isinstance(k, str) and k and (k[0].isalpha() or k[0] == "_") \
            and all(c.isalnum() or c == "_" for c in k):
        return k
    return quote(k)


def show(v):
    if isinstance(v, str):
        return v
    if v is True:
        return "true"
    if v is False:
        return "false"
    if v is None:
        return "null"
    if isinstance(v, (int, float)):
        return fmt_number(v)
    if isinstance(v, list):
        return "[" + ", ".join(show(x) for x in v) + "]"
    if isinstance(v, dict):
        return "{" + ", ".join(f"{show_key(k)}: {show(x)}" for k, x in v.items()) + "}"
    if isinstance(v, Function):
        return f"<fn {v.name}>"
    return str(v)


def fmt_number(n):
    if isinstance(n, int) or float(n).is_integer():
        return str(int(n))
    return repr(float(n))


def quote(v):
    if isinstance(v, str):
        return '"' + v.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'
    return show(v)


def to_json(v, indent=0):
    pad, pad2 = "  " * indent, "  " * (indent + 1)
    if isinstance(v, dict):
        if not v:
            return "{}"
        items = [f"{pad2}{quote(k)}: {to_json(x, indent + 1)}" for k, x in v.items()]
        return "{\n" + ",\n".join(items) + "\n" + pad + "}"
    if isinstance(v, list):
        if not v:
            return "[]"
        items = [f"{pad2}{to_json(x, indent + 1)}" for x in v]
        return "[\n" + ",\n".join(items) + "\n" + pad + "]"
    return quote(v)


class Interp:
    def __init__(self):
        self.global_env = Env()
        self.out = []
        for name, fn in CORE.items():
            self.global_env.declare(name, Builtin(name, fn))
        for name, fn in BUILTINS.items():
            self.global_env.declare(name, Builtin(name, fn))

    def soq_print(self, *args):
        self.out.append(" ".join(show(a) for a in args))
        return None

    def call1(self, f, v):
        return self.call_value(f, [v], (0, 0))

    def run(self, program):
        result = None
        for stmt in program.a:
            result = self.exec_stmt(stmt, self.global_env)
        return result

    def exec_stmt(self, node, env):
        at = (node.line, node.col)
        if node.kind == "let":
            env.declare(node.a, self.eval(node.b, env))
            return None
        if node.kind == "def":
            fn = Function(node.a, node.b, node.c, env)
            env.declare(node.a, fn)
            return None
        if node.kind == "expr":
            return self.eval(node.a, env)
        if node.kind == "assign":
            return self.assign(node.a, self.eval(node.b, env), env)
        if node.kind == "for":
            return self.exec_for(node, env)
        raise SoqError(f"unknown statement '{node.kind}'", at[0], at[1])

    def exec_for(self, node, env):
        seq = self.eval(node.b, env)
        if not isinstance(seq, list):
            raise SoqError(f"cannot loop over a {type_name(seq)} value", node.line, node.col)
        for item in seq:
            inner = Env(env)
            inner.declare(node.a, item)
            self.exec_stmt(node.c, inner)
        return None

    def assign(self, target, value, env):
        at = (target.line, target.col)
        if target.kind == "name":
            env.assign(target.a, value, at)
            return None
        if target.kind == "field":
            obj = self.eval(target.a, env)
            if not isinstance(obj, dict):
                raise SoqError(f"cannot set field '{target.b}' on a {type_name(obj)} value",
                               at[0], at[1])
            obj[target.b] = value
            return None
        if target.kind == "index":
            obj = self.eval(target.a, env)
            idx = self.eval(target.b, env)
            if isinstance(obj, list) and isinstance(idx, int):
                if not -len(obj) <= idx < len(obj):
                    raise SoqError(f"index {idx} out of range", at[0], at[1])
                obj[idx if idx >= 0 else len(obj) + idx] = value
                return None
            if isinstance(obj, dict) and isinstance(idx, str):
                obj[idx] = value
                return None
            raise SoqError(f"cannot index a {type_name(obj)} with {type_name(idx)}",
                           at[0], at[1])
        raise SoqError("invalid assignment target", at[0], at[1])

    def eval(self, node, env):
        at = (node.line, node.col)
        kind = node.kind

        if kind in ("number", "string", "boolean", "null"):
            return node.a
        if kind == "name":
            return env.lookup(node.a, at)
        if kind == "list":
            return [self.eval(x, env) for x in node.a]
        if kind == "object":
            return {self.eval(k, env) if not isinstance(k, str) else k: self.eval(v, env)
                    for k, v in node.a}
        if kind == "bin":
            return self.binary(node.a, self.eval(node.b, env), self.eval(node.c, env), at)
        if kind == "neg":
            v = self.eval(node.a, env)
            if not isinstance(v, (int, float)) or isinstance(v, bool):
                raise SoqError(f"cannot negate a {type_name(v)} value", at[0], at[1])
            return -v
        if kind == "not":
            return not truthy(self.eval(node.a, env))
        if kind == "and":
            left = self.eval(node.a, env)
            return self.eval(node.b, env) if truthy(left) else left
        if kind == "or":
            left = self.eval(node.a, env)
            return left if truthy(left) else self.eval(node.b, env)
        if kind == "if":
            branch = node.b if truthy(self.eval(node.a, env)) else node.c
            return self.eval(branch, env) if branch else None
        if kind == "fn":
            return Function(None, node.a, node.b, env)
        if kind == "call":
            return self.call(node, env)
        if kind == "pipe":
            return self.pipe(node, env)
        if kind == "field":
            obj = self.eval(node.a, env)
            key = node.b
            if isinstance(obj, dict):
                if key in obj:
                    return obj[key]
                raise SoqError(f"object has no key '{key}'", at[0], at[1])
            raise SoqError(f"cannot read field '{key}' of a {type_name(obj)} value", at[0], at[1])
        if kind == "index":
            return self.index(self.eval(node.a, env), self.eval(node.b, env), at)

        raise SoqError(f"unknown expression '{kind}'", at[0], at[1])

    def index(self, obj, idx, at):
        if isinstance(obj, list):
            if not isinstance(idx, int) or isinstance(idx, bool):
                raise SoqError(f"cannot index an array with a {type_name(idx)} value", at[0], at[1])
            if -len(obj) <= idx < len(obj):
                return obj[idx if idx >= 0 else len(obj) + idx]
            raise SoqError(f"index {idx} out of range", at[0], at[1])
        if isinstance(obj, dict):
            if isinstance(idx, str) and idx in obj:
                return obj[idx]
            if isinstance(idx, str):
                raise SoqError(f"object has no key '{idx}'", at[0], at[1])
            raise SoqError(f"cannot index an object with a {type_name(idx)} value", at[0], at[1])
        if isinstance(obj, str) and isinstance(idx, int):
            if -len(obj) <= idx < len(obj):
                return obj[idx if idx >= 0 else len(obj) + idx]
            raise SoqError(f"index {idx} out of range", at[0], at[1])
        raise SoqError(f"cannot index a {type_name(obj)} value", at[0], at[1])

    def binary(self, op, left, right, at):
        if op == "EQ":
            return equal(left, right)
        if op == "NEQ":
            return not equal(left, right)

        if op in ("LT", "LE", "GT", "GE"):
            ok = (isinstance(left, (int, float)) and not isinstance(left, bool)
                  and isinstance(right, (int, float)) and not isinstance(right, bool))
            if not ok:
                if isinstance(left, str) and isinstance(right, str):
                    ok = True
                else:
                    raise SoqError(
                        f"cannot compare {type_name(left)} with {type_name(right)}",
                        at[0], at[1])
            if op == "LT":
                return left < right
            if op == "LE":
                return left <= right
            if op == "GT":
                return left > right
            return left >= right

        if op == "PLUS":
            if isinstance(left, str) and isinstance(right, str):
                return left + right
            if isinstance(left, list) and isinstance(right, list):
                return left + right
            return self.arith("add", left, right, at)

        if op == "MINUS":
            return self.arith("subtract", left, right, at)
        if op == "STAR":
            return self.arith("multiply", left, right, at)

        if op == "SLASH":
            if _is_num(left) and _is_num(right):
                if right == 0:
                    raise SoqError("division by zero", at[0], at[1])
                return left / right
            raise SoqError(f"cannot divide {type_name(left)} by {type_name(right)}",
                           at[0], at[1])

        if op == "PERCENT":
            if _is_num(left) and _is_num(right):
                if right == 0:
                    raise SoqError("modulo by zero", at[0], at[1])
                return left % right
            raise SoqError(f"cannot take {type_name(left)} modulo {type_name(right)}",
                           at[0], at[1])

        raise SoqError(f"unknown operator '{op}'", at[0], at[1])

    def arith(self, what, left, right, at):
        if _is_num(left) and _is_num(right):
            if what == "add":
                return left + right
            if what == "subtract":
                return left - right
            return left * right
        raise SoqError(f"cannot {what} {type_name(left)} and {type_name(right)}",
                       at[0], at[1])

    def pipe(self, node, env):
        value = self.eval(node.a, env)
        target = node.b
        if target.kind == "call":
            args = [self.eval(x, env) for x in target.b]
            return self.apply(target.a, args + [value], env, (node.line, node.col))
        if target.kind in ("name", "fn"):
            fn = self.eval(target, env)
            return self.apply(target, [value], env, (node.line, node.col))
        if target.kind == "field":
            return self.field_chain(value, target, env)
        if target.kind == "index":
            return self.index(value, self.eval(target.b, env), (node.line, node.col))
        raise SoqError("cannot pipe into this expression", node.line, node.col)

    def field_chain(self, value, target, env):
        if target.a.kind == "name":
            base = env.lookup(target.a.a, (target.line, target.col))
        else:
            base = self.eval(target.a, env)
        if not isinstance(base, dict):
            raise SoqError(f"cannot read field '{target.b}' of a {type_name(base)} value",
                           target.line, target.col)
        if target.b not in base:
            raise SoqError(f"object has no key '{target.b}'", target.line, target.col)
        return base[target.b]

    def apply(self, target, args, env, at):
        if target.kind == "name":
            fn = env.lookup(target.a, at)
        elif target.kind == "fn":
            fn = Function(None, target.a, target.b, env)
        else:
            fn = self.eval(target, env)
        return self.call_value(fn, args, at)

    def call(self, node, env):
        args = [self.eval(x, env) for x in node.b]
        return self.apply(node.a, args, env, (node.line, node.col))

    def call_value(self, fn, args, at):
        if isinstance(fn, Builtin):
            try:
                return fn.fn(self, *args)
            except SoqError:
                raise
            except TypeError as e:
                raise SoqError(f"{fn.name}: {e}", at[0], at[1])
            except (IndexError, ZeroDivisionError) as e:
                raise SoqError(f"{fn.name}: {type(e).__name__.lower()}", at[0], at[1])
        if isinstance(fn, Function):
            if len(args) != len(fn.params):
                raise SoqError(
                    f"{fn.name or 'function'} expects {len(fn.params)} argument(s), "
                    f"got {len(args)}", at[0], at[1])
            local = Env(fn.env)
            for name, value in zip(fn.params, args):
                local.declare(name, value)
            return self.eval(fn.body, local)
        raise SoqError(f"cannot call a {type_name(fn)} value", at[0], at[1])


class Builtin:
    __slots__ = ("name", "fn")

    def __init__(self, name, fn):
        self.name, self.fn = name, fn


CORE = {
    "print": Interp.soq_print,
    "println": Interp.soq_print,
    "to_json": lambda it, v: to_json(v),
    "type_of": lambda it, v: type_name(v),
}


BUILTINS = {}


def _b(name):
    def deco(fn):
        BUILTINS[name] = fn
        return fn
    return deco


def _num(name, v):
    if not isinstance(v, (int, float)) or isinstance(v, bool):
        raise SoqError(f"{name} expects a number, got {type_name(v)}")
    return v


def _str(name, v):
    if not isinstance(v, str):
        raise SoqError(f"{name} expects a string, got {type_name(v)}")
    return v


def _list(name, v):
    if not isinstance(v, list):
        raise SoqError(f"{name} expects an array, got {type_name(v)}")
    return v


def _obj(name, v):
    if not isinstance(v, dict):
        raise SoqError(f"{name} expects an object, got {type_name(v)}")
    return v


@_b("len")
def _len(it, v):
    if isinstance(v, (str, list, dict)):
        return len(v)
    raise SoqError(f"len does not work on {type_name(v)}")


@_b("keys")
def _keys(it, v):
    if isinstance(v, dict):
        return sorted(v.keys())
    if isinstance(v, list):
        return list(range(len(v)))
    raise SoqError(f"keys does not work on {type_name(v)}")


@_b("values")
def _values(it, v):
    if isinstance(v, dict):
        return [v[k] for k in sorted(v.keys())]
    if isinstance(v, list):
        return list(v)
    raise SoqError(f"values does not work on {type_name(v)}")


@_b("has")
def _has(it, v, key):
    _obj("has", v)
    return key in v


@_b("get")
def _get(it, v, key):
    if isinstance(v, dict):
        return v.get(key)
    if isinstance(v, list) and isinstance(key, int) and not isinstance(key, bool):
        return v[key] if -len(v) <= key < len(v) else None
    raise SoqError(f"get does not work on {type_name(v)} with {type_name(key)}")


@_b("set")
def _set(it, v, key, value):
    _obj("set", v)
    v[key] = value
    return v


@_b("map")
def _map(it, f, xs):
    return [it.call1(f, x) for x in _list("map", xs)]


@_b("select")
def _select(it, f, xs):
    return [x for x in _list("select", xs) if truthy(it.call1(f, x))]


@_b("filter")
def _filter(it, f, xs):
    return [x for x in _list("filter", xs) if truthy(it.call1(f, x))]


@_b("reject")
def _reject(it, f, xs):
    return [x for x in _list("reject", xs) if not truthy(it.call1(f, x))]


@_b("reduce")
def _reduce(it, f, init, xs):
    acc = init
    for x in _list("reduce", xs):
        acc = it.call_value(f, [acc, x], (0, 0))
    return acc


@_b("any")
def _any(it, f, xs):
    return any(truthy(it.call1(f, x)) for x in _list("any", xs))


@_b("all")
def _all(it, f, xs):
    return all(truthy(it.call1(f, x)) for x in _list("all", xs))


@_b("sort")
def _sort(it, xs):
    xs = _list("sort", xs)
    if all(isinstance(x, str) for x in xs):
        return sorted(xs)
    return sorted(xs, key=lambda v: _num("sort", v))


@_b("sort_by")
def _sort_by(it, f, xs):
    return sorted(_list("sort_by", xs), key=lambda v: it.call1(f, v))


@_b("group_by")
def _group_by(it, f, xs):
    out = {}
    for x in _list("group_by", xs):
        out.setdefault(show(it.call1(f, x)), []).append(x)
    return out


@_b("unique")
def _unique(it, xs):
    out = []
    for x in _list("unique", xs):
        if not any(equal(x, y) for y in out):
            out.append(x)
    return out


@_b("reverse")
def _reverse(it, xs):
    if isinstance(xs, str):
        return xs[::-1]
    return list(reversed(_list("reverse", xs)))


@_b("take")
def _take(it, n, xs):
    return _list("take", xs)[:max(0, _num("take", n))]


@_b("skip")
def _skip(it, n, xs):
    return _list("skip", xs)[max(0, _num("skip", n)):]


@_b("flatten")
def _flatten(it, xs):
    out = []
    for x in _list("flatten", xs):
        out.extend(x) if isinstance(x, list) else out.append(x)
    return out


@_b("range")
def _range(it, a, b=None, step=None):
    if b is None:
        a, b = 0, a
    _num("range", a)
    _num("range", b)
    if step is None:
        step = 1 if b >= a else -1
    elif _num("range", step) == 0:
        raise SoqError("range step cannot be zero")
    out, i = [], a
    while (step > 0 and i < b) or (step < 0 and i > b):
        out.append(i)
        i += step
    return out


@_b("min")
def _min(it, xs):
    xs = _list("min", xs)
    if not xs:
        return None
    return min(xs, key=_num) if any(isinstance(x, str) for x in xs) else min(xs)


@_b("max")
def _max(it, xs):
    xs = _list("max", xs)
    if not xs:
        return None
    return max(xs, key=_num) if any(isinstance(x, str) for x in xs) else max(xs)


@_b("sum")
def _sum(it, xs):
    return sum(_num("sum", x) for x in _list("sum", xs))


@_b("first")
def _first(it, xs):
    xs = _list("first", xs)
    return xs[0] if xs else None


@_b("last")
def _last(it, xs):
    xs = _list("last", xs)
    return xs[-1] if xs else None


@_b("to_entries")
def _to_entries(it, v):
    if isinstance(v, dict):
        return [{"key": k, "value": v[k]} for k in sorted(v.keys())]
    if isinstance(v, list):
        return [{"index": i, "value": x} for i, x in enumerate(v)]
    raise SoqError(f"to_entries does not work on {type_name(v)}")


@_b("from_entries")
def _from_entries(it, xs):
    out = {}
    for e in _list("from_entries", xs):
        _obj("from_entries", e)
        out[e.get("key", e.get("index"))] = e.get("value")
    return out


@_b("upper")
def _upper(it, s):
    return _str("upper", s).upper()


@_b("lower")
def _lower(it, s):
    return _str("lower", s).lower()


@_b("trim")
def _trim(it, s):
    return _str("trim", s).strip()


@_b("split")
def _split(it, sep, s):
    return _str("split", s).split(_str("split", sep))


@_b("join")
def _join(it, sep, xs):
    return _str("join", sep).join(show(x) for x in _list("join", xs))


@_b("replace")
def _replace(it, old, new, s):
    return _str("replace", s).replace(_str("replace", old), _str("replace", new))


@_b("starts_with")
def _starts_with(it, pre, s):
    return _str("starts_with", s).startswith(_str("starts_with", pre))


@_b("ends_with")
def _ends_with(it, suf, s):
    return _str("ends_with", s).endswith(_str("ends_with", suf))


@_b("contains")
def _contains(it, needle, hay):
    if isinstance(hay, str):
        return _str("contains", needle) in hay
    if isinstance(hay, list):
        return any(equal(needle, x) for x in hay)
    if isinstance(hay, dict):
        return needle in hay
    raise SoqError(f"contains does not work on {type_name(hay)}")


@_b("str")
def _to_str(it, v):
    return show(v)


@_b("int")
def _int(it, v):
    if isinstance(v, bool):
        raise SoqError("int does not work on a boolean")
    if isinstance(v, (int, float)):
        return int(v)
    if isinstance(v, str):
        try:
            return int(float(v))
        except ValueError:
            raise SoqError(f"cannot read a number from {quote(v)}")
    raise SoqError(f"int does not work on {type_name(v)}")


@_b("float")
def _float(it, v):
    if isinstance(v, bool):
        raise SoqError("float does not work on a boolean")
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        try:
            return float(v)
        except ValueError:
            raise SoqError(f"cannot read a number from {quote(v)}")
    raise SoqError(f"float does not work on {type_name(v)}")


@_b("is_null")
def _is_null(it, v):
    return v is None


@_b("not")
def _not(it, v):
    return not truthy(v)
