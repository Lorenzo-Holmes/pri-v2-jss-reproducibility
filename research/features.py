"""Public syntactic relevance, calculated without endpoint outcomes."""

import ast


def public_relevance(edits, witness_sites, api_specifications):
    touches_witness = any(edit["site"] in witness_sites for edit in edits)
    new_goal_writer = False
    target_literal = False
    for edit in edits:
        try:
            tree = ast.parse(edit["value_token"] or "")
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            specification = api_specifications.get(ast.unparse(node.func), {})
            if "goal" in specification.get("writes", {}):
                new_goal_writer = True
                target_literal |= any(
                    isinstance(arg, ast.Constant) and arg.value is True for arg in node.args
                )
    return 2 * int(target_literal) + int(new_goal_writer) + int(touches_witness)
