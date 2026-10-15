"""Sixteen source templates crossed with six contexts, independent of outcomes."""

from research import candidates as candidate_model
from research.types import EditOp
from research.parser import parse_program
from research.patching import apply_python_patch, make_edit_policy

RECORDED_CORPUS_ID = "PRESERVATION_REPAIR_INVERSION_V1"
GOAL_CALLS = (
    "apis.toy.goal(False)",
    "apis.toy.goal(True)",
    "apis.toy.goal(not False)",
    "apis.toy.finish(False, True)",
    "apis.toy.finish(True, False)",
    "apis.toy.finish(True, True)",
)
SIMPLE_GOAL_CALLS = ("apis.toy.goal(False)", "apis.toy.goal(True)")
MECHANISMS = (
    "literal",
    "value_dependency",
    "resource_chain",
    "delete_overwrite",
    "branch_guard",
    "early_return",
    "control_bypass",
    "may_raise",
    "high_write_only",
    "two_edits",
    "unknown",
    "insertion",
    "multiple_observers",
    "alias",
    "unreachable_correction",
    "resource_correction",
)
CONTEXTS = ("independent", "irrelevant", "overwritten", "heap_alias", "unreachable", "exception")


def context_definition(name):
    return {
        "independent": {
            "body": ["apis.out.set(7)"],
            "edit_line": 0,
            "values": ("apis.out.set(0)", "apis.out.set(7)"),
        },
        "irrelevant": {
            "body": ["apis.calendar.set(7)", "apis.out.set(apis.calendar.get())"],
            "edit_line": 0,
            "values": ("apis.calendar.set(0)", "apis.calendar.set(7)"),
        },
        "overwritten": {
            "body": ["apis.toy.set_audit(0)", "apis.toy.set_audit(7)"],
            "edit_line": 0,
            "values": ("apis.toy.set_audit(11)", "apis.toy.set_audit(0)"),
        },
        "heap_alias": {
            "body": [
                "parcel = apis.values.box(7)",
                "other = parcel",
                "apis.values.mutate(other, 7)",
                "apis.mail.set(apis.values.readbox(parcel))",
            ],
            "edit_line": 2,
            "values": ("apis.values.mutate(other, 0)", "apis.values.mutate(other, 7)"),
        },
        "unreachable": {
            "body": ["apis.toy.set_audit(7)", "if False:", "    apis.toy.set_vault(0)"],
            "edit_line": 0,
            "values": ("apis.toy.set_audit(0)", "apis.toy.set_audit(7)"),
        },
        "exception": {
            "body": ["apis.check.verify(True)", "apis.mail.set(7)"],
            "edit_line": 0,
            "values": ("apis.check.verify(False)", "apis.check.verify(True)"),
        },
    }[name]


