"""Finite lexical edit space and executable API for the paired study."""

from __future__ import annotations
from dataclasses import dataclass
from itertools import combinations
from typing import Any
from research.types import AtomicEdit, EditConstraints, EditOp, Patch, SiteId

OBSERVER_RESOURCES = {"P_vault": "vault", "P_audit": "audit", "P_mail": "mail"}
OBLIGATIONS = {"P_vault": 7, "P_audit": 7, "P_mail": 7}


def _patch_key(patch: Patch) -> tuple:
    return (
        patch.cost,
        len(patch.edits),
        tuple(
            (edit.op.value, str(edit.target_site), edit.value_token or "") for edit in patch.edits
        ),
    )


class ToyAPI:
    """Deterministic executable API with explicit state, aliases, and errors."""

    def __init__(self, initial: dict[str, Any]):
        self.state = dict(initial)
        self.calls = 0
        self.horizon = 64

    def _tick(self):
        self.calls += 1
        if self.calls > self.horizon:
            raise RuntimeError("fixed API execution horizon exceeded")

    def noop(self):
        self._tick()

    def goal(self, value):
        self._tick()
        self.state["goal"] = bool(value)

    def finish(self, value, preserve):
        self._tick()
        self.state["goal"] = bool(value)
        self.state["vault"] = 7 if preserve else 0

    def set_vault(self, value):
        self._tick()
        self.state["vault"] = value

    def set_audit(self, value):
        self._tick()
        self.state["audit"] = value

    def commit_alias(self, value):
        self._tick()
        self.state["vault"] = value["value"]

    def make_alias(self, value):
        self._tick()
        return {"value": value}

    def set_buffer(self, value):
        self._tick()
        self.state["buffer"] = value

    def flush(self):
        self._tick()
        self.state["vault"] = self.state["buffer"]

    def unknown(self, value, touch):
        self._tick()
        self.state["goal"] = bool(value)
        if touch:
            self.state["vault"] = 0


@dataclass(frozen=True)
class SiteMenu:
    site: str
    op: EditOp
    values: tuple[str | None, ...]


@dataclass(frozen=True)
class FiniteCase:
    case_id: str
    corpus_id: str
    source: str
    menus: tuple[SiteMenu, ...]
    allowed_operations: tuple[tuple[str, tuple[EditOp, ...]], ...]
    witness_sites: tuple[str, ...]
    policy_id: str
    initial_items: tuple[tuple[str, Any], ...] = (
        ("goal", False),
        ("vault", 7),
        ("audit", 7),
        ("mail", 7),
        ("buffer", 7),
    )
    max_patch_cost: int = 2
    description: str = ""

    @property
    def initial(self):
        return dict(self.initial_items)

    @property
    def edit_constraints(self):
        return EditConstraints(
            policy_id=self.policy_id,
            allowed_ops_by_site={
                SiteId(site): frozenset(ops) for site, ops in self.allowed_operations
            },
            max_cost=self.max_patch_cost,
        )


def _source(*body: str) -> str:
    return "def solution(apis):\n" + "\n".join("    " + line for line in body) + "\n"


def generate_candidates(case: FiniteCase) -> tuple[Patch, ...]:
    """Enumerate menu combinations up to cost B, with at most one edit per site."""
    atoms = [
        AtomicEdit(menu.op, SiteId(menu.site), 1, value)
        for menu in case.menus
        for value in menu.values
    ]
    patches = set()
    for count in range(1, case.max_patch_cost + 1):
        for edits in combinations(atoms, count):
            if len({e.target_site for e in edits}) == count:
                patches.add(
                    Patch(
                        tuple(
                            sorted(
                                edits,
                                key=lambda e: (str(e.target_site), e.op.value, e.value_token or ""),
                            )
                        )
                    )
                )
    return tuple(sorted(patches, key=_patch_key))


def patch_record(patch: Patch) -> dict:
    value = {
        "edits": [
            {
                "op": e.op.value,
                "site": str(e.target_site),
                "value_token": e.value_token,
                "cost": e.cost,
            }
            for e in patch.edits
        ],
        "cost": patch.cost,
        "size": len(patch.edits),
    }
    return value


def case_definition(case: FiniteCase) -> dict:
    return {
        "case_id": case.case_id,
        "coverage": case.corpus_id,
        "description": case.description,
        "W_bad": case.source,
        "initial_state": case.initial,
        "independent_A": {
            "source_id": case.edit_constraints.policy_id,
            "allowed_ops": {
                site: [op.value for op in ops] for site, ops in case.allowed_operations
            },
        },
        "independent_P": dict(OBLIGATIONS),
        "B": case.max_patch_cost,
        "failure_witness_sites": list(case.witness_sites),
        "grammar_menus": [
            {"site": m.site, "op": m.op.value, "values": list(m.values)} for m in case.menus
        ],
    }
