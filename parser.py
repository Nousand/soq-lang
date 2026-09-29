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
