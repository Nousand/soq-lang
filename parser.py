from lexer import SoqError, tokenize

LEFT_BINDING = {
    "PIPE": 10,
    "OR": 20, "AND": 30,
    "EQ": 40, "NEQ": 40, "LT": 40, "LE": 40, "GT": 40, "GE": 40,
    "PLUS": 50, "MINUS": 50,
    "STAR": 60, "SLASH": 60, "PERCENT": 60,
}

NOT_BINDING = 35
UNARY_BINDING = 65
CALL_BINDING = 70


class Node:
    pass
    __slots__ = ("kind", "line", "col", "a", "b", "c", "d")

    def __init__(self, kind, at, a=None, b=None, c=None, d=None):
        self.kind = kind
        self.line, self.col = at[0], at[1]
        self.a, self.b, self.c, self.d = a, b, c, d

    def __repr__(self):
        return f"({self.kind} {self.a} {self.b} {self.c} {self.d})"


class Parser:
    def __init__(self, src):
        self.toks = tokenize(src)
        self.p = 0

    @property
    def tok(self):
        return self.toks[self.p]

    def at(self, *kinds):
        return self.tok.kind in kinds

    def fail(self, msg):
        raise SoqError(msg, self.tok.line, self.tok.col)

    def next(self):
        tok = self.toks[self.p]
        if tok.kind != "EOF":
            self.p += 1
        return tok

    def eat(self, kind, what=None):
        if self.tok.kind != kind:
            self.fail(f"expected {what or kind}, found {self.tok.kind}")
        return self.next()

    def accept(self, kind):
        if self.tok.kind == kind:
            return self.next()
        return None

    def skip_newlines(self):
        while self.at("NEWLINE"):
            self.next()

    def skip_terminators(self):
        while self.at("NEWLINE", "SEMI"):
            self.next()

    # ---------- statements ----------

    def parse_program(self):
        stmts = []
        self.skip_terminators()
        while not self.at("EOF"):
            stmts.append(self.parse_statement())
            if not self.at("NEWLINE", "SEMI", "EOF"):
                self.fail(f"expected end of statement, found {self.tok.kind}")
            self.skip_terminators()
        return Node("program", (1, 1), a=stmts)

    def parse_statement(self):
        at = (self.tok.line, self.tok.col)
        kind = self.tok.kind

        if kind == "LET":
            self.next()
            name = self.eat("IDENT", "a name").text
            self.eat("ASSIGN", "'='")
            return Node("let", at, a=name, b=self.parse_expr())

        if kind == "DEF":
            self.next()
            name = self.eat("IDENT", "a name").text
            params = self.parse_params()
            self.eat("ASSIGN", "'='")
            return Node("def", at, a=name, b=params, c=self.parse_expr())

        if kind == "FOR":
            self.next()
            name = self.eat("IDENT", "a loop variable").text
            self.eat("IN", "'in'")
            seq = self.parse_expr()
            self.eat("DO", "'do'")
            body = self.parse_statement()
            return Node("for", at, a=name, b=seq, c=body)

        expr = self.parse_expr()
        if self.at("ASSIGN"):
            self.next()
            value = self.parse_expr()
            return Node("assign", (expr.line, expr.col), a=expr, b=value)
        return Node("expr", at, a=expr)

    def parse_params(self):
        self.eat("LPAREN", "'('")
        params = []
        if not self.at("RPAREN"):
            params.append(self.eat("IDENT", "a parameter name").text)
            while self.accept("COMMA"):
                params.append(self.eat("IDENT", "a parameter name").text)
        self.eat("RPAREN", "')'")
        return params

    # ---------- expressions ----------

    def parse_expr(self, rbp=0):
        left = self.parse_nud()
        while True:
            kind = self.tok.kind
            lbp = LEFT_BINDING.get(kind, -1)
            if kind in ("LPAREN", "LBRACK", "DOT"):
                lbp = CALL_BINDING
            if lbp <= rbp:
                return left
            if kind == "PIPE":
                left = self.parse_pipe(left)
            elif kind in ("LPAREN", "LBRACK", "DOT"):
                left = self.parse_postfix(left)
            else:
                left = self.parse_led(left, kind)

    def parse_nud(self):
        tok = self.tok
        at = (tok.line, tok.col)
        kind = tok.kind

        if kind in ("NUMBER", "STRING"):
            self.next()
            return Node(kind.lower(), at, a=tok.value)

        if kind in ("TRUE", "FALSE"):
            self.next()
            return Node("boolean", at, a=tok.value)

        if kind == "NULL":
            self.next()
            return Node("null", at)

        if kind == "IDENT":
            self.next()
            return Node("name", at, a=tok.text)

        if kind == "LPAREN":
            self.next()
            self.skip_newlines()
            expr = self.parse_expr()
            self.skip_newlines()
            self.eat("RPAREN", "')'")
            return expr

        if kind == "LBRACK":
            return self.parse_list(at)

        if kind == "LBRACE":
            return self.parse_object(at)

        if kind == "IF":
            return self.parse_if(at)

        if kind == "FN":
            self.next()
            params = self.parse_params()
            self.eat("ASSIGN", "'='")
            return Node("fn", at, a=params, b=self.parse_expr())

        if kind == "MINUS":
            self.next()
            return Node("neg", at, a=self.parse_expr(UNARY_BINDING))

        if kind == "NOT":
            self.next()
            return Node("not", at, a=self.parse_expr(NOT_BINDING))

        self.fail(f"expected an expression, found {kind}")

    def parse_led(self, left, kind):
        op = self.next()
        at = (op.line, op.col)
        if kind == "OR":
            return Node("or", at, a=left, b=self.parse_expr(LEFT_BINDING[kind]))
        if kind == "AND":
            return Node("and", at, a=left, b=self.parse_expr(LEFT_BINDING[kind]))
        right = self.parse_expr(LEFT_BINDING[kind])
        return Node("bin", at, a=kind, b=left, c=right)

    def parse_pipe(self, left):
        self.next()
        self.skip_newlines()
        if not self.at("IDENT", "LPAREN"):
            self.fail(f"expected a function or field after '|>', found {self.tok.kind}")
        target = self.parse_nud()
        while self.at("LPAREN", "LBRACK", "DOT"):
            target = self.parse_postfix(target)
        return Node("pipe", (left.line, left.col), a=left, b=target)

    def parse_postfix(self, target):
        kind = self.tok.kind
        at = (self.tok.line, self.tok.col)
        self.next()
        if kind == "DOT":
            return Node("field", at, a=target, b=self.eat("IDENT", "a field name").text)
        if kind == "LBRACK":
            self.skip_newlines()
            index = self.parse_expr()
            self.skip_newlines()
            self.eat("RBRACK", "']'")
            return Node("index", at, a=target, b=index)
        self.skip_newlines()
        args = []
        if not self.at("RPAREN"):
            args.append(self.parse_expr())
            while self.accept("COMMA"):
                self.skip_newlines()
                args.append(self.parse_expr())
        self.skip_newlines()
        self.eat("RPAREN", "')'")
        return Node("call", at, a=target, b=args)

    def parse_list(self, at):
        self.next()
        items = []
        self.skip_newlines()
        if not self.at("RBRACK"):
            items.append(self.parse_expr())
            while self.accept("COMMA"):
                self.skip_newlines()
                items.append(self.parse_expr())
            self.skip_newlines()
        self.eat("RBRACK", "']'")
        return Node("list", at, a=items)

    def parse_object(self, at):
        self.next()
        entries = []
        self.skip_newlines()
        if not self.at("RBRACE"):
            entries.append(self.parse_entry())
            while self.accept("COMMA"):
                self.skip_newlines()
                entries.append(self.parse_entry())
            self.skip_newlines()
        self.eat("RBRACE", "'}'")
        return Node("object", at, a=entries)

    def parse_entry(self):
        tok = self.tok
        if tok.kind not in ("IDENT", "STRING"):
            self.fail(f"expected a key, found {tok.kind}")
        self.next()
        self.eat("COLON", "':'")
        return (tok.value, self.parse_expr())

    def parse_if(self, at):
        self.next()
        cond = self.parse_expr()
        self.eat("THEN", "'then'")
        then = self.parse_expr()
        alt = None
        if self.at("ELSE"):
            self.next()
            alt = self.parse_expr()
        return Node("if", at, a=cond, b=then, c=alt)


def parse(src):
    return Parser(src).parse_program()
