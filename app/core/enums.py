"""Stable vocabulary for persisted improvement decisions."""
from enum import StrEnum


class CandidateScope(StrEnum):
    INVARIANT = "INVARIANT"
    DOMAIN = "DOMAIN"


class CompositionAction(StrEnum):
    KEEP = "KEEP"
    DROP = "DROP"
    REVISE = "REVISE"
    MERGE = "MERGE"


class AttributionVerdict(StrEnum):
    HELPED = "HELPED"
    HURT = "HURT"
    NO_OBSERVED_EFFECT = "NO_OBSERVED_EFFECT"
    CONFOUNDED = "CONFOUNDED"
