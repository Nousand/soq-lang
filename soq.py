import json
import sys

from interp import Builtin, Interp
from lexer import SoqError, tokenize
from parser import parse

USAGE = """
soq - a small data-oriented scripting language

  soq run FILE [args]   run a program
  soq -e CODE [args]    run a one-liner
  soq json FILE [CODE]  load JSON, run CODE on it (default: print input)
  soq tokens FILE       print the token stream
"""


def run_source(src, args):
    interp = Interp()
    interp.global_env.declare("args", list(args))
    interp.global_env.declare("load_json", Builtin("load_json", _load))
    interp.global_env.declare("dump_json", Builtin("dump_json", _dump))
    interp.run(parse(src))
    return interp


def _load(it, path):
    with open(path) as fh:
        return json.load(fh)


def _dump(it, value, path=None):
    if path is None:
        json.dump(value, sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        with open(path, "w") as fh:
            json.dump(value, fh, indent=2)


def read(path):
    if path == "-":
        return sys.stdin.read()
    with open(path) as fh:
        return fh.read()


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(USAGE.strip())
        return 0

    cmd = argv[0]
    try:
        if cmd == "tokens":
            for t in tokenize(read(argv[1])):
                print(f"{t.kind:<8} {t.line}:{t.col:<4} {t.text!r}")
            return 0

        if cmd == "run":
            interp = run_source(read(argv[1]), argv[2:])
            for line in interp.out:
                print(line)
            return 0

        if cmd == "-e":
            interp = run_source(argv[1], argv[2:])
            for line in interp.out:
                print(line)
            return 0

        if cmd == "json":
            data = json.loads(read(argv[1]))
            interp = Interp()
            interp.global_env.declare("args", [])
            interp.global_env.declare("input", data)
            interp.run(parse(argv[2] if len(argv) > 2 else "print(input)"))
            for line in interp.out:
                print(line)
            return 0
    except SoqError as e:
        print(f"{cmd}: {e}", file=sys.stderr)
        return 1
    except RecursionError:
        print(f"{cmd}: call stack too deep (is a function recursing forever?)",
              file=sys.stderr)
        return 1
    except FileNotFoundError as e:
        print(f"{cmd}: {e.filename}: no such file", file=sys.stderr)
        return 1
    except json.JSONDecodeError as e:
        print(f"{cmd}: invalid JSON: {e}", file=sys.stderr)
        return 1

    print(f"unknown command {cmd!r}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    if not sys.argv[1:]:
        print(USAGE.strip())
    else:
        sys.exit(main(sys.argv[1:]))
