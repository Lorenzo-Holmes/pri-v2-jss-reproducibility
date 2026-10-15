"""Preservation observers shared by the effect estimators."""
from dataclasses import dataclass


@dataclass(frozen=True)
class PreservationObserver:
    observer_id: str
    resources: frozenset[str]
