"""Verify every `file.py::symbol` reference in the docs resolves.

ARCHITECTURE.md points at specific code. Line numbers drifted on nearly every
refactor and went silently stale, so references name symbols instead and this
script checks them.

    ./.venv/bin/python tools/check_doc_refs.py
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ["ARCHITECTURE.md", "README.md"]
REF = re.compile(r"`([\w/]+\.py)::(\w+)`")


def symbols(path: Path) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            found.add(node.name)
        elif isinstance(node, ast.Assign):
            found.update(t.id for t in node.targets if isinstance(t, ast.Name))
    return found


def resolve(name: str) -> Path | None:
    roots = (ROOT, ROOT / "app", ROOT / "app" / "linkedin")
    return next((r / name for r in roots if (r / name).exists()), None)


def main() -> int:
    bad, checked = [], 0
    for doc in DOCS:
        for module, symbol in REF.findall((ROOT / doc).read_text()):
            checked += 1
            path = resolve(module)
            if path is None:
                bad.append(f"{doc}: no such module {module}")
            elif symbol not in symbols(path):
                bad.append(f"{doc}: {module} has no symbol {symbol}")

    for line in bad:
        print("STALE:", line)
    print(f"{checked} reference(s) checked, {len(bad)} stale")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