def template_definition(name):
    if name == "literal":
        return {
            "body": ["apis.toy.goal(False)"],
            "menus": [{"line": 0, "operation": EditOp.REPLACE_CALL, "values": GOAL_CALLS}],
            "witness_lines": [0],
            "max_edit_cost": 1,
        }
    if name == "value_dependency":
        return {
            "body": ["permit = apis.values.pick(False)", "apis.toy.goal(permit)"],
            "menus": [
                {
                    "line": 0,
                    "operation": EditOp.REPLACE_CALL,
                    "values": (
                        "permit = apis.values.pick(False)",
                        "permit = apis.values.pick(True)",
                    ),
                },
                {"line": 1, "operation": EditOp.REPLACE_CALL, "values": GOAL_CALLS},
            ],
            "witness_lines": [1],
            "max_edit_cost": 1,
        }
    if name == "resource_chain":
        return {
            "body": [
                "apis.out.set(0)",
                "apis.calendar.set(apis.out.get())",
                "apis.toy.goal(apis.calendar.get() == 7)",
            ],
            "menus": [
                {
                    "line": 0,
                    "operation": EditOp.REPLACE_CALL,
                    "values": ("apis.out.set(0)", "apis.out.set(7)"),
                },
                {"line": 2, "operation": EditOp.REPLACE_CALL, "values": GOAL_CALLS},
            ],
            "witness_lines": [2],
            "max_edit_cost": 1,
        }
    if name == "delete_overwrite":
        return {
            "body": ["apis.toy.goal(True)", "apis.toy.goal(False)"],
            "menus": [
                {"line": 1, "operation": EditOp.DELETE_CALL, "values": (None,)},
                {"line": 1, "operation": EditOp.REPLACE_CALL, "values": GOAL_CALLS},
            ],
            "witness_lines": [1],
            "max_edit_cost": 1,
        }
    if name == "branch_guard":
        return {
            "body": ["if True:", "    apis.toy.goal(False)", "else:", "    apis.toy.goal(True)"],
            "menus": [
                {"line": 0, "operation": EditOp.REPLACE_CONDITION, "values": ("False", "True")},
                {"line": 1, "operation": EditOp.REPLACE_CALL, "values": GOAL_CALLS},
            ],
            "witness_lines": [1],
            "max_edit_cost": 1,
        }
    if name == "early_return":
        return {
            "body": [
                "apis.toy.goal(False)",
                "if True:",
                "    return",
                "apis.toy.set_vault(7)",
                "apis.toy.goal(False)",
            ],
            "menus": [
                {"line": 0, "operation": EditOp.REPLACE_CALL, "values": GOAL_CALLS},
                {"line": 1, "operation": EditOp.REPLACE_CONDITION, "values": ("False", "True")},
            ],
            "witness_lines": [0, 4],
            "max_edit_cost": 2,
        }
    if name == "control_bypass":
        return {
            "body": [
                "apis.toy.goal(True)",
                "if True:",
                "    apis.toy.goal(False)",
                "else:",
                "    apis.toy.noop()",
            ],
            "menus": [
                {"line": 1, "operation": EditOp.REPLACE_CONDITION, "values": ("False", "True")},
                {"line": 2, "operation": EditOp.REPLACE_CALL, "values": GOAL_CALLS},
            ],
            "witness_lines": [2],
            "max_edit_cost": 1,
        }
    if name == "may_raise":
        return {
            "body": ["apis.toy.goal(True)", "apis.check.verify(False)", "apis.toy.goal(True)"],
            "menus": [
                {
                    "line": 1,
                    "operation": EditOp.REPLACE_CALL,
                    "values": (
                        "apis.check.verify(False)",
                        "apis.check.verify(True)",
                        "apis.toy.noop()",
                        "apis.toy.finish(True, False)",
                        "apis.toy.finish(True, True)",
                    ),
                }
            ],
            "witness_lines": [1],
            "max_edit_cost": 1,
        }
    if name == "high_write_only":
        return {
            "body": ["if apis.calendar.get() == 7:", "    apis.toy.goal(False)"],
            "menus": [
                {
                    "line": 1,
                    "operation": EditOp.REPLACE_CALL,
                    "values": (
                        "apis.toy.goal(False)",
                        "apis.toy.finish(False, True)",
                        "apis.toy.finish(True, False)",
                        "apis.toy.finish(True, True)",
                    ),
                }
            ],
            "witness_lines": [1],
            "max_edit_cost": 1,
        }
    if name == "two_edits":
        return {
            "body": ["apis.toy.goal(False)", "if True:", "    apis.toy.goal(False)"],
            "menus": [
                {"line": 0, "operation": EditOp.REPLACE_CALL, "values": GOAL_CALLS},
                {"line": 1, "operation": EditOp.REPLACE_CONDITION, "values": ("False", "True")},
            ],
            "witness_lines": [0, 2],
            "max_edit_cost": 2,
        }
    if name == "unknown":
        return {
            "body": ["apis.toy.unknown(False, False)"],
            "menus": [
                {
                    "line": 0,
                    "operation": EditOp.REPLACE_CALL,
                    "values": (
                        "apis.toy.unknown(False, False)",
                        "apis.toy.unknown(True, False)",
                        "apis.toy.unknown(True, True)",
                        "apis.toy.finish(True, True)",
                    ),
                }
            ],
            "witness_lines": [0],
            "max_edit_cost": 1,
        }
    if name == "insertion":
        return {
            "body": ["apis.toy.goal(False)", "apis.toy.noop()"],
            "menus": [
                {"line": 0, "operation": EditOp.REPLACE_CALL, "values": SIMPLE_GOAL_CALLS},
                {"line": 1, "operation": EditOp.INSERT_CALL, "values": GOAL_CALLS},
            ],
            "witness_lines": [0],
            "max_edit_cost": 1,
        }
    if name == "multiple_observers":
        return {
            "body": ["apis.toy.goal(False)", "apis.mail.set(7)", "apis.toy.set_audit(7)"],
            "menus": [
                {"line": 0, "operation": EditOp.REPLACE_CALL, "values": GOAL_CALLS},
                {
                    "line": 1,
                    "operation": EditOp.REPLACE_CALL,
                    "values": ("apis.mail.set(0)", "apis.mail.set(7)"),
                },
                {
                    "line": 2,
                    "operation": EditOp.REPLACE_CALL,
                    "values": ("apis.toy.set_audit(0)", "apis.toy.set_audit(7)"),
                },
            ],
            "witness_lines": [0],
            "max_edit_cost": 2,
        }
    if name == "alias":
        return {
            "body": [
                "parcel = apis.toy.make_alias(7)",
                "if False:",
                "    apis.toy.commit_alias(parcel)",
                "apis.toy.goal(False)",
            ],
            "menus": [
                {"line": 1, "operation": EditOp.REPLACE_CONDITION, "values": ("False", "True")},
                {"line": 3, "operation": EditOp.REPLACE_CALL, "values": SIMPLE_GOAL_CALLS},
                {
                    "line": 0,
                    "operation": EditOp.REPLACE_CALL,
                    "values": (
                        "parcel = apis.toy.make_alias(0)",
                        "parcel = apis.toy.make_alias(7)",
                    ),
                },
            ],
            "witness_lines": [3],
            "max_edit_cost": 2,
        }
    if name == "unreachable_correction":
        return {
            "body": ["apis.toy.goal(False)", "if False:", "    apis.toy.finish(True, True)"],
            "menus": [
                {"line": 0, "operation": EditOp.REPLACE_CALL, "values": SIMPLE_GOAL_CALLS},
                {"line": 1, "operation": EditOp.REPLACE_CONDITION, "values": ("False", "True")},
            ],
            "witness_lines": [0],
            "max_edit_cost": 2,
        }
    if name == "resource_correction":
        return {
            "body": [
                "apis.toy.goal(False)",
                "apis.out.set(7)",
                "if False:",
                "    apis.toy.set_buffer(apis.out.get())",
                "    apis.toy.flush()",
            ],
            "menus": [
                {"line": 0, "operation": EditOp.REPLACE_CALL, "values": SIMPLE_GOAL_CALLS},
                {"line": 2, "operation": EditOp.REPLACE_CONDITION, "values": ("False", "True")},
                {
                    "line": 1,
                    "operation": EditOp.REPLACE_CALL,
                    "values": ("apis.out.set(0)", "apis.out.set(7)"),
                },
            ],
            "witness_lines": [0],
            "max_edit_cost": 2,
        }
    raise ValueError(name)


