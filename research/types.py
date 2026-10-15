"""Edit operations, patches, and restrictions on allowed edits."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Callable, Mapping, NewType


SiteId = NewType("SiteId", str)


class EditOp(str, Enum):
    INSERT_CALL = "INSERT_CALL"
    DELETE_CALL = "DELETE_CALL"
    REPLACE_CALL = "REPLACE_CALL"
    REPLACE_CONDITION = "REPLACE_GUARD"


@dataclass(frozen=True, order=True)
class AtomicEdit:
    """One typed edit applied to a stable site in the unmodified program."""

    op: EditOp
    target_site: SiteId
    cost: int = 1
    value_token: str | None = None

    def __post_init__(self) -> None:
        if not str(self.target_site):
            raise ValueError("target_site must be non-empty")
        if self.cost <= 0:
            raise ValueError("edit cost must be positive")


@dataclass(frozen=True)
class Patch:
    """A finite typed patch; order is part of patch identity."""

    edits: tuple[AtomicEdit, ...]

    def __post_init__(self) -> None:
        if not self.edits:
            raise ValueError("patch must contain at least one edit")

    @property
    def cost(self) -> int:
        return sum(edit.cost for edit in self.edits)


CombinationRule = Callable[[Patch], bool]


@dataclass(frozen=True)
class EditConstraints:
    """Allowed operations by site, total cost limit, and combination rules.

    The policy is specified independently of failure locations and relevance.
    """

    policy_id: str
    allowed_ops_by_site: Mapping[SiteId, frozenset[EditOp]]
    max_cost: int
    combination_rules: tuple[CombinationRule, ...] = ()

    def __post_init__(self) -> None:
        if not self.policy_id:
            raise ValueError("edit policy_id is required")
        if self.max_cost <= 0:
            raise ValueError("edit max_cost must be positive")

    def allows_patch(self, patch: Patch) -> bool:
        if patch.cost > self.max_cost:
            return False
        for edit in patch.edits:
            allowed = self.allowed_ops_by_site.get(edit.target_site, frozenset())
            if edit.op not in allowed:
                return False
        return all(rule(patch) for rule in self.combination_rules)
