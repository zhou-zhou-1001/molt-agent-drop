"""Portable lexical checks for the Windows PowerShell 5.1 entry scripts."""

from pathlib import Path
import sys


FILES = ("bootstrap.ps1", "bootstrap_python.ps1", "molt.ps1", "run_drop_host.ps1", "run_molt_tunnel.ps1")
PAIRS = {"(": ")", "[": "]", "{": "}"}


def check(path: Path) -> list[str]:
    data = path.read_bytes()
    errors = []
    if any(byte > 0x7F for byte in data):
        errors.append("is not ASCII-only")
    text = data.decode("ascii", errors="replace")
    stack = []
    quote = None
    line = 1
    index = 0
    while index < len(text):
        char = text[index]
        if char == "\n":
            line += 1
        if quote:
            if char == "`":
                index += 2
                continue
            if char == quote:
                if index + 1 < len(text) and text[index + 1] == quote:
                    index += 2
                    continue
                quote = None
            index += 1
            continue
        if char == "#":
            newline = text.find("\n", index)
            index = len(text) if newline < 0 else newline
            continue
        if char in "'\"":
            quote = char
        elif char in PAIRS:
            stack.append((char, line))
        elif char in PAIRS.values():
            if not stack or PAIRS[stack[-1][0]] != char:
                errors.append(f"unexpected {char!r} on line {line}")
            else:
                stack.pop()
        index += 1
    if quote:
        errors.append("has an unterminated string")
    for opener, opener_line in stack:
        errors.append(f"unclosed {opener!r} from line {opener_line}")
    return errors


def main() -> int:
    root = Path(__file__).resolve().parent
    failed = False
    for name in FILES:
        errors = check(root / name)
        if errors:
            failed = True
            for error in errors:
                print(f"{name}: {error}", file=sys.stderr)
        else:
            print(f"{name}: ASCII and lexical structure OK")
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
