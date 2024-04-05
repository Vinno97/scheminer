from scheminer.types import Relation


def detect_parent_child_confusion(relations: list[Relation]) -> list[Relation]:
    """Returns a list of possible parent-child confusions."""
    return [r for r in relations if r.from_strength == r.to_strength]
