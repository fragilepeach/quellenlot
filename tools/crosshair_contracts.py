"""Check production review rules against independent symbolic specifications."""

from quellenlot_agents.models import Relation
from quellenlot_agents.review_rules import covers_assigned_findings, effective_relation

_RELATIONS: tuple[Relation, ...] = (
    "supports",
    "qualifies",
    "contradicts",
    "omits",
    "not_assessable",
)


def review_index_coverage(indexes: list[int], count: int) -> bool:
    """Check exact coverage across small assignments in arbitrary order.

    Args:
        indexes: Candidate reviewer indexes, including duplicates and invalid values.
        count: Number of assigned source findings in the bounded search.

    Returns:
        Whether the production coverage rule accepts the assignments.

    pre: len(indexes) <= 3
    pre: 0 <= count <= 3
    post: __return__ == (len(indexes) == count and set(indexes) == set(range(count)))
    """
    return covers_assigned_findings(indexes, count)


def source_omission(relation_index: int, *, text_is_complete: bool) -> Relation:
    """Check the only change allowed by snapshot completeness.

    Args:
        relation_index: Index of a relation supported by the review schema.
        text_is_complete: Whether the full source was available for analysis.

    Returns:
        The relation produced by the workflow's evidence rule.

    pre: 0 <= relation_index < len(_RELATIONS)
    post: relation_index != 3 or text_is_complete or __return__ == "not_assessable"
    post: (relation_index == 3 and not text_is_complete) or __return__ == _RELATIONS[relation_index]
    """
    return effective_relation(_RELATIONS[relation_index], text_is_complete=text_is_complete)
