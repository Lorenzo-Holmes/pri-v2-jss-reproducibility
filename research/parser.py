"""Parse controlled Python programs into statement and API-call sites.

Accepted syntax includes assignments, calls, conditionals, and for loops.
The node and call restrictions below define the supported subset. Statement
identifiers follow source order and are shared by edit menus and patching.
"""
from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import Iterable


class UnsupportedProgramSyntax(ValueError):
    pass


FORBIDDEN_NODE_TYPES = (
    ast.While,
    ast.AsyncFor,
    ast.AsyncWith,
    ast.Await,
    ast.Yield,
    ast.YieldFrom,
    ast.Try,
    ast.With,
    ast.ClassDef,
    ast.Global,
    ast.Nonlocal,
    ast.Delete,
)

FORBIDDEN_CALL_NAMES = {"eval", "exec", "compile", "__import__", "open", "input"}


@dataclass(frozen=True)
class ApiCallSite:
    call_id: str
    statement_id: str
    qualified_name: str
    line: int


@dataclass(frozen=True)
class ProgramNode:
    node_id: str
    kind: str
    line: int
    end_line: int
    source: str
    api_calls: tuple[ApiCallSite, ...] = ()


@dataclass(frozen=True)
class ParsedProgram:
    function_name: str
    nodes: tuple[ProgramNode, ...]
    api_calls: tuple[ApiCallSite, ...]

def _qualified_name(expr: ast.AST) -> str | None:
    parts: list[str] = []
    current = expr
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if isinstance(current, ast.Name):
        parts.append(current.id)
        return ".".join(reversed(parts))
    return None


def _api_name(call: ast.Call) -> str | None:
    name = _qualified_name(call.func)
    if not name:
        return None
    # The controlled API retains the apis.<namespace>.<operation> syntax.
    if name.startswith("apis.") and name.count(".") >= 2:
        return name
    return None


def _validate(tree: ast.AST) -> None:
    for node in ast.walk(tree):
        if isinstance(node, FORBIDDEN_NODE_TYPES):
            raise UnsupportedProgramSyntax(f"Unsupported {type(node).__name__} at line {getattr(node, 'lineno', '?')}")
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            raise UnsupportedProgramSyntax("Imports inside the solution function are not supported")
        if isinstance(node, ast.Call):
            name = _qualified_name(node.func)
            if name and name.split(".")[-1] in FORBIDDEN_CALL_NAMES:
                raise UnsupportedProgramSyntax(f"Unsupported dynamic/IO call {name}")
        if isinstance(node, ast.FunctionDef) and node.name != "solution":
            raise UnsupportedProgramSyntax(f"Helper function {node.name} is not supported")
        if isinstance(node, ast.Lambda):
            # Lambdas are only expressions. Recursive/self-referential lambdas are
            # not supported, but ordinary key functions are retained structurally.
            for sub in ast.walk(node.body):
                if isinstance(sub, FORBIDDEN_NODE_TYPES):
                    raise UnsupportedProgramSyntax("Unsupported syntax inside lambda")


def _statement_children(stmt: ast.stmt) -> Iterable[ast.stmt]:
    if isinstance(stmt, (ast.If, ast.For)):
        yield from stmt.body
        yield from stmt.orelse


def _flatten_statements(statements: list[ast.stmt]) -> list[ast.stmt]:
    out: list[ast.stmt] = []
    for stmt in statements:
        out.append(stmt)
        out.extend(_flatten_statements(list(_statement_children(stmt))))
    return out


def _extract_solution(source: str) -> ast.FunctionDef:
    tree = ast.parse(source)
    functions = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "solution"]
    if len(functions) != 1:
        raise UnsupportedProgramSyntax("Expected exactly one function named solution")
    fn = functions[0]
    # Only the solution body supplies editable statements.
    body_module = ast.Module(body=fn.body, type_ignores=[])
    _validate(body_module)
    return fn


def parse_program(source: str) -> ParsedProgram:
    fn = _extract_solution(source)
    statements = _flatten_statements(fn.body)
    nodes: list[ProgramNode] = []
    all_calls: list[ApiCallSite] = []
    for index, stmt in enumerate(statements, start=1):
        node_id = f"n{index:04d}"
        calls: list[ApiCallSite] = []
        call_index = 0
        for sub in ast.walk(stmt):
            if not isinstance(sub, ast.Call):
                continue
            qname = _api_name(sub)
            if not qname:
                continue
            call_index += 1
            call = ApiCallSite(
                call_id=f"{node_id}.c{call_index:02d}",
                statement_id=node_id,
                qualified_name=qname,
                line=getattr(sub, "lineno", getattr(stmt, "lineno", 0)),
            )
            calls.append(call)
            all_calls.append(call)
        nodes.append(
            ProgramNode(
                node_id=node_id,
                kind=type(stmt).__name__,
                line=getattr(stmt, "lineno", 0),
                end_line=getattr(stmt, "end_lineno", getattr(stmt, "lineno", 0)),
                source=ast.unparse(stmt),
                api_calls=tuple(calls),
            )
        )
    return ParsedProgram(
        function_name="solution",
        nodes=tuple(nodes),
        api_calls=tuple(all_calls),
    )
