"""Enforce descriptive Python API docs, concrete types, and unsuppressed diagnostics."""

from __future__ import annotations

import ast
import io
import re
import sys
import tokenize
from collections.abc import Iterator
from pathlib import Path
from typing import Final

_SECTIONS: Final = frozenset(
    {"Args", "Returns", "Yields", "Raises", "Attributes", "Examples", "Notes"}
)
_ENTRY: Final = re.compile(r"^ {4}(\*{0,2}[\w.]+):\s*(.+)$")
_WORD: Final = re.compile(r"\b\w+\b")
_PLACEHOLDER: Final = re.compile(r"\b(?:todo|tbd|fixme|placeholder|document me)\b", re.IGNORECASE)
_SUPPRESSION: Final = re.compile(
    r"^#\s*(?:noqa\b|(?:ruff|flake8):\s*noqa\b|"
    r"(?:type|pyright|ty|mypy|pyre|pytype):\s*ignore\b|nosec\b|pylint:\s*disable\b)",
    re.IGNORECASE,
)

type _Function = ast.FunctionDef | ast.AsyncFunctionDef
type _Declaration = ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef


def _describes(text: str, min_words: int = 2) -> bool:
    return len(_WORD.findall(text)) >= min_words and _PLACEHOLDER.search(text) is None


def _sections(docstring: str) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {}
    current: list[str] = []
    for line in docstring.splitlines():
        heading = line.removesuffix(":")
        if heading != line and heading in _SECTIONS:
            current = sections.setdefault(heading, [])
        else:
            current.append(line)
    return sections


def _entries(lines: list[str]) -> dict[str, str]:
    return {match[1]: match[2] for line in lines if (match := _ENTRY.match(line)) is not None}


def _body_nodes(function: _Function) -> Iterator[ast.AST]:
    pending: list[ast.AST] = list(function.body)
    while pending:
        node = pending.pop()
        if not isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            yield node
            pending.extend(ast.iter_child_nodes(node))


def _raised_names(nodes: list[ast.AST]) -> set[str]:
    names: set[str] = set()
    for node in nodes:
        if isinstance(node, ast.Raise):
            expression = node.exc.func if isinstance(node.exc, ast.Call) else node.exc
            if isinstance(expression, ast.Name):
                names.add(expression.id)
            elif isinstance(expression, ast.Attribute):
                names.add(expression.attr)
    return names


def _function_docs(node: _Function, docstring: str, label: str) -> Iterator[str]:
    sections = _sections(docstring)
    args = node.args
    parameters = {arg.arg for arg in (*args.posonlyargs, *args.args, *args.kwonlyargs)} - {
        "self",
        "cls",
    }
    if args.vararg is not None:
        parameters.add(f"*{args.vararg.arg}")
    if args.kwarg is not None:
        parameters.add(f"**{args.kwarg.arg}")

    entries = _entries(sections.get("Args", []))
    for name in sorted(parameters):
        if not _describes(entries.get(name, "")):
            yield f"{label}: Args needs a descriptive entry for {name}."
    for name in sorted(entries.keys() - parameters):
        yield f"{label}: Args documents an unknown parameter {name}."

    nodes = list(_body_nodes(node))
    result_section = None
    if any(isinstance(item, (ast.Yield, ast.YieldFrom)) for item in nodes):
        result_section = "Yields"
    elif any(isinstance(item, ast.Return) and item.value is not None for item in nodes):
        result_section = "Returns"
    if result_section is not None and not _describes(" ".join(sections.get(result_section, []))):
        yield f"{label}: missing a descriptive {result_section} section."

    raises = _entries(sections.get("Raises", []))
    for name in sorted(_raised_names(nodes)):
        if not _describes(raises.get(name, "")):
            yield f"{label}: Raises needs a descriptive entry for {name}."


def _declarations(body: list[ast.stmt]) -> Iterator[_Declaration]:
    for node in body:
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and (
            not node.name.startswith("_") or node.name == "__init__"
        ):
            yield node
            if isinstance(node, ast.ClassDef):
                yield from _declarations(node.body)


