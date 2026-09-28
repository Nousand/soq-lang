KEYWORDS = {
    "let", "def", "fn", "if", "then", "else",
    "for", "in", "do", "and", "or", "not",
    "true", "false", "null",
}

TWO_CHAR = {
    "|>": "PIPE", "==": "EQ", "!=": "NEQ", "<=": "LE", ">=": "GE",
}

ONE_CHAR = {
    "+": "PLUS", "-": "MINUS", "*": "STAR", "/": "SLASH", "%": "PERCENT",
    "=": "ASSIGN", "<": "LT", ">": "GT", ".": "DOT", ",": "COMMA",
    ":": "COLON", ";": "SEMI", "(": "LPAREN", ")": "RPAREN",
    "[": "LBRACK", "]": "RBRACK", "{": "LBRACE", "}": "RBRACE",
}

ENDS_STATEMENT = {
    "IDENT", "NUMBER", "STRING", "TRUE", "FALSE", "NULL",
    "RPAREN", "RBRACK", "RBRACE",
}

OPENERS = {"LPAREN", "LBRACK", "LBRACE"}
CLOSERS = {"RPAREN", "RBRACK", "RBRACE"}

ESCAPES = {"n": "\n", "t": "\t", "r": "\r", "0": "\0",
           "\\": "\\", '"': '"', "'": "'"}


class SoqError(Exception):
    def __init__(self, msg, line, col):
        self.msg, self.line, self.col = msg, line, col
        super().__init__(f"{line}:{col}: {msg}")


class Token:
    __slots__ = ("kind", "text", "value", "line", "col")

    def __init__(self, kind, text, value, line, col):
        self.kind, self.text, self.value = kind, text, value
        self.line, self.col = line, col

    def __repr__(self):
        return f"{self.kind}({self.text!r})@{self.line}:{self.col}"


def is_digit(c):
    return c != "" and "0" <= c <= "9"


def is_start(c):
    return c != "" and (c == "_" or c.isalpha() or ord(c) > 127)


def is_part(c):
    return is_start(c) or is_digit(c)


class Lexer:
    def __init__(self, src):
        self.src = src
        self.i = 0
        self.line, self.col = 1, 1
        self.depth = 0
        self.last = None

    def pos(self):
        return self.line, self.col

    def fail(self, msg, at=None):
        line, col = at or self.pos()
        raise SoqError(msg, line, col)

    def peek(self, n=0):
        j = self.i + n
        return self.src[j] if j < len(self.src) else ""

    # Returns current character and increments index
    # aswell as keeping track of the current location for debugging ease
    def bump(self):
        c = self.src[self.i]
        self.i += 1
        if c == "\n":
            self.line, self.col = self.line + 1, 1
        else:
            self.col += 1
        return c

    def emit(self, kind, text, value, at):
        self.last = kind
        return Token(kind, text, value, at[0], at[1])

    def skip_blanks(self):
        while self.i < len(self.src):
            c = self.peek()
            if c in " \t\r":
                self.bump()
            elif c == "#" or (c == "/" and self.peek(1) == "/"):
                while self.i < len(self.src) and self.peek() != "\n":
                    self.bump()
            else:
                return

    # Look past blank and comment lines for a leading '|>'.
    # A pipeline reads as one statement, so a line that continues one with
    # '|>' must not break it. Every other operator stays line-final.
    def next_line_starts_pipe(self):
        j = self.i
        while True:
            while j < len(self.src) and self.src[j] in " \t\r":
                j += 1
            if j < len(self.src) and self.src[j] == "\n":
                j += 1
                continue
            if self.src[j:j + 1] == "#" or self.src[j:j + 2] == "//":
                while j < len(self.src) and self.src[j] != "\n":
                    j += 1
                continue
            return self.src[j:j + 2] == "|>"

    def tokens(self):
        out = []
        while True:
            tok = self.next_token()
            out.append(tok)
            if tok.kind == "EOF":
                return out

    def next_token(self):
        self.skip_blanks()
        at = self.pos()
        c = self.peek()

        if self.i >= len(self.src):
            if self.last in ENDS_STATEMENT:
                return self.emit("NEWLINE", "\n", None, at)
            return self.emit("EOF", "", None, at)

        if c == "\n":
            self.bump()
            if self.depth > 0 or self.last not in ENDS_STATEMENT:
                return self.next_token()
            if self.next_line_starts_pipe():
                return self.next_token()
            return self.emit("NEWLINE", "\n", None, at)

        if c in "\"'":
            return self.lex_string(c, at)
        if is_digit(c):
            return self.lex_number(at)
        if is_start(c):
            return self.lex_ident(at)
        return self.lex_operator(at)

    # Supports integers, decimals and scientific notation
    def lex_number(self, at):
        start = self.i
        while is_digit(self.peek()):
            self.bump()
        if self.peek() == "." and is_digit(self.peek(1)):
            self.bump()
            while is_digit(self.peek()):
                self.bump()
        if self.peek() in "eE":
            off = 2 if self.peek(1) in "+-" else 1
            if is_digit(self.peek(off)):
                self.bump()
                if self.peek() in "+-":
                    self.bump()
                while is_digit(self.peek()):
                    self.bump()
        text = self.src[start:self.i]
        try:
            value = float(text)
        except ValueError:
            self.fail(f"bad number {text!r}", at)
        if value.is_integer() and "." not in text and "e" not in text.lower():
            value = int(text)
        return self.emit("NUMBER", text, value, at)

    def lex_string(self, quote, at):
        self.bump()
        buf = []
        while True:
            if self.i >= len(self.src) or self.peek() == "\n":
                self.fail("unterminated string", at)
            c = self.peek()
            if c == quote:
                self.bump()
                break
            if c != "\\":
                buf.append(self.bump())
                continue
            esc = self.pos()
            self.bump()
            if self.i >= len(self.src):
                self.fail("unterminated escape", esc)
            e = self.bump()
            if e in ESCAPES:
                buf.append(ESCAPES[e])
            else:
                self.fail(f"unknown escape \\{e}", esc)
        text = "".join(buf)
        return self.emit("STRING", text, text, at)

    def lex_ident(self, at):
        start = self.i
        while is_part(self.peek()):
            self.bump()
        text = self.src[start:self.i]
        if text not in KEYWORDS:
            return self.emit("IDENT", text, text, at)
        if text == "true":
            return self.emit("TRUE", text, True, at)
        if text == "false":
            return self.emit("FALSE", text, False, at)
        return self.emit(text.upper(), text, None, at)

    def lex_operator(self, at):
        two = self.src[self.i:self.i + 2]
        if two in TWO_CHAR:
            self.bump()
            self.bump()
            return self.emit(TWO_CHAR[two], two, None, at)
        c = self.peek()
        if c == "|":
            self.fail("did you mean '|>'?", at)
        if c not in ONE_CHAR:
            self.fail(f"unexpected character {c!r}", at)
        self.bump()
        kind = ONE_CHAR[c]
        if kind in OPENERS:
            self.depth += 1
        elif kind in CLOSERS and self.depth > 0:
            self.depth -= 1
        return self.emit(kind, c, None, at)


def tokenize(src):
    return Lexer(src).tokens()

if __name__ == "__main__":
    print("hello world")
