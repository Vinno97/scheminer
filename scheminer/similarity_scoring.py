from typing import Iterable


def jaccard_metric(a: Iterable, b: Iterable) -> float:
    set_a = set(a)
    set_b = set(b)
    intersection = set_a & set_b
    union = set_a | set_b
    similarity = len(intersection) / len(union)
    return similarity


def jaccard_left(a: Iterable, b: Iterable) -> float:
    set_a = set(a)
    set_b = set(b)
    intersection = set_a & set_b
    union = set_a
    similarity = len(intersection) / len(union)
    return similarity


def jaccard_right(a: Iterable, b: Iterable) -> float:
    set_a = set(a)
    set_b = set(b)
    intersection = set_a & set_b
    union = set_b
    similarity = len(intersection) / len(union)
    return similarity
