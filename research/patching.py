from __future__ import annotations

import ast
from copy import deepcopy

from research.types import AtomicEdit, EditConstraints, EditOp, Patch, SiteId
from research.parser import ParsedProgram, parse_program


class PatchApplicationError(ValueError):
    pass


SUPPORTED_PATCH_OPS = frozenset(
    {EditOp.REPLACE_CALL, EditOp.DELETE_CALL, EditOp.INSERT_CALL, EditOp.REPLACE_CONDITION}
)


def _api_name(call: ast.Call) -> str | None:
    parts: list[str] = []
    current: ast.AST = call.func
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if isinstance(current, ast.Name):
        parts.append(current.id)
        name = ".".join(reversed(parts))
        if name.startswith("apis.") and name.count(".") >= 2:
            return name
    return None


def _contains_api_call(node: ast.AST) -> bool:
    return any(isinstance(sub, ast.Call) and _api_name(sub) for sub in ast.walk(node))


def _flatten(statements: list[ast.stmt]) -> list[ast.stmt]:
    out: list[ast.stmt] = []
    for stmt in statements:
        out.append(stmt)
        if isinstance(stmt, (ast.If, ast.For)):
            out.extend(_flatten(stmt.body))
            out.extend(_flatten(stmt.orelse))
    return out


def _solution_function(tree: ast.Module) -> ast.FunctionDef:
    functions = [
        node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "solution"
    ]
    if len(functions) != 1:
        raise PatchApplicationError("expected exactly one solution function")
    return functions[0]


def make_edit_policy(
    program: ParsedProgram,
    *,
    max_cost: int = 3,
    policy_id: str = "controlled_edit_policy",
) -> EditConstraints:
    """Construct allowed edits from program structure and a cost limit.

    Simple API-call statements allow replacement, deletion, and insertion.
    An if-statement allows replacement of its condition. API calls nested
    inside control-flow statements do not make those statements editable calls.
    """

    allowed: dict[SiteId, frozenset[EditOp]] = {}
    for node in program.nodes:
        ops: set[EditOp] = set()
        if node.api_calls and node.kind not in {"If", "For"}:
            ops.update((EditOp.REPLACE_CALL, EditOp.DELETE_CALL, EditOp.INSERT_CALL))
        if node.kind == "If":
            ops.add(EditOp.REPLACE_CONDITION)
        if ops:
            allowed[SiteId(node.node_id)] = frozenset(ops)
    return EditConstraints(
        policy_id=policy_id,
        allowed_ops_by_site=allowed,
        max_cost=max_cost,
    )


def _parse_one_statement(source: str) -> ast.stmt:
    try:
        module = ast.parse(source)
    except SyntaxError as exc:
        raise PatchApplicationError("replacement is not valid Python") from exc
    if len(module.body) != 1:
        raise PatchApplicationError("replacement token must contain exactly one statement")
    return module.body[0]


def _parse_condition(source: str) -> ast.expr:
    try:
        parsed = ast.parse(source, mode="eval")
    except SyntaxError as exc:
        raise PatchApplicationError("condition token is not a Python expression") from exc
    return parsed.body


def apply_python_patch(
    source: str,
    patch: Patch,
    *,
    edit_constraints: EditConstraints | None = None,
) -> str:
    """Apply edits simultaneously at sites in the unmodified program.

    The edited source is parsed again using the same syntax restrictions.
    """

    if edit_constraints is not None and not edit_constraints.allows_patch(patch):
        raise PatchApplicationError("edit violates constraints")
    for edit in patch.edits:
        if edit.op not in SUPPORTED_PATCH_OPS:
            raise PatchApplicationError(f"unsupported patch operation: {edit.op.value}")
    by_site: dict[str, AtomicEdit] = {}
    for edit in patch.edits:
        site = str(edit.target_site)
        if site in by_site:
            raise PatchApplicationError("at most one atomic edit per site is supported")
        by_site[site] = edit

    tree = ast.parse(source)
    fn = _solution_function(tree)
    original_statements = _flatten(fn.body)
    site_by_identity = {
        id(stmt): f"n{index:04d}" for index, stmt in enumerate(original_statements, 1)
    }
    unknown = set(by_site) - set(site_by_identity.values())
    if unknown:
        raise PatchApplicationError(f"unknown stable site(s): {sorted(unknown)}")

    def rewrite_list(statements: list[ast.stmt]) -> list[ast.stmt]:
        rewritten: list[ast.stmt] = []
        for stmt in statements:
            site = site_by_identity.get(id(stmt))
            edit = by_site.get(site or "")
            current = deepcopy(stmt)
            if edit is not None:
                if edit.op is EditOp.DELETE_CALL:
                    if not _contains_api_call(stmt):
                        raise PatchApplicationError("DELETE_CALL target has no API call")
                    continue
                if edit.op is EditOp.INSERT_CALL:
                    if not edit.value_token:
                        raise PatchApplicationError("INSERT_CALL requires value_token")
                    inserted = _parse_one_statement(edit.value_token)
                    if not _contains_api_call(inserted):
                        raise PatchApplicationError("INSERT_CALL token must contain an API call")
                    if isinstance(inserted, (ast.If, ast.For, ast.FunctionDef, ast.ClassDef)):
                        raise PatchApplicationError(
                            "INSERT_CALL cannot inject control-flow or definitions"
                        )
                    rewritten.append(inserted)
                elif edit.op is EditOp.REPLACE_CALL:
                    if not _contains_api_call(stmt):
                        raise PatchApplicationError("REPLACE_CALL target has no API call")
                    if not edit.value_token:
                        raise PatchApplicationError("REPLACE_CALL requires value_token")
                    replacement = _parse_one_statement(edit.value_token)
                    if not _contains_api_call(replacement):
                        raise PatchApplicationError("REPLACE_CALL token must contain an API call")
                    if isinstance(replacement, (ast.If, ast.For, ast.FunctionDef, ast.ClassDef)):
                        raise PatchApplicationError(
                            "REPLACE_CALL cannot replace with control-flow or definitions"
                        )
                    current = replacement
                elif edit.op is EditOp.REPLACE_CONDITION:
                    if not isinstance(current, ast.If):
                        raise PatchApplicationError(
                            "condition replacement target must be an if statement"
                        )
                    if not edit.value_token:
                        raise PatchApplicationError("condition replacement requires value_token")
                    current.test = _parse_condition(edit.value_token)

            # Recurse using the original child identities when the statement
            # itself was not replaced. A replaced simple API statement has no
            # supported nested control flow.
            if edit is None or edit.op in (EditOp.INSERT_CALL, EditOp.REPLACE_CONDITION):
                if isinstance(current, (ast.If, ast.For)):
                    # Map deepcopy children back by position to original children.
                    original_body = stmt.body if isinstance(stmt, (ast.If, ast.For)) else []
                    original_else = stmt.orelse if isinstance(stmt, (ast.If, ast.For)) else []
                    # Rewrite originals, not copied nodes, then place fresh rewrites.
                    current.body = rewrite_list(original_body)
                    current.orelse = rewrite_list(original_else)
            rewritten.append(current)
        return rewritten

    fn.body = rewrite_list(fn.body)
    ast.fix_missing_locations(tree)
    output = ast.unparse(tree)
    # Check the resulting program against the same supported grammar.
    parse_program(output)
    return output + "\n"