def build_family(template_index, context_index):
    template_name = MECHANISMS[template_index]
    context_name = CONTEXTS[context_index]
    template = template_definition(template_name)
    context = context_definition(context_name)
    body = template["body"]
    menus = template["menus"] + [
        {
            "line": len(body) + context["edit_line"],
            "operation": EditOp.REPLACE_CALL,
            "values": context["values"],
        }
    ]
    source = candidate_model._source(*(body + context["body"]))
    compile(source, "<static>", "exec")
    parsed = parse_program(source)
    sites_by_body_line = {node.line - 2: node.node_id for node in parsed.nodes}
    max_edit_cost = template["max_edit_cost"]
    edit_constraints = make_edit_policy(parsed, max_cost=max_edit_cost)
    allowed_operations = tuple(
        (str(site), tuple(sorted(operations, key=lambda operation: operation.value)))
        for site, operations in sorted(edit_constraints.allowed_ops_by_site.items())
    )
    family_id = f"PRI_{template_index:02d}_{context_index}_{template_name}_{context_name}"
    resolved_menus = tuple(
        candidate_model.SiteMenu(
            site=sites_by_body_line[menu["line"]],
            op=menu["operation"],
            values=menu["values"],
        )
        for menu in menus
    )
    initial_state = {
        "goal": False,
        "vault": 7,
        "audit": 7,
        "mail": 7,
        "buffer": 7,
        "out": 7,
        "calendar": 7,
    }
    original_case = candidate_model.FiniteCase(
        case_id=family_id,
        corpus_id=RECORDED_CORPUS_ID,
        source=source,
        menus=resolved_menus,
        allowed_operations=allowed_operations,
        witness_sites=tuple(sites_by_body_line[line] for line in template["witness_lines"]),
        policy_id=f"independent_toy_policy/{family_id}/v1",
        initial_items=tuple(initial_state.items()),
        max_patch_cost=max_edit_cost,
        description="Fixed grammar crossing; vault-only paired initial intervention.",
    )
    candidates = []
    for patch in candidate_model.generate_candidates(original_case):
        patched_source = apply_python_patch(
            source, patch, edit_constraints=original_case.edit_constraints
        )
        compile(patched_source, "<static-candidate>", "exec")
        candidates.append({**candidate_model.patch_record(patch), "patched_source": patched_source})
    states = []
    for preservation_valid in (True, False):
        state = dict(initial_state)
        state["vault"] = 7 if preservation_valid else 0
        paired_case = candidate_model.FiniteCase(
            case_id=family_id,
            corpus_id=RECORDED_CORPUS_ID,
            source=source,
            menus=resolved_menus,
            allowed_operations=allowed_operations,
            witness_sites=original_case.witness_sites,
            policy_id=original_case.policy_id,
            initial_items=tuple(state.items()),
            max_patch_cost=max_edit_cost,
            description=original_case.description,
        )
        definition = candidate_model.case_definition(paired_case)
        assert paired_case.edit_constraints == original_case.edit_constraints
        assert [
            candidate_model.patch_record(patch)
            for patch in candidate_model.generate_candidates(paired_case)
        ] == [
            {key: value for key, value in candidate.items() if key != "patched_source"}
            for candidate in candidates
        ]
        states.append(
            {
                "state_id": family_id + ("_VALID" if preservation_valid else "_INVALID"),
                "condition": "STATE_VALID" if preservation_valid else "STATE_INVALID",
                "definition": definition,
            }
        )
    return {
        "family_id": family_id,
        "mechanism": template_name,
        "context": context_name,
        "states": states,
        "candidates": candidates,
    }


