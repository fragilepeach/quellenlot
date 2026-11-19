"""Define the evidence and coverage rules used by the review workflow."""

from quellenlot_agents.models import Relation


def covers_assigned_findings(indexes: list[int], expected_count: int) -> bool:
    """Require one review entry for every zero-based finding index.

    Args:
        indexes: Finding indexes returned by the reviewer in any order.
        expected_count: Number of findings assigned to the reviewer.

    Returns:
        Whether exactly the assigned indexes appear, with no duplicates.
    """
    return sorted(indexes) == list(range(expected_count))


def effective_relation(relation: Relation, *, text_is_complete: bool) -> Relation:
    """Treat apparent omissions in incomplete sources as unassessable.

    Args:
        relation: Claim-to-source relation proposed by an analysis model.
        text_is_complete: Whether the snapshot contains the complete source text.

    Returns:
        The relation that can be recorded for this snapshot.
    """
    if relation == "omits" and not text_is_complete:
        return "not_assessable"
    return relation