def _doc_errors(tree: ast.Module, filename: str) -> Iterator[str]:
    module_doc = ast.get_docstring(tree)
    if not filename.endswith(".pyi") and not _describes(module_doc or "", min_words=3):
        yield f"{filename}:1: missing a descriptive module docstring."
    for node in _declarations(tree.body):
        label = f"{filename}:{node.lineno}: {node.name}"
        docstring = ast.get_docstring(node) or ""
        summary = docstring.partition("\n")[0]
        if not _describes(summary, min_words=3) or (
            summary.lower().rstrip(".") == node.name.lower().replace("_", " ")
        ):
            yield f"{label}: missing a descriptive API summary."
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            yield from _function_docs(node, docstring, label)


def _type_expressions(tree: ast.Module, casts: set[str]) -> Iterator[ast.expr]:
    for node in ast.walk(tree):
        if isinstance(node, (ast.arg, ast.AnnAssign)):
            annotation = node.annotation
            if annotation is not None:
                yield annotation
        elif isinstance(node, ast.TypeAlias):
            yield node.value
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.returns is not None:
            yield node.returns
        elif (
            isinstance(node, ast.Call)
            and node.args
            and (
                (isinstance(node.func, ast.Name) and node.func.id in casts)
                or (isinstance(node.func, ast.Attribute) and node.func.attr == "cast")
            )
        ):
            yield node.args[0]


def _contains_generic_type(expression: ast.expr, generic_names: set[str]) -> bool:
    match expression:
        case ast.Constant(value=str(value)):
            try:
                return _contains_generic_type(ast.parse(value, mode="eval").body, generic_names)
            except SyntaxError:
                return False
        case ast.Subscript(value=ast.Name(id="Literal") | ast.Attribute(attr="Literal")):
            return False
        case ast.Name(id=name):
            return name in generic_names
        case ast.Attribute(attr=name):
            return name in {"Any", "object"}
        case _:
            return any(
                _contains_generic_type(child, generic_names)
                for child in ast.iter_child_nodes(expression)
                if isinstance(child, ast.expr)
            )


def _annotation_errors(tree: ast.Module, filename: str) -> Iterator[str]:
    generic_names = {"Any", "object"}
    casts = {"cast"}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module in {
            "typing",
            "typing_extensions",
            "builtins",
        }:
            for alias in node.names:
                if alias.name in {"Any", "object"}:
                    generic_names.add(alias.asname or alias.name)
                elif alias.name == "cast":
                    casts.add(alias.asname or alias.name)
    for annotation in _type_expressions(tree, casts):
        if _contains_generic_type(annotation, generic_names):
            yield f"{filename}:{annotation.lineno}: use a concrete type instead of Any or object."


def check_source(source: str, filename: str) -> list[str]:
    """Validate one complete Python source or stub.

    Args:
        source: Contents of the tracked Python file, decoded as UTF-8.
        filename: Workspace-relative name used for diagnostics.

    Returns:
        Documentation, typing, and suppression violations in diagnostic order.
    """
    try:
        tree = ast.parse(source, filename=filename)
    except SyntaxError as exc:
        return [f"{filename}:{exc.lineno}: Python syntax error: {exc.msg}"]
    suppressions = (
        f"{filename}:{token.start[0]}: inline checker suppression is forbidden."
        for token in tokenize.generate_tokens(io.StringIO(source).readline)
        if token.type == tokenize.COMMENT and _SUPPRESSION.match(token.string)
    )
    return [*_doc_errors(tree, filename), *_annotation_errors(tree, filename), *suppressions]


def main() -> int:
    """Check the submitted filenames and write any violations to standard error.

    Returns:
        Zero for a clean run, one for violations, or two for missing filenames.
    """
    if len(sys.argv) == 1:
        sys.stderr.write("Pass Python source paths to check.\n")
        return 2
    failures: list[str] = []
    for filename in sys.argv[1:]:
        try:
            source = Path(filename).read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            failures.append(f"{filename}: {exc}")
        else:
            failures.extend(check_source(source, filename))
    if failures:
        sys.stderr.write("\n".join(failures) + "\n")
    return int(bool(failures))


if __name__ == "__main__":
    sys.exit(main())