def generate():
    families = [
        build_family(template_index, context_index)
        for template_index in range(len(MECHANISMS))
        for context_index in range(len(CONTEXTS))
    ]
    identifiers = {}
    for family in families:
        for candidate in family["candidates"]:
            descriptor = (
                candidate["cost"],
                candidate["size"],
                tuple(
                    (edit["op"], edit["site"], edit["value_token"], edit["cost"])
                    for edit in candidate["edits"]
                ),
            )
            if descriptor not in identifiers:
                identifiers[descriptor] = f"C{len(identifiers) + 1:04d}"
            candidate["candidate_id"] = identifiers[descriptor]
    return families


def case_from_record(row):
    definition = row["definition"]
    return candidate_model.FiniteCase(
        case_id=definition["case_id"],
        corpus_id=definition["coverage"],
        source=definition["W_bad"],
        menus=tuple(
            candidate_model.SiteMenu(
                site=menu["site"], op=EditOp(menu["op"]), values=tuple(menu["values"])
            )
            for menu in definition["grammar_menus"]
        ),
        allowed_operations=tuple(
            (site, tuple(EditOp(operation) for operation in operations))
            for site, operations in definition["independent_A"]["allowed_ops"].items()
        ),
        witness_sites=tuple(definition["failure_witness_sites"]),
        policy_id=definition["independent_A"]["source_id"],
        initial_items=tuple(definition["initial_state"].items()),
        max_patch_cost=definition["B"],
        description=definition["description"],
    )
